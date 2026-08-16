# DocSearch — Architecture de production, 8 serveurs

*Debian 13 « trixie » · podman + systemd (Quadlet) · Elasticsearch 9.4.3*

**8 serveurs physiques** (i3-12100T · 16 Go RAM) · **2 × SSD 4 To + 6 × SSD 256 Go**,
stockage réparti par rôle · **cluster Elasticsearch à 3 nœuds** : 2 data + 1 arbitre (voting).

> **Document confidentiel — usage interne.** 8 juillet 2026.
> Converti du format Word le 2026-08-06 : le Markdown est désormais la
> source, il se relit et se compare dans Git comme le reste du dépôt.

## Sommaire

- 1. Vue d'ensemble
- 2. Les 8 serveurs et leurs rôles
- 3. Flux réseau et pare-feu
- 4. Prérequis avant installation
- 5. Installation commune (à répéter sur les 8 machines)
- 6. Installation spécifique par rôle
- 7. Ordre de démarrage et vérification
- 8. Lancer l'indexation initiale
- 9. Dépannage rapide
- 10. Fichiers de référence

## 1. Vue d'ensemble

Ce document décrit l'architecture de déploiement de DocSearch retenue pour le test de montée en charge à 4 millions de documents, ainsi que la procédure d'installation sur Debian 13 des 8 serveurs physiques qui la composent.

Matériel disponible :

- 6 machines Intel i3-12100T, 16 Go de RAM, SSD 256 Go
- 2 machines Intel i3-12100T, 16 Go de RAM, SSD 4 To
Les 8 machines partagent le même CPU/RAM (4 cœurs / 8 threads, 16 Go) — seule la capacité disque diffère. La répartition des rôles suit donc la nature de la charge de chaque composant, pas la puissance de la machine :

- Elasticsearch est sensible à la latence disque (fusions de segments, refresh) et bénéficie d'espace pour stocker des millions de documents → les 2 machines à 4 To.
- Apache Tika (extraction de contenu) est 100 % CPU-bound et sans état → réparti sur plusieurs petites machines, jamais colocalisé avec Elasticsearch (une rafale d'extraction ne doit pas voler du CPU à un nœud ES en pleine écriture).
- Kafka, point de passage de tous les documents à indexer, mérite d'être isolé pour ne pas subir le bruit d'autres services pendant une charge d'ingestion massive.
- Redis, l'API de recherche, l'interface web et Nginx (le seul point d'entrée public) sont regroupés pour isoler proprement le chemin de la recherche, mesuré séparément de celui de l'ingestion lors des tests de charge.
> **💡  Pourquoi un nœud Elasticsearch "voting only" ?**
> Avec seulement 2 machines de données ES, la panne de l'une des deux laisserait la survivante avec 1 voix sur 2 — pas de majorité, pas d'élection de master possible (split-brain). Un 3ᵉ nœud, éligible master mais sans données (rôle voting_only), résout ce problème avec une charge quasi nulle : c'est exactement le rôle du serveur es-voting.

## 2. Les 8 serveurs et leurs rôles

| **Machine** | **Rôle** | **Services (conteneurs)** | **Disque** |
|---|---|---|---|
| es-data-1 | Nœud Elasticsearch — données | Elasticsearch (master + data) | SSD 4 To |
| es-data-2 | Nœud Elasticsearch — données | Elasticsearch (master + data) | SSD 4 To |
| es-voting | Arbitre de quorum ES + supervision | Elasticsearch (voting_only) + Kibana | SSD 256 Go |
| kafka | File de travail de l'indexation | Kafka (KRaft, broker unique) | SSD 256 Go |
| frontend | Point d'entrée utilisateur | Redis + API FastAPI + UI + Nginx | SSD 256 Go |
| ingest-1 | Extraction de contenu + ingestion | 2× Tika, workers, watcher, indexer-init | SSD 256 Go |
| ingest-2 | Extraction de contenu + ingestion | 2× Tika, workers | SSD 256 Go |
| ingest-3 | Extraction de contenu + ingestion | 2× Tika, workers | SSD 256 Go |

### 2.1 Elasticsearch — es-data-1, es-data-2, es-voting

Avec number_of_replicas: 1 et seulement 2 nœuds de données, chaque nœud finit par stocker l'intégralité du jeu de données (miroir complet des shards de l'autre, pas une simple moitié) — les 4 To donnent une marge confortable même bien au-delà de 4 millions de documents. Heap JVM fixé à 7 Go sur chaque nœud de données (règle des 50 % de la RAM disponible, le reste servant de cache page OS, déterminant pour les performances de recherche).

### 2.2 Kafka — kafka

Broker unique en mode KRaft (sans Zookeeper), cohérent avec l'usage actuel de Kafka dans DocSearch : une simple file de travail pour paralléliser l'indexation, pas un système d'enregistrement durable. Un message perdu est simplement rattrapé au prochain scan complet.

> **⚠️  Point de défaillance unique — ingestion seulement**
> Si la machine kafka tombe, l'indexation de nouveaux documents s'arrête. La RECHERCHE continue de fonctionner normalement : elle ne dépend ni de Kafka ni des machines d'ingestion, seulement d'Elasticsearch.

### 2.3 Frontend — frontend

Seule machine exposée publiquement (ports 80/443 via Nginx). Redis, l'API FastAPI et l'interface web statique y sont colocalisés — ils communiquent entre eux sur un réseau Docker local à cette machine, aucun de ces trois composants n'a besoin d'être joignable depuis les autres serveurs, à l'exception de Redis (interrogé par les workers d'ingestion pour la configuration à chaud).

> **⚠️  ES_HOST ne pointe que sur es-data-1**
> Le client Elasticsearch utilisé par l'API ne fait pas de bascule automatique entre plusieurs hôtes à partir d'une simple variable d'environnement. Si es-data-1 tombe, l'API perd son point d'entrée même si le cluster ES reste opérationnel par ailleurs. Amélioration possible hors périmètre de ce document : liste de hosts côté client, ou répartiteur de charge TCP devant les 2 nœuds de données.

### 2.4 Ingestion — ingest-1, ingest-2, ingest-3

Chaque machine héberge 2 instances Tika et plusieurs réplicas du service worker (extraction + indexation), soit 6 instances Tika et 9 workers au total pour la configuration par défaut (3 workers/machine, ajustable après le pilote de dimensionnement). Un worker peut appeler n'importe laquelle des 6 instances Tika du cluster, ce qui répartit naturellement la charge entre les 3 machines.

watcher (surveillance temps réel) et indexer-init (scan complet à la demande) sont des services singletons : une seule instance suffit pour tout le cluster. Ils vivent sur ingest-1 uniquement, aux côtés de ses propres Tika/workers.

## 3. Flux réseau et pare-feu

Les 8 machines doivent se trouver sur un même LAN dédié à ce cluster (ou à défaut, isolé/pare-feuté des autres usages), en Gigabit minimum. Le trafic de réplication Elasticsearch et Kafka ↔ workers y transite réellement — contrairement à un déploiement de développement mono-hôte, où tout restait en boucle locale sur le réseau virtuel Docker.

| **Port(s)** | **Service** | **Sens du flux** |
|---|---|---|
| 9200, 9300 | Elasticsearch (HTTP + transport) | es-data-1/2, es-voting entre eux · frontend et ingest-* → es-data-1 |
| 9092, 9093 | Kafka (client + contrôleur KRaft) | ingest-* → kafka |
| 6379 | Redis | ingest-* → frontend |
| 9998, 9999 | Tika | ingest-* entre eux (les 3 machines s'appellent mutuellement) |
| 80, 443 | Nginx | Public → frontend |
| 5601 | Kibana | Poste d'administration → es-voting (accès à restreindre — pas de SSO devant Kibana) |

## 4. Prérequis avant installation

- 8 machines avec Debian 13 (« trixie ») fraîchement installé, accès root ou sudo
- 8 adresses IP statiques réservées sur le LAN dédié (voir tableau ci-dessous)
- Un partage réseau (CIFS ou NFS) contenant les documents sources, accessible depuis ingest-1, ingest-2, ingest-3 et frontend (ce dernier pour l'aperçu de document par l'API)
- Accès aux 5 dépôts Git DocSearch (docsearch-infra, docsearch-ingestion, docsearch-api, docsearch-ui-vue, docsearch-docs)

| **Machine** | **Variable (docsearch.env)** | **Adresse IP (exemple)** |
|---|---|---|
| es-data-1 | ES_DATA1_IP | 192.168.10.11 |
| es-data-2 | ES_DATA2_IP | 192.168.10.12 |
| es-voting | ES_VOTING_IP | 192.168.10.13 |
| kafka | KAFKA_IP | 192.168.10.14 |
| frontend | FRONTEND_IP | 192.168.10.15 |
| ingest-1 | INGEST1_IP | 192.168.10.16 |
| ingest-2 | INGEST2_IP | 192.168.10.17 |
| ingest-3 | INGEST3_IP | 192.168.10.18 |

## 5. Installation commune (à répéter sur les 8 machines)

### 5.1 Mise à jour du système et outils de base

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y curl git ca-certificates gnupg nfs-common cifs-utils chrony
```

### 5.2 Horloge (NTP via chrony)

Des horloges désynchronisées entre les 8 machines faussent les dates d'indexation (date_created/date_modified) et compliquent la corrélation des logs — chrony est installé et activé par défaut sur Debian 13 (4.6.1), vérifier simplement qu'il tourne :

```bash
sudo systemctl enable --now chrony
chronyc tracking
```

### 5.3 podman (moteur de conteneurs)

```bash
sudo apt-get install -y podman netavark aardvark-dns
# Debian 13 livre podman 5.4.2 : aucun backport nécessaire (il en fallait un
# sur Debian 12, restée en 4.3, sous le seuil de 4.4 qu'exige Quadlet).
# aardvark-dns est indispensable : sans lui, aucun conteneur ne résout le nom d'un autre
podman --version   # doit afficher 4.4 ou plus
```

### 5.4 Réglages noyau requis par Elasticsearch

Nécessaire strictement sur es-data-1, es-data-2 et es-voting — appliqué ici partout par simplicité, sans effet sur les autres rôles :

```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-docsearch.conf
```

> **⚠️  Désactiver le swap sur les 3 machines Elasticsearch**
> Elasticsearch utilise bootstrap.memory_lock=true (verrouillage du heap en RAM) — un swap actif dégrade fortement les performances et peut provoquer des pauses GC longues. Sur es-data-1, es-data-2 et es-voting : sudo swapoff -a, puis commenter la ligne swap dans /etc/fstab pour que ce soit permanent après redémarrage.

### 5.5 Pare-feu (nftables)

Exemple minimal avec nftables (adapter les ports selon le rôle de la machine, voir §3) :

```bash
sudo apt install -y nftables
sudo tee /etc/nftables.conf > /dev/null <<'EOF'
#!/usr/sbin/nft -f
flush ruleset
table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    ip saddr 192.168.10.0/24 tcp dport { 22,9200,9300,9092,9093,6379,9998,9999,80,443,5601 } accept
  }
}
EOF
sudo systemctl enable --now nftables
```

### 5.6 Clonage des dépôts

Cloner uniquement les dépôts requis par le rôle de la machine (voir §6) :

```bash
mkdir -p ~/docsearch && cd ~/docsearch
git clone <url>/docsearch-infra.git
# + docsearch-ingestion (ingest-*, frontend), docsearch-api et docsearch-ui-vue (frontend uniquement)
cd docsearch-infra
# Les images ne se construisent PAS ici : la production n'a pas d'accès Internet.
# Elles arrivent d'une machine de préparation (voir HOWTO-deploiement-hors-ligne.md).
```

## 6. Installation spécifique par rôle

### 6.1 es-data-1 et es-data-2

Monter le SSD 4 To sur /data/es (adapter selon le périphérique réel, ex. /dev/sdb) :

```bash
sudo mkfs.ext4 /dev/sdb
sudo mkdir -p /data/es
echo '/dev/sdb /data/es ext4 defaults 0 2' | sudo tee -a /etc/fstab
sudo mount -a
sudo chown 1000:1000 /data/es   # UID de l'utilisateur du conteneur Elasticsearch
```

Puis, depuis ~/docsearch/docsearch-infra :

```bash
# Sur es-data-1 :
sudo ./quadlet/install-units.sh es-data   # puis node.name=es01 dans /etc/docsearch/elasticsearch.env

# Sur es-data-2 :
sudo ./quadlet/install-units.sh es-data   # puis node.name=es02 dans /etc/docsearch/elasticsearch.env
```

### 6.2 es-voting

```bash
sudo ./quadlet/install-units.sh es-voting && sudo systemctl start docsearch.target
```

Vérifier que le cluster atteint 3 nœuds avant de poursuivre l'installation des autres machines :

```bash
curl -s http://<ES_DATA1_IP>:9200/_cluster/health?pretty
# "status": "green", "number_of_nodes": 3
```

### 6.3 kafka

```bash
sudo ./quadlet/install-units.sh kafka   # renseigner l'IP réelle dans /etc/docsearch/kafka.env
```

### 6.4 frontend

Monter le partage réseau des sources en lecture seule (exemple CIFS) :

```bash
sudo mkdir -p /data/docsearch-sources
echo '//<serveur>/partage /data/docsearch-sources cifs ro,uid=1000,gid=1000,_netdev 0 0' | sudo tee -a /etc/fstab
sudo mount -a
```

Générer (ou copier) le certificat SSL utilisé par Nginx, puis démarrer :

```bash
sudo ./quadlet/install-units.sh frontend && sudo mkdir -p /etc/docsearch/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/docsearch/nginx/certs/key.pem -out /etc/docsearch/nginx/certs/cert.pem \
  -subj '/CN=docsearch.local'
sudo ./quadlet/transfer-images.sh frontend   # images venues de la machine de préparation
```

Configurer l'authentification. Sans cette étape, l'application démarre mais personne ne peut se connecter : /auth/login répond 503 tant que la paire de clés qui signe les sessions n'existe pas.

```bash
sudo install -d -o 1000 -g 1000 -m 700 /etc/docsearch/jwt
sudo podman run --rm -v /etc/docsearch/jwt:/etc/docsearch/jwt:Z \
  localhost/docsearch/api:latest python scripts/generer-cles.py
# Reporter les 3 lignes JWT_* affichées dans /etc/docsearch/docsearch.env,
# avec API_ENV=production, COOKIE_SECURE=true, les paramètres LDAP_* et
# les deux groupes ACCESS_GROUP / ADMIN_GROUP.
# Compte de secours, à créer AVANT la première panne d'annuaire :
sudo podman exec -it docsearch-api python scripts/gerer-comptes-locaux.py \
  creer secours.admin --groupes docsearch-users,docsearch-admins
```

Deux points qui coûtent une matinée s'ils sont manqués. Le répertoire des clés est monté en LECTURE SEULE dans le service : la génération passe donc par un conteneur jetable, jamais par « podman exec » dans le conteneur qui tourne. Et « -o 1000 » donne ce répertoire à l'UID de l'utilisateur DANS le conteneur — appartenant à root, les clés seraient générées puis illisibles par le service.

Le compte de secours porte ses propres groupes, et c'est tout son intérêt : l'annuaire étant indisponible au moment où il sert, c'est la seule chose qui établira que son porteur a le droit d'entrer et d'administrer. Sans lui, une panne d'annuaire rend DocSearch totalement inaccessible, administration comprise.

### 6.5 ingest-1, ingest-2, ingest-3

Monter le même partage réseau des sources (lecture seule) que sur frontend, puis :

```bash
# ingest-1 uniquement : le watcher ET le worker des modules
# complémentaires sont des singletons — un seul exemplaire dans la grappe.
sudo ./quadlet/install-units.sh ingest --with-singletons
sudo ./quadlet/transfer-images.sh ingest

# ingest-2 et ingest-3 :
sudo ./quadlet/install-units.sh ingest && sudo ./quadlet/transfer-images.sh ingest
```

### 6.6 Modules complémentaires (facultatif)

Un module ne se clone pas : il arrive comme une archive, au même titre
qu'une image (voir
[HOWTO-deploiement-hors-ligne.md](../docsearch-infra/HOWTO-deploiement-hors-ligne.md)),
et s'installe sur la machine qui doit l'héberger — **ingest-1** pour un
module qui pousse des documents, **frontend** pour un module qui expose
des écrans.

```bash
sudo ./manage.sh plugin install /chemin/<module>-<version>.tar
sudo ./manage.sh plugin enable <module>
./manage.sh plugin list
```

Le réseau `docsearch-plugins`, sur lequel ces conteneurs sont isolés, est
créé par `install-units.sh` — rien à faire de plus. Voir
[HOWTO-creer-module-complementaire.md](../docsearch-infra/HOWTO-creer-module-complementaire.md)
pour en écrire un.

## 7. Ordre de démarrage et vérification

L'ordre compte : Kafka doit être opérationnel avant les workers/watcher, l'API a besoin de Redis, Nginx a besoin de l'API. Sur chaque machine, le démarrage se fait par « sudo systemctl start docsearch.target » (ou « sudo ./manage.sh start »), dans cet ordre :

- 1. es-data-1 et es-data-2 (en parallèle)
- 2. es-voting — puis vérifier le cluster à 3 nœuds (§6.2)
- 3. kafka
- 4. frontend
- 5. ingest-1 (avec le watcher)
- 6. ingest-2 et ingest-3

### 7.1 Vérifications de bout en bout

```bash
# Cluster Elasticsearch
curl -s http://<ES_DATA1_IP>:9200/_cluster/health?pretty

# Topics Kafka
sudo podman exec docsearch-kafka kafka-topics --bootstrap-server localhost:9092 --list

# Santé de l'API
curl -s http://<FRONTEND_IP>:8000/health

# Interface de recherche
curl -sk https://<FRONTEND_IP>/
#   → 302 vers /connexion : attendu, l'accès anonyme n'existe plus
```

## 8. Lancer l'indexation initiale

Depuis ingest-1 uniquement (seule machine où tourne le watcher) :

```bash
cd ~/docsearch/docsearch-infra
sudo ./manage.sh init
# (producer.py s'exécute dans un conteneur jetable sur l'image ingestion)
# Suivre l'avancement : ./manage.sh logs worker
```

Le scan publie les références de fichiers sur Kafka rapidement ; l'extraction Tika et l'indexation Elasticsearch se poursuivent ensuite en arrière-plan sur les workers des 3 machines d'ingestion.

## 9. Dépannage rapide

9.1 Cluster ES bloqué en jaune/rouge au démarrage

Normal tant que les 3 nœuds (es-data-1, es-data-2, es-voting) ne sont pas tous démarrés — cluster.initial_master_nodes liste les 3 et attend leur présence pour élire un master. Vérifier que les 3 conteneurs tournent et que le port 9300 est bien ouvert entre les 3 machines (§3).

9.2 Les workers ne consomment aucun message

Vérifier que KAFKA_NUM_PARTITIONS (16 par défaut) est bien ≥ au nombre total de workers actifs sur les 3 machines d'ingestion — sinon certains workers ne reçoivent jamais de partition.

9.3 vm.max_map_count revient à sa valeur par défaut après redémarrage

Vérifier que la ligne a bien été écrite dans /etc/sysctl.d/99-docsearch.conf (§5.4), pas seulement appliquée à chaud avec sysctl -w.

9.4 Erreur de connexion Kafka depuis un worker

KAFKA_ADVERTISED_LISTENERS doit annoncer l'IP réelle de la machine kafka (KAFKA_IP), jamais un nom de conteneur — contrairement au mono-hôte, les machines ne partagent aucun réseau de conteneurs et se joignent uniquement par IP.

## 10. Fichiers de référence

Les unités systemd et le README détaillé correspondant à ce document se trouvent dans le dépôt docsearch-infra :

- docsearch-infra/quadlet/install-units.sh   (installation des unités par rôle)
- docsearch-infra/quadlet/transfer-images.sh   (mise en place des images côté root)
- docsearch-infra/quadlet/common/   (cible docsearch.target, réseau, modèles de configuration)
- docsearch-infra/quadlet/roles/es-data/ · es-voting/ · kafka/
- docsearch-infra/quadlet/roles/frontend/ · ingest/
- docsearch-infra/quadlet/README.md   (installation, dépannage, prérequis podman)
- docsearch-infra/HOWTO-deploiement-hors-ligne.md   (transfert des images)
- docsearch-infra/HOWTO-commandes-utiles.md   (exploitation au quotidien)
> **💡  manage.sh fonctionne sur les 8 machines**
> Le script manage.sh à la racine de docsearch-infra pilote les unités systemd de la machine où il est lancé, quel que soit son rôle : start/stop/restart, status, journaux, et les commandes d'administration (init, add-file-source, set-config…) qui s'exécutent dans un conteneur jetable. Il exige sudo pour tout ce qui touche aux unités, au réseau ou aux images.
