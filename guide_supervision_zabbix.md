# DocSearch — Guide d'installation de la supervision

*Architecture 8 serveurs · Debian 13 « trixie » · Zabbix 7.0 LTS*

Supervision des **8 machines de production** et de **l'application** — au sens
de ce qu'un utilisateur constate : la recherche répond-elle, les documents
arrivent-ils dans l'index, la connexion fonctionne-t-elle.

> **Document confidentiel — usage interne.** 10 août 2026.
> Complète le « Guide d'installation — Production 8 serveurs », dont il
> reprend les noms de machines, de rôles et de fichiers.

## Sommaire

- 1. Vue d'ensemble
- 2. Prérequis
- 3. Ouvrir le pare-feu
- 4. Installer l'agent Zabbix sur les 8 machines
- 5. Déployer les sondes DocSearch
- 6. Créer le compte de supervision
- 7. Importer les modèles dans Zabbix
- 8. Créer les groupes d'hôtes et les hôtes
- 9. Lier les modèles et poser les macros
- 10. Vérification de bout en bout
- 11. Dépannage
- 12. Ce qui reste à définir
- 13. Fichiers de référence

## 1. Vue d'ensemble

La supervision se déploie **après** l'installation de la production, sur une
plateforme qui fonctionne. Elle n'ajoute aucun composant à l'application : ni
conteneur, ni port applicatif, ni dépendance dans les images. Elle se compose
de trois choses seulement :

- un **agent Zabbix** sur chacune des 8 machines ;
- **sept scripts de collecte** en `/usr/local/bin`, appelés par cet agent ;
- **sept modèles** importés dans le serveur Zabbix, qui portent 114 éléments,
  7 prototypes de découverte et 62 déclencheurs.

Tout le reste — Elasticsearch, Kibana, Tika, les ports TCP — est interrogé
**directement par le serveur Zabbix**, sans agent.

### 1.1 Où est quoi

| Emplacement | Contenu |
|---|---|
| `docsearch-infra/zabbix/templates/` | Le fichier à importer dans Zabbix |
| `docsearch-infra/zabbix/scripts/` | Les 7 scripts de collecte |
| `docsearch-infra/zabbix/agent/` | Configuration de l'agent (`UserParameter`) |
| `docsearch-infra/zabbix/sudoers/` | La règle sudo des 3 sondes qui ont besoin de root |
| `docsearch-infra/zabbix/deployer-sondes.sh` | Installe tout cela sur une machine, selon son rôle |
| `docsearch-infra/zabbix/README.md` | Pourquoi ce découpage, et ce qui n'est pas surveillé |
| `docsearch-infra/zabbix/REFERENCE.md` | Catalogue complet des éléments et déclencheurs |

### 1.2 Ce qui est surveillé, machine par machine

| Machine | Modèles à lier |
|---|---|
| es-data-1, es-data-2 | Linux by Zabbix agent · DocSearch socle · DocSearch noeud Elasticsearch |
| es-voting | les trois ci-dessus **+** DocSearch arbitre et Kibana |
| kafka | Linux by Zabbix agent · DocSearch socle · DocSearch Kafka |
| frontend | Linux by Zabbix agent · DocSearch socle · DocSearch frontend |
| ingest-1, ingest-2, ingest-3 | Linux by Zabbix agent · DocSearch socle · DocSearch ingestion |
| *DocSearch — application* (hôte logique) | DocSearch application |

`Linux by Zabbix agent` est le modèle livré avec Zabbix : CPU, mémoire,
disques, réseau, redémarrages. Les modèles DocSearch ne redéclarent aucune de
ses clés — ils se lient par-dessus, sans conflit.

> **💡  Le neuvième hôte n'est pas une machine**
> `DocSearch — application` est un hôte **logique**, sans interface et sans
> agent. Il porte l'état du CLUSTER Elasticsearch — relevé une seule fois, et
> non trois, sinon une panne unique sonnerait sur les trois nœuds — et les
> agrégats inter-machines. Ceux-ci voient ce qu'aucune machine ne voit seule :
> un watcher démarré deux fois (chaque document indexé en double, et les deux
> machines se portent très bien), les 6 Tika tombés ensemble, les 9 workers
> réduits à 3.

## 2. Prérequis

- Les 8 machines installées et en service (voir le guide d'installation
  production), `docsearch.target` démarré partout.
- Un serveur Zabbix **7.0 LTS** en état de marche, avec accès réseau aux
  8 machines.
- Le dépôt `docsearch-infra` cloné sur chacune des 8 machines — il l'est déjà,
  l'installation de production l'exige.
- Les paquets de l'agent Zabbix récupérés sur la machine de préparation
  (§4.1) : **la production n'a aucun accès Internet.**

> **⚠️  Le serveur Zabbix doit voir le LAN du cluster**
> Les vérifications sans agent partent du serveur Zabbix vers 9200 (les
> 3 machines ES), 5601 (es-voting), 9998 et 9999 (les 3 machines
> d'ingestion), 443, 80, 8000, 6379 et 9092. Ces ports sont déjà ouverts par
> le guide d'installation, mais **pour `192.168.10.0/24` seulement** : si le
> serveur Zabbix est ailleurs, chaque règle est à élargir à son adresse.

## 3. Ouvrir le pare-feu

**C'est l'étape qui bloque toujours en premier.** Le jeu de règles nftables du
guide d'installation (§5.5) est en `policy drop` et n'autorise qu'une liste de
ports fixe — **où le 10050 de l'agent Zabbix ne figure pas**. Tant que cette
étape n'est pas faite, aucune machine ne répond, et le symptôme côté Zabbix est
un laconique « Get value from agent failed ».

Sur les 8 machines :

```bash
sudo nft add rule inet filter input ip saddr <IP_SERVEUR_ZABBIX> tcp dport 10050 accept
```

Puis reporter la règle dans `/etc/nftables.conf`, faute de quoi elle disparaît
au premier redémarrage :

```bash
sudo sed -i 's|tcp dport { 22,|tcp dport { 22,10050,|' /etc/nftables.conf
sudo nft -c -f /etc/nftables.conf && sudo systemctl reload nftables
```

> **⚠️  Vérifier la règle AVANT de recharger**
> `nft -c -f` contrôle le fichier sans l'appliquer. Recharger un
> `/etc/nftables.conf` invalide sur une machine distante en `policy drop`
> coupe la session SSH en cours et n'en laisse pas ouvrir de nouvelle.

Si le serveur Zabbix n'est pas sur `192.168.10.0/24`, ajouter aussi son adresse
en source autorisée pour les ports applicatifs interrogés sans agent (§2).

## 4. Installer l'agent Zabbix sur les 8 machines

### 4.1 Récupérer les paquets (machine de préparation)

La production n'a aucun accès Internet : les `.deb` se téléchargent sur la
machine de préparation et se transfèrent avec les images de conteneurs (voir
`HOWTO-deploiement-hors-ligne.md`).

```bash
mkdir -p ~/transfert/zabbix && cd ~/transfert/zabbix
apt-get download zabbix-agent2
apt-get download $(apt-cache depends --recurse --no-recommends --no-suggests \
                     --no-conflicts --no-breaks --no-replaces --no-enhances \
                     zabbix-agent2 | grep '^\w' | sort -u)
```

> **💡  L'agent classique convient aussi**
> Aucune sonde DocSearch n'utilise de clé propre à l'agent 2 : ce sont des
> `UserParameter`, plus une clé standard (`system.swap.size`). Si le miroir
> interne ne fournit que `zabbix-agent`, il fait parfaitement l'affaire —
> passer alors `AGENT_DIR=/etc/zabbix/zabbix_agentd.d` au script du §5.

### 4.2 Installer et configurer (les 8 machines)

```bash
sudo dpkg -i ~/transfert/zabbix/*.deb
```

Dans `/etc/zabbix/zabbix_agent2.conf` :

```
Server=<IP_SERVEUR_ZABBIX>
ServerActive=<IP_SERVEUR_ZABBIX>
Hostname=<nom de la machine, IDENTIQUE au nom d'hôte déclaré dans Zabbix>
Include=/etc/zabbix/zabbix_agent2.d/*.conf
Timeout=30
```

> **⚠️  `Timeout=30` est obligatoire sur la machine kafka**
> `kafka-consumer-groups` interroge le coordinateur de groupe et met couramment
> 5 à 10 secondes. Avec le défaut (3 s), la sonde de la file d'indexation ne
> remonte jamais rien — et l'élément reste « non supporté » sans autre
> explication qu'un dépassement de délai. Le poser partout ne coûte rien.

```bash
sudo systemctl enable --now zabbix-agent2
```

## 5. Déployer les sondes DocSearch

Sur chaque machine, avec le **même nom de rôle** que
`quadlet/install-units.sh` :

```bash
cd ~/docsearch/docsearch-infra/zabbix && sudo ./deployer-sondes.sh <rôle>
```

| Machine | Rôle |
|---|---|
| es-data-1, es-data-2 | `es-data` |
| es-voting | `es-voting` |
| kafka | `kafka` |
| frontend | `frontend` |
| ingest-1, ingest-2, ingest-3 | `ingest` |

`--dry-run` montre ce qui serait fait sans rien écrire. Le script installe les
scripts de collecte en `0755 root:root`, la configuration de l'agent, la règle
sudo — **contrôlée par `visudo -c` avant d'être posée** — puis vérifie que
chaque sonde s'exécute sous l'identité de l'utilisateur `zabbix`.

Sur `es-data` et `es-voting`, il n'installe que les sondes communes : le nœud
Elasticsearch et Kibana sont interrogés en HTTP par le serveur Zabbix.

Redémarrer l'agent après le déploiement :

```bash
sudo systemctl restart zabbix-agent2
```

> **⚠️  Pourquoi une règle sudo, et pourquoi elle est étroite**
> Les unités Quadlet de production sont installées dans
> `/etc/containers/systemd` : elles sont pilotées par le podman **rootful**, et
> les conteneurs n'existent tout simplement pas pour l'utilisateur `zabbix`.
> Trois sondes doivent y accéder — santé des conteneurs, Redis, Kafka. La règle
> autorise **trois chemins précis, sans argument variable**. Un
> `zabbix ALL=(root) NOPASSWD: /usr/bin/podman *` aurait été plus simple à
> écrire et aurait donné `podman run --privileged -v /:/hôte`, c'est-à-dire
> root complet, à quiconque prend la main sur le compte de l'agent.
> Corollaire : les scripts doivent rester `root:root`. Modifiables par
> `zabbix`, ils vaudraient la même chose.

## 6. Créer le compte de supervision

**Sur frontend uniquement.** Les sondes applicatives — `/admin/status`,
`/metrics`, la recherche de bout en bout — ont besoin d'une vraie session :
l'API vérifie elle-même un jeton RS256 qu'elle a signé, et ne croit aucun
en-tête d'identité sur parole (`TRUST_X_USER_HEADER` est refusé au démarrage
en `API_ENV=production`).

```bash
sudo podman exec -it docsearch-api python scripts/gerer-comptes-locaux.py creer svc-supervision --groupes docsearch-users,docsearch-admins --nom "Supervision Zabbix"
```

Les deux groupes sont nécessaires, et pour deux raisons distinctes :
`docsearch-users` pour qu'une session puisse s'ouvrir — le contrôle d'accès a
lieu à la connexion, pas seulement à chaque requête — et `docsearch-admins`
pour `/admin/status`.

> **💡  Un compte LOCAL, pas un compte d'annuaire**
> Un compte local reste opérant quand l'annuaire est en panne, c'est-à-dire
> exactement quand la supervision doit encore parler. C'est le même
> raisonnement que pour le compte de secours du §6.4 du guide d'installation —
> mais un compte distinct, pour que le journal d'audit distingue une
> intervention humaine d'un relevé automatique.

Renseigner ensuite `/etc/zabbix/docsearch-supervision.conf`, créé depuis son
modèle par `deployer-sondes.sh frontend` en `0640 root:zabbix` :

```
DOCSEARCH_URL=https://127.0.0.1
DOCSEARCH_HOTE=docsearch.local
DOCSEARCH_IDENTIFIANT=svc-supervision
DOCSEARCH_MOT_DE_PASSE=<le mot de passe saisi ci-dessus>
DOCSEARCH_REQUETE_TEMOIN=rapport
```

`DOCSEARCH_HOTE` doit correspondre au `server_name` de Nginx.

> **⚠️  La requête témoin subit le filtrage ACL de ce compte**
> Choisir un terme dont on sait qu'il ramène des résultats **avec
> `svc-supervision`**, et le vérifier une fois à la main. Un terme validé avec
> un compte d'administration mais filtré pour celui-ci ferait sonner en
> permanence « la requête témoin ne ramène plus aucun résultat ».

### Ce que ce compte coûte

- Le mot de passe est **sur le disque de frontend**, lisible par `zabbix`. Il
  n'est ni dans le dépôt, ni dans un `Containerfile`, ni en argument de ligne
  de commande — donc absent de l'historique du shell et de la liste des
  processus. Si la politique l'exige, le remplacer par une macro secrète Zabbix
  ou un secret Vault passé en variable d'environnement de l'agent.
- **Environ 96 lignes par jour dans `login_events`.** Le jeton d'accès vit
  15 minutes et la session est rafraîchie, pas rouverte à chaque relevé. Ces
  lignes portent l'agent utilisateur `Zabbix-DocSearch` : filtrables d'un coup
  dans le journal d'audit.

## 7. Importer les modèles dans Zabbix

*Data collection → Templates → Import*, fichier
`docsearch-infra/zabbix/templates/docsearch-zabbix-7.0.yaml`. Cocher
**Create new** pour *Templates*, *Template groups*, *Value maps*.

L'import crée le groupe de modèles `Templates/DocSearch` et les 7 modèles. Il
ne crée **ni hôtes ni groupes d'hôtes** : c'est l'objet du §8.

## 8. Créer les groupes d'hôtes et les hôtes

### 8.1 Les groupes

Les agrégats du modèle `DocSearch application` désignent ces groupes **par leur
nom, à l'orthographe et à la casse près**. Un groupe mal nommé ne produit pas
d'erreur : l'agrégat rend simplement « pas de données ».

| Groupe | Hôtes |
|---|---|
| `DocSearch` | les 8 machines |
| `DocSearch/es` | es-data-1, es-data-2, es-voting |
| `DocSearch/kafka` | kafka |
| `DocSearch/frontend` | frontend |
| `DocSearch/ingestion` | ingest-1, ingest-2, ingest-3 |
| `DocSearch/application` | l'hôte logique |

Chaque machine appartient à `DocSearch` **et** à son groupe de rôle.

### 8.2 Les hôtes

Les 8 machines : *Data collection → Hosts → Create host*, avec une **interface
Agent** pointant sur l'IP de la machine (port 10050) et un *Host name*
strictement identique au `Hostname=` de `zabbix_agent2.conf`.

Le neuvième, `DocSearch — application` : **sans aucune interface**. Il ne porte
que des éléments HTTP et calculés, qui n'en ont pas besoin.

## 9. Lier les modèles et poser les macros

Lier les modèles selon le tableau du §1.2, puis poser ces macros — onglet
*Macros* de l'hôte, *Inherited and host macros* :

| Hôte | Macro | Valeur |
|---|---|---|
| **es-voting** | `{$DOCSEARCH.ES.ROLE.ATTENDU}` | `voting_only` |
| **DocSearch — application** | `{$DOCSEARCH.ES.URL}` | `http://<ES_DATA1_IP>:9200` |
| frontend, ingest-* | `{$DOCSEARCH.SOURCES.CHEMIN}` | le point de montage réel, si différent de `/data/docsearch-sources` |

> **⚠️  La première n'est pas optionnelle**
> Sans elle, es-voting déclenchera en permanence « ce nœud n'a pas le rôle
> attendu » : le modèle attend `data` par défaut, ce qui est juste pour les deux
> nœuds de données et faux pour l'arbitre. C'est le même déclencheur qui
> attrape un `elasticsearch.env` recopié d'une machine à l'autre sans
> adaptation — le piège du §6.1 du guide d'installation, qui produit sinon un
> nœud refusant silencieusement de rejoindre le cluster.

Les seuils (retard d'indexation, tas JVM, mémoire Redis, expiration du
certificat) ont des valeurs par défaut raisonnables et se surchargent de la
même façon. Le catalogue complet est dans `REFERENCE.md`.

## 10. Vérification de bout en bout

### 10.1 Les sondes, sur la machine

Sous l'identité réelle de l'agent, pas sous root :

```bash
sudo runuser -u zabbix -- /usr/local/bin/docsearch-zabbix-unites
```

```bash
sudo runuser -u zabbix -- sudo -n /usr/local/bin/docsearch-zabbix-podman
```

Sur frontend, la sonde applicative complète :

```bash
sudo runuser -u zabbix -- /usr/local/bin/docsearch-zabbix-api etat
```

Une sonde saine rend du JSON. `"http":200` dans la sortie de la dernière
signifie que le compte de supervision fonctionne de bout en bout : session
ouverte, groupe d'administration reconnu, `/admin/status` servi.

### 10.2 Les sondes, depuis le serveur Zabbix

```bash
zabbix_get -s <ip_machine> -k docsearch.unites
```

Un `ZBX_NOTSUPPORTED` affiche sa propre cause en clair. Un délai dépassé sans
message est presque toujours le pare-feu (§3).

### 10.3 Les données, dans l'interface

*Monitoring → Latest data*, filtré sur le groupe `DocSearch`. Au bout de deux
ou trois minutes, chaque machine doit montrer ses unités systemd découvertes.
La découverte de bas niveau tourne à son propre rythme : compter jusqu'à une
heure avant de voir apparaître tous les éléments par unité et par conteneur, ou
forcer avec *Execute now* sur la règle de découverte.

Vérification finale, celle qui compte :

| À regarder | Valeur attendue |
|---|---|
| `DocSearch — application` → Agrégat : instances Tika joignables | 6 |
| `DocSearch — application` → Agrégat : watchers actifs dans le cluster | **exactement 1** |
| `DocSearch — application` → Agrégat : workers d'indexation dans le cluster | 9 |
| `DocSearch — application` → Cluster ES : état | Vert |
| frontend → Recherche : résultats de la requête témoin | > 0 |
| frontend → TLS : jours avant expiration du certificat | ~365 après installation |

## 11. Dépannage

**11.1 Tous les éléments d'une machine sont en échec, sans message**

Le pare-feu (§3). `nft list ruleset | grep 10050` sur la machine ; si la ligne
manque, la règle n'a pas été reportée dans `/etc/nftables.conf` et a disparu au
redémarrage.

**11.2 `docsearch.conteneurs` rend un tableau vide `[]`**

La sonde a interrogé le podman **rootless** de l'utilisateur `zabbix`, où il
n'y a rien. Vérifier que `sudo -n` fonctionne :
`runuser -u zabbix -- sudo -n /usr/local/bin/docsearch-zabbix-podman`. Un
« sudo: a password is required » signale que `/etc/sudoers.d/zabbix-docsearch`
est absent ou que le chemin du script y diffère.

**11.3 `docsearch.kafka.file` reste non supporté**

`Timeout=30` manquant dans `zabbix_agent2.conf` (§4.2). Le script, lui, met
jusqu'à 25 secondes par construction.

**11.4 Les sondes applicatives rendent `"http":401`**

Le compte de supervision ne s'authentifie pas. Dans l'ordre : mot de passe
erroné dans `docsearch-supervision.conf` ; compte inexistant
(`gerer-comptes-locaux.py lister`) ; ou compte bloqué par la limite de débit —
5 échecs par tranche de 15 minutes, la fenêtre se vide d'elle-même.

**11.5 `"http":403`**

La session s'ouvre mais `/admin/status` est refusé : le compte n'a pas
`docsearch-admins`. Le recréer avec les deux groupes (§6).

**11.6 `"http":503` sur `/health` alors que le cluster ES est vert**

`ES_HOST` ne liste qu'un seul hôte, es-data-1 (§2.3 du guide d'installation).
Si ce nœud est tombé, l'API perd son point d'entrée même si le cluster reste
opérationnel sur les autres. C'est le comportement attendu de la sonde : elle
signale ce que subit l'application, pas ce que dit le cluster.

**11.7 es-voting déclenche « ce nœud n'a pas le rôle attendu »**

La macro `{$DOCSEARCH.ES.ROLE.ATTENDU}` n'a pas été posée à `voting_only`
(§9).

**11.8 « Aucun watcher actif » alors que le watcher tourne**

L'agrégat additionne `docsearch.unite.actif[docsearch-watcher.service]` sur le
groupe `DocSearch/ingestion`. Vérifier l'orthographe exacte du groupe (§8.1) et
qu'ingest-1 y figure bien.

## 12. Ce qui reste à définir

La **chaîne d'alerte** — actions, escalades, destinataires — n'est pas livrée :
elle dépend des usages de l'équipe et des horaires d'astreinte. Les priorités
des déclencheurs sont posées pour s'y brancher directement :

| Priorité | Sens retenu | Exemples |
|---|---|---|
| Désastre | Les utilisateurs ne peuvent plus travailler | API muette, recherche en échec, cluster ES rouge, registre des sources disparu |
| Haute | Une fonction est perdue | Kafka arrêté, aucun Tika, watcher muet, clés de signature illisibles |
| Moyenne | À traiter en heures ouvrées | Cluster jaune, écritures ES rejetées, horloge désynchronisée |
| Avertissement | Tendance à surveiller | Retard d'indexation, mémoire Redis, certificat à 30 jours |
| Information | Trace, pas alerte | Changement de version de podman |

Sont également hors périmètre de ce premier jeu de sondes, avec les raisons,
dans `docsearch-infra/zabbix/README.md` §8 : JMX Kafka, consommation par
conteneur via `podman stats`, analyse des journaux applicatifs.

> **⚠️  Les seuils numériques sont des points de départ**
> Retard d'indexation, tas JVM, mémoire Redis : ces valeurs sont raisonnables,
> pas mesurées sur ce corpus. À réviser après le test de montée en charge à
> 4 millions de documents, quand on saura à quoi ressemble un régime normal.

## 13. Fichiers de référence

| Fichier | Contenu |
|---|---|
| `docsearch-infra/zabbix/README.md` | Le pourquoi du découpage, ce qui n'est pas surveillé, limites connues |
| `docsearch-infra/zabbix/REFERENCE.md` | Catalogue complet : chaque élément, chaque déclencheur, chaque macro |
| `docsearch-infra/zabbix/templates/docsearch-zabbix-7.0.yaml` | Le fichier à importer |
| `docsearch-infra/zabbix/deployer-sondes.sh` | Déploiement sur une machine, par rôle |
| `docsearch-infra/zabbix/generer-reference.py` | Régénère `REFERENCE.md` depuis le modèle |
| `guide_install_production_8_serveurs.md` | Installation de la production, dont ce guide reprend les rôles |
| `guide_mise_a_jour_production.md` | Mise à jour de la production |

> **💡  `REFERENCE.md` est généré, pas rédigé**
> Il est produit par `generer-reference.py` à partir du modèle Zabbix
> lui-même. Après toute modification des sondes, le régénérer — et
> `./generer-reference.py --verifier` sort en erreur si le catalogue a divergé,
> de quoi le brancher sur la CI.
