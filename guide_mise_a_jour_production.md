# DocSearch — Guide de mise à jour de la production

*Architecture 8 serveurs · Debian 13 « trixie » · podman + systemd (Quadlet)*

**Code applicatif** (API · Ingestion · UI) et **composants d'infrastructure**
(ES · Kafka · Tika · Redis · Nginx) — **sans interruption de la recherche**,
sauf Nginx et Kafka (fenêtre courte).

> **Document confidentiel — usage interne.** 9 juillet 2026.
> Converti du format Word le 2026-08-06 : le Markdown est désormais la
> source, il se relit et se compare dans Git comme le reste du dépôt.

## Sommaire

- 1. Vue d'ensemble
- 2. Avant toute mise à jour : sauvegarde
- 3. Mise à jour du code applicatif (API, ingestion, UI)
- 4. Mise à jour d'Elasticsearch
- 5. Mise à jour de Kafka
- 6. Mise à jour de Tika
- 7. Mise à jour de Redis et Nginx
- 8. Mise à jour de la configuration partagée (/etc/docsearch)
- 9. Vérification post mise à jour
- 10. Procédure de rollback
- 11. Récapitulatif — fenêtre de maintenance par composant

## 1. Vue d'ensemble

Ce guide couvre la mise à jour de la plateforme DocSearch une fois déployée en production sur les 8 serveurs (voir « Guide d'installation — Production 8 serveurs »). Trois natures de mise à jour, traitées séparément car leurs procédures et leur impact diffèrent :

- Code applicatif DocSearch (docsearch-api, docsearch-ingestion, docsearch-ui-vue) — le cas le plus fréquent, à chaque nouvelle version poussée sur les dépôts Git.
- Composants d'infrastructure (Elasticsearch, Kafka, Tika, Redis, Nginx) — changement de version d'image, plus rare, plus sensible.
- Configuration partagée (/etc/docsearch/*.env) — un fichier par machine, dont les valeurs communes (IP du cluster, index, LDAP) doivent rester cohérentes entre les 8 machines.
> **💡  Pas de temps d'arrêt total, mais pas d'invisibilité parfaite non plus**
> L'architecture actuelle n'élimine pas complètement les coupures : l'API et l'UI tournent en instance unique sur frontend (redémarrage = quelques secondes d'indisponibilité de la recherche), et Kafka est un broker unique (redémarrage = pause de l'ingestion, pas de la recherche). Les workers et Tika, eux, sont répliqués — leur mise à jour peut se faire sans aucune coupure visible, une instance à la fois.
> Ce guide indique pour chaque composant l'impact réel attendu — voir aussi le récapitulatif du §11.

> **⚠️  Toujours valider en pilote avant la production**
> Comme pour le dimensionnement initial, une mise à jour de composant sensible (Elasticsearch en particulier) doit être testée sur un environnement représentatif avant d'être appliquée aux 8 serveurs de production — voir le guide d'installation pour reproduire un environnement de test.

## 2. Avant toute mise à jour : sauvegarde

manage.sh backup n'est pas utilisable tel quel (outil mono-hôte) — la sauvegarde s'effectue directement contre le cluster Elasticsearch, depuis n'importe quelle machine ayant accès réseau à es-data-1 :

```bash
# Enregistrer (une seule fois) le dépôt de snapshots sur les 3 nœuds ES —
# le chemin doit exister et être accessible en écriture sur CHAQUE nœud
curl -X PUT "http://<ES_DATA1_IP>:9200/_snapshot/backup_repo" \
  -H 'Content-Type: application/json' -d '{
    "type": "fs",
    "settings": { "location": "/backup" }
  }'

# Déclencher un snapshot avant la mise à jour
curl -X PUT "http://<ES_DATA1_IP>:9200/_snapshot/backup_repo/snap_$(date +%s)?wait_for_completion=true"
```

> **⚠️  Le chemin /backup doit être un volume partagé entre les 3 nœuds ES**
> Elasticsearch exige que tous les nœuds du cluster voient le même chemin de dépôt de snapshot — sur un déploiement multi-machines, cela signifie un partage réseau (NFS/CIFS) monté au même chemin sur es-data-1, es-data-2 et es-voting, déclaré dans path.repo côté configuration ES. À mettre en place une fois, indépendamment de ce guide de mise à jour.

Pour la configuration à chaud (Redis — types de fichiers, filtres de chemin, paramètres opérationnels), la persistance RDB de Redis (volume podman systemd-redis-data) suffit ; aucune action supplémentaire n'est nécessaire avant une mise à jour de code applicatif.

## 3. Mise à jour du code applicatif (API, ingestion, UI)

Chaque dépôt (docsearch-api, docsearch-ingestion, docsearch-ui-vue) évolue et se déploie indépendamment — inutile de reconstruire les 3 images pour une modification touchant un seul dépôt.

> **📌  Version produit : le fichier VERSION, dans les 3 dépôts**
> La version affichée aux utilisateurs (pied de page, aide) et en administration vient du fichier `VERSION` à la racine de chaque dépôt construit en image. Elle est **déclarative et identique dans les trois** : la monter fait partie de la préparation d'une livraison, avant `./manage.sh build`, jamais après. Le commit et la date de construction, eux, sont relevés automatiquement dans git par `manage.sh` et n'ont pas à être tenus à jour.
>
> Une mise à jour ne portant que sur une brique laisse volontairement les versions divergentes le temps de la bascule — l'administration l'affiche en avertissement, c'est le comportement voulu (voir §9).

### 3.1 docsearch-ingestion (workers, watcher) — sans interruption

Les workers sont répliqués (3 par machine d'ingestion) — les mettre à jour une machine à la fois, jamais les 3 simultanément, pour qu'il reste toujours des workers actifs consommant Kafka :

```bash
# Image construite AILLEURS : la production n'a pas d'accès Internet.
# Sur la machine de préparation : ./manage.sh build ingestion
# puis podman save localhost/docsearch/ingestion:latest | gzip > ingestion.tar.gz
# Sur ingest-1, ingest-2 PUIS ingest-3, l'une après l'autre :
gunzip -c ingestion.tar.gz | sudo podman load && sudo systemctl restart 'docsearch-worker-*' docsearch-watcher
```

Les commandes ponctuelles d'administration (manage.sh init, add-file-source…) lancent un conteneur jetable sur cette même image : elles prendront la nouvelle version au prochain appel, aucune action requise ici.

> **💡  Un redémarrage de worker en cours de traitement est sans risque**
> Le commit Kafka n'a lieu qu'après un flush réussi vers Elasticsearch (voir worker.py) — un message en cours de traitement au moment du redémarrage n'est jamais perdu, il est simplement redistribué à un autre worker actif par le rééquilibrage du groupe de consumers.

### 3.2 docsearch-api et docsearch-ui-vue — brève interruption

Ces deux services tournent en instance unique sur frontend : leur redémarrage entraîne quelques secondes d'indisponibilité de la recherche (le temps que le nouveau conteneur passe le healthcheck).

```bash
# Sur frontend :
# Images construites puis transférées depuis la machine de préparation
gunzip -c api.tar.gz | sudo podman load
sudo systemctl restart docsearch-api docsearch-alert-worker   # alert-worker partage l'image
gunzip -c ui-vue.tar.gz | sudo podman load && sudo systemctl restart docsearch-ui-vue
```

> **💡  Réduire l'interruption à zéro — piste hors périmètre de ce guide**
> Passer l'API à plusieurs réplicas derrière Nginx (comme les workers) éliminerait cette coupure, au prix d'une complexité supplémentaire (répartition de charge, cohérence du cache Redis entre instances). Non mis en place ici — à évaluer séparément si la disponibilité de la recherche pendant les mises à jour devient un enjeu critique.

### 3.3 Bascule vers l'authentification par session — une seule fois

Cette montée de version remplace l'identification par en-tête HTTP X-User par une authentification réelle : jeton de session signé par l'application, page de connexion, comptes de secours. Trois choses doivent être faites AVANT de redémarrer l'API, sans quoi l'application démarre mais plus personne ne se connecte.

1. Générer la paire de clés qui signe les sessions. Sans elle, /auth/login répond 503.

```bash
sudo install -d -o 1000 -g 1000 -m 700 /etc/docsearch/jwt
sudo podman run --rm -v /etc/docsearch/jwt:/etc/docsearch/jwt:Z \
     localhost/docsearch/api:latest python scripts/generer-cles.py
```

2. Compléter /etc/docsearch/docsearch.env À LA MAIN. Point à ne pas manquer : install-units.sh ne réécrit JAMAIS un fichier de configuration existant, donc aucune des variables nouvelles n'y arrive toute seule.

```bash
API_ENV=production          # verrouille les contournements de recette
JWT_ACTIVE_KID=...          # les 3 lignes affichées à l'étape 1
JWT_PRIVATE_KEY_PATH=...
JWT_PUBLIC_KEY_PATH=...
COOKIE_SECURE=true          # l'accès est en HTTPS derrière Nginx
COOKIE_SAMESITE=strict      # 'lax' si l'on arrive par un lien de messagerie
ACCESS_GROUP=docsearch-users
ADMIN_GROUP=docsearch-admins
```

3. Si LDAP_HOST commence par ldap:// — donc en clair — ajouter LDAP_ALLOW_PLAINTEXT_INSECURE=true. Le bind non chiffré est désormais refusé par défaut : sans cette dérogation explicite, l'annuaire devient injoignable et toute connexion répond 503. La dérogation reste acceptée en production, mais elle est journalisée en avertissement à chaque connexion.

Créer enfin un compte de secours, avant d'en avoir besoin : il porte ses propres groupes, et c'est la seule voie d'accès à l'administration si l'annuaire devient indisponible.

```bash
sudo podman exec -it docsearch-api python scripts/gerer-comptes-locaux.py \
     creer secours.admin --groupes docsearch-users,docsearch-admins
```

Ce qui cesse de fonctionner, et qu'il faut corriger dans vos scripts : toute commande d'administration qui présentait un en-tête X-User. L'API l'ignore désormais. Ouvrir un bocal à cookies avec /auth/login, puis rejouer les appels avec « curl -b » — la recette complète est au §9, sur l'exemple d'une recherche. Le contrôle qui vérifie la bascule :

```bash
curl -H 'X-User: un.admin' https://<FRONTEND_IP>/admin/status   # doit répondre 401
```

### 3.4 Migrations d'index — une seule fois par fonctionnalité

Trois fonctionnalités livrées les 2026-08-12 et 2026-08-13 s'appuient sur des réglages d'analyse ou des champs que les index déjà créés n'ont pas. Redémarrer les conteneurs ne les pose pas : ce sont des opérations sur les index eux-mêmes, à lancer une fois, après la mise à jour du code.

Le point à retenir : tant que la migration n'est pas passée, la fonctionnalité est **inerte et silencieuse**. Aucune des trois ne produit d'erreur quand son champ manque — une recherche exacte sur un index non migré ne remonte rien, sans le moindre signal dans les journaux, et se lit exactement comme « aucun document ne correspond ».

Depuis ingest-1 (la machine d'où sont déjà lancées les commandes ponctuelles, §3.1) :

```bash
cd ~/docsearch/docsearch-infra
# 1. Thésaurus métier — index fermé/rouvert quelques secondes, AUCUNE réindexation.
#    Ne concerne que les sources fichiers : les index SQL et web ne reçoivent
#    pas le filtre de synonymes, c'est voulu.
sudo ./manage.sh migrer-synonymes

# 2. Recherche exacte (case à cocher et opérateur « exact: ») — les trois
#    familles d'index (fichiers, SQL, web), qui partagent l'alias de recherche.
sudo ./manage.sh migrer-exact              # simulation, n'écrit rien
sudo ./manage.sh migrer-exact --apply

# 3. Empreinte de contenu, pour le rapport de doublons — relit les fichiers
#    sur disque, SANS appeler Tika : pas de réindexation.
sudo ./manage.sh backfill-hashes           # simulation, n'écrit rien
sudo ./manage.sh backfill-hashes --apply
```

`migrer-exact` et `backfill-hashes` simulent par défaut ; `migrer-synonymes` n'a pas de simulation, étant idempotente et rejouable sans dommage. Les trois acceptent un nom de source en argument pour ne traiter que celle-là.

⚠️ `migrer-exact --apply` rend la main **avant** la fin du travail : la réécriture des documents est lancée en tâche de fond côté Elasticsearch (`_update_by_query`). Suivre son avancement avec `GET _tasks/<tâche>` — l'identifiant de tâche figure dans la sortie de la commande — plutôt que de conclure au succès sur le retour de l'invite.

Contrôle que la migration a bien pris, une fois la tâche terminée : cocher **Recherche exacte** dans l'interface et relancer une recherche qui donnait des résultats sans elle. Une liste vide sur toutes les sources signale un index oublié, pas un corpus vide. Côté moteur, le sous-champ doit exister :

```bash
curl -s "http://<ES_DATA1_IP>:9200/docsearch-all/_mapping/field/content.exact?pretty"
```

Le thésaurus lui-même se règle ensuite depuis **Administration › Thésaurus**, à chaud : la migration ne pose que l'analyseur, pas les règles.

## 4. Mise à jour d'Elasticsearch

> **⚠️  Un seul nœud à la fois, jamais deux simultanément**
> Avec seulement 2 nœuds de données, arrêter es-data-1 ET es-data-2 en même temps rend le cluster totalement indisponible (recherche ET écriture). La procédure ci-dessous traite les 3 nœuds strictement l'un après l'autre, en attendant le retour au vert avant de passer au suivant.

### 4.1 Procédure — répéter pour es-data-1, puis es-data-2, puis es-voting

- Désactiver la réallocation de shards pour un arrêt propre du nœud :
```bash
curl -X PUT "http://<ES_DATA1_IP>:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '{
    "persistent": { "cluster.routing.allocation.enable": "primaries" }
  }'
```

- L'image de la nouvelle version doit avoir été chargée au préalable (sudo podman load). Sur le nœud concerné, arrêter l'unité, modifier son tag d'image, recharger systemd, puis redémarrer :
```bash
sudo systemctl stop docsearch-es        # ou docsearch-es03-voting sur es-voting
sudo nano /etc/containers/systemd/docsearch-es.container   # Image=...elasticsearch:<nouvelle_version>
sudo systemctl daemon-reload && sudo systemctl start docsearch-es
```

- Attendre que le nœud rejoigne le cluster :
```bash
curl -s "http://<ES_DATA1_IP>:9200/_cat/nodes?v"
```

- Réactiver la réallocation et attendre le statut vert avant de passer au nœud suivant :
```bash
curl -X PUT "http://<ES_DATA1_IP>:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '{
    "persistent": { "cluster.routing.allocation.enable": "all" }
  }'
curl -s "http://<ES_DATA1_IP>:9200/_cluster/health?wait_for_status=green&timeout=5m"
```

> **⚠️  Montées de version majeure — vérifier les breaking changes**
> Ce guide couvre les montées de version mineure/patch (ex. 9.4.3 → 9.4.5), compatibles avec une mise à jour rolling nœud par nœud. Une montée de version majeure (ex. 9.x → 10.x) peut exiger une réindexation complète ou casser des mappings existants — toujours consulter les notes de version Elastic et tester sur un environnement pilote avant toute application en production.

### 4.2 Kibana

Kibana n'est pas un nœud du cluster ES — son redémarrage n'affecte ni la recherche ni l'indexation, seulement la disponibilité du tableau de bord d'administration pendant quelques secondes :

```bash
sudo systemctl restart docsearch-kibana
```

## 5. Mise à jour de Kafka

> **⚠️  Broker unique — pause de l'ingestion pendant le redémarrage**
> Contrairement à Elasticsearch, il n'existe qu'un seul broker Kafka (cohérent avec son rôle de simple file de travail, pas de système d'enregistrement durable). Son redémarrage interrompt temporairement la publication et la consommation de nouveaux documents. La RECHERCHE n'est pas affectée — elle ne dépend pas de Kafka. Préférer une fenêtre de faible activité d'ingestion.

```bash
# Sur kafka :
# L'image confluentinc/cp-kafka:<nouvelle_version> doit avoir été chargée au préalable (sudo podman load)
sudo systemctl stop docsearch-kafka
sudo nano /etc/containers/systemd/docsearch-kafka.container   # Image=...cp-kafka:<nouvelle_version>
sudo systemctl daemon-reload && sudo systemctl start docsearch-kafka
```

Producer et workers ont une logique de reconnexion automatique (retry_on_timeout, max_retries côté client Kafka) — aucune action requise sur les autres machines, l'ingestion reprend d'elle-même une fois Kafka de nouveau disponible.

## 6. Mise à jour de Tika

6 instances réparties sur 3 machines (tika-a et tika-b sur chacune) — un worker peut appeler n'importe laquelle. Mise à jour instance par instance, jamais les 2 d'une même machine simultanément, pour qu'il en reste toujours au moins une disponible sur chaque machine :

```bash
# Sur ingest-1 (puis ingest-2, puis ingest-3) :
# L'image apache/tika:<nouvelle_version> doit avoir été chargée au préalable (sudo podman load)
sudo nano /etc/containers/systemd/docsearch-tika-a.container   # puis daemon-reload
sudo systemctl daemon-reload && sudo systemctl restart docsearch-tika-a
# vérifier qu'elle répond avant de passer à la seconde :
curl -sf http://localhost:9998/tika
sudo systemctl restart docsearch-tika-b   # après avoir édité son unité de la même façon
```

## 7. Mise à jour de Redis et Nginx

### 7.1 Redis

Redis contient uniquement de la configuration à chaud (types de fichiers, filtres de chemin, paramètres opérationnels) — jamais de documents indexés. Un redémarrage bref est sans risque : les composants basculent automatiquement sur leurs valeurs par défaut codées en dur tant que Redis est indisponible (résilience déjà en place, voir README docsearch-ingestion).

```bash
# Sur frontend :
sudo systemctl restart docsearch-redis
```

### 7.2 Nginx

> **⚠️  Seul point d'entrée public — brève coupure visible**
> Nginx est l'unique porte d'entrée (ports 80/443) sur frontend, sans réplica — son redémarrage entraîne quelques secondes d'indisponibilité totale de l'interface, à réaliser de préférence en dehors des heures d'utilisation.

```bash
sudo systemctl restart docsearch-nginx
```

## 8. Mise à jour de la configuration partagée (/etc/docsearch)

La configuration vit dans /etc/docsearch/docsearch.env sur chaque machine (voir guide d'installation, §4). Les valeurs communes — IP du cluster ES, de Kafka, de Redis, index, réglages LDAP — doivent rester STRICTEMENT cohérentes entre les 8 machines. Toute divergence est une source de bugs difficiles à diagnostiquer (ex. un worker pointant vers une mauvaise IP Kafka).

- Modifier /etc/docsearch/docsearch.env sur UNE seule machine de référence (ex. frontend).
- Propager le fichier identique aux 7 autres machines :
```bash
for host in $ES_DATA1_IP $ES_DATA2_IP $ES_VOTING_IP $KAFKA_IP $INGEST1_IP $INGEST2_IP $INGEST3_IP; do
  scp /etc/docsearch/docsearch.env $USER@$host:/tmp/ && ssh $USER@$host 'sudo install -m 0600 -o root -g root /tmp/docsearch.env /etc/docsearch/'
done
```

- Redémarrer uniquement les services concernés par le changement (pas besoin de tout relancer pour une variable qui ne touche qu'un seul rôle).
> **⚠️  Les nouvelles variables ne s'ajoutent pas toutes seules**
> Le script d'installation des unités n'écrase jamais un /etc/docsearch/docsearch.env existant : une variable apparue dans une nouvelle version reste absente des machines déjà installées, où le code retombe alors sur sa valeur par défaut. Comparer le fichier en place avec le modèle du dépôt (quadlet/common/docsearch.env.example) après chaque mise à jour, et reporter à la main les lignes manquantes que l'on souhaite régler.
>
> Variables introduites récemment : `LOG_LEVEL` (niveau du journal de l'API, défaut INFO) et `SLOW_SEARCH_MS` (durée au-delà de laquelle une recherche est signalée dans le journal, défaut 2000 ms). Cette dernière doit rester alignée avec la macro Zabbix {$DOCSEARCH.RECHERCHE.MS.MAX}, sinon la supervision alerte sur des recherches dont le journal ne dit rien.

> **⚠️  ES_INDEX et ES_SEARCH_ALIAS ne migrent jamais les données existantes**
> Changer l'une de ces deux valeurs sur un cluster déjà en production démarre un index vide — l'index précédent (et ses documents) reste inchangé mais n'est plus interrogé. Prévoir une réindexation complète après tout changement de ce type (voir §8 du guide d'installation pour la procédure d'indexation).

## 9. Vérification post mise à jour

Après CHAQUE mise à jour, quel que soit le composant touché :

```bash
# Cluster Elasticsearch au vert, 3 nœuds
curl -s http://<ES_DATA1_IP>:9200/_cluster/health?pretty

# Nombre de documents inchangé (comparer à la valeur d'avant mise à jour)
curl -s "http://<ES_DATA1_IP>:9200/docsearch-all/_count"

# Topics Kafka accessibles
sudo podman exec docsearch-kafka kafka-topics --bootstrap-server localhost:9092 --list

# API en bonne santé — et surtout : la version attendue est-elle celle
# qui répond ? "version" est celle de DocSearch, "es_version" celle
# d'Elasticsearch. Un "commit" suffixé de "+modifie" signale une image
# construite depuis un dépôt non commité, qui n'a rien à faire ici.
curl -s http://<FRONTEND_IP>:8000/health

# Une recherche réelle (pas seulement /health) — en deux temps depuis la
# bascule du §3.3 : l'en-tête X-User n'identifie plus personne, il faut
# ouvrir une session et rejouer l'appel avec son cookie.
#
# 1. Ouvrir le bocal à cookies. Le mot de passe est saisi à l'invite, pour
#    qu'il n'atterrisse ni dans l'historique du shell ni dans « ps ».
read -rsp 'Mot de passe de <compte_test> : ' MDP && echo
curl -sk -c /tmp/ds-cookies -X POST -H 'Content-Type: application/json' \
     --data-binary @- https://<FRONTEND_IP>/auth/login <<JSON
{"identifiant": "<compte_test>", "mot_de_passe": "$MDP"}
JSON
unset MDP
#   → 200 et un JSON décrivant le compte. Un 401 vise les identifiants,
#     un 503 la paire de clés ou l'annuaire (§3.3), pas la recherche.
#   Un mot de passe contenant " ou \ casserait ce JSON : choisir un compte
#   de test qui n'en a pas plutôt que d'échapper à la main.

# 2. La recherche elle-même, avec le cookie de session
curl -sk -b /tmp/ds-cookies -X POST -H 'Content-Type: application/json' \
     -d '{"query":"test"}' https://<FRONTEND_IP>/search

# Le bocal contient le cookie de rafraîchissement, valable 7 jours par
# défaut (JWT_REFRESH_TOKEN_TTL_DAYS) : l'effacer.
rm -f /tmp/ds-cookies

# Logs des workers — reprise de la consommation sans erreurs en boucle
journalctl -u 'docsearch-worker-*' -n 50
```

Puis, dans l'interface : **Administration › État des composants › Versions déployées**. Les trois briques (Interface, API, Ingestion) doivent annoncer la version visée. Un avertissement s'y affiche tant qu'elles divergent — c'est le contrôle qui attrape le conteneur oublié, seul symptôme visible d'une mise à jour incomplète tant qu'aucune incompatibilité ne s'est manifestée.

Deux limites à connaître pour lire ce bloc correctement :

- La ligne « Ingestion » est relevée sur le **watcher**, qui ne tourne que sur ingest-1. Les workers d'ingest-2 et ingest-3 partagent la même image mais ne sont pas interrogés individuellement : pendant une mise à jour rolling (§3.1), cette ligne ne dit rien de leur avancement. S'en remettre à l'ordre des opérations et aux `journalctl` de chaque machine.
- Elle n'apparaît pas du tout tant qu'aucun battement de watcher récent n'a été reçu (moins de 120 s) — c'est alors un problème de watcher, que le bloc « État des composants » signale juste au-dessus.

## 10. Procédure de rollback

### 10.1 Code applicatif

```bash
cd ~/docsearch/docsearch-api   # ou docsearch-ingestion / docsearch-ui-vue
git log --oneline -5           # identifier le commit précédent stable
git checkout <commit_precedent>
# reconstruire sur la machine de préparation, puis transférer :
gunzip -c api.tar.gz | sudo podman load && sudo systemctl restart docsearch-api
```

### 10.2 Composants d'infrastructure (image de conteneur)

Revenir au tag d'image précédent dans l'unité concernée (/etc/containers/systemd/*.container), recharger systemd, puis relancer la même procédure de mise à jour rolling décrite pour ce composant (§4 à §7) — jamais de retour arrière brutal sur tous les nœuds ES simultanément.

> **⚠️  Elasticsearch : la rétrogradation d'un nœud déjà rejoint au cluster n'est pas garantie**
> Un nœud ES ayant rejoint un cluster avec une version plus récente peut avoir écrit des métadonnées ou des formats de segment incompatibles avec une version antérieure. Le retour en arrière fiable pour Elasticsearch est la restauration du snapshot pris au §2, pas un simple changement de tag d'image — c'est la raison principale de toujours sauvegarder avant une mise à jour ES.

### 10.3 Configuration (/etc/docsearch)

Conserver une copie de l'ancien docsearch.env hors de /etc (versionnée via Git, hors secrets) permet un rollback simple : récupérer la version précédente du fichier et répéter la procédure de propagation du §8.

## 11. Récapitulatif — fenêtre de maintenance par composant

| **Composant** | **Impact recherche** | **Impact ingestion** | **Fenêtre recommandée** |
|---|---|---|---|
| Workers / watcher (ingestion) | Aucun | Aucun (rolling par machine) | Aucune |
| API / UI (frontend) | Quelques secondes | Aucun | Faible trafic conseillé |
| Elasticsearch (rolling) | Aucun si vert entre nœuds | Aucun | Faible trafic conseillé |
| Kafka (broker unique) | Aucun | Pause pendant le redémarrage | Faible activité d'ingestion |
| Tika (rolling) | Aucun | Aucun (rolling par instance) | Aucune |
| Redis | Aucun (repli sur défauts) | Aucun (repli sur défauts) | Aucune |
| Nginx | Coupure totale brève | Aucun | Hors heures d'utilisation |
