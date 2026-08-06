# DocSearch — Guide d'installation, environnement de développement

*VirtualBox · Ubuntu 24.04 LTS · podman + systemd (Quadlet)*

**Ubuntu 24.04 LTS** en VM invitée · **podman 4.9 + Quadlet** ·
**Elasticsearch 9.4.3 · Tika 3.3.1.0**

> **Document confidentiel — usage interne.** 4 juillet 2026.
> Converti du format Word le 2026-08-06 : le Markdown est désormais la
> source, il se relit et se compare dans Git comme le reste du dépôt.

## 1. Prérequis

### 1.1 Matériel requis (machine hôte)

L'environnement de développement tourne dans une VM VirtualBox avec les ressources minimales suivantes :

| **Ressource** | **Minimum** | **Recommandé** |
|---|---|---|
| **RAM hôte** | **16 GB** | **32 GB** |
| **RAM VM** | **8 GB** | **16 GB** |
| **CPU** | **4 vCPU** | **8 vCPU** |
| **Disque VM** | **40 GB SSD** | **80 GB SSD** |
| **OS hôte** | **Windows 10/11, macOS 12+, Linux** | **Windows 11 Pro ou macOS 13+** |

> **⚠️  Elasticsearch 9.x — vm.max_map_count**
> Elasticsearch 9.x requiert vm.max_map_count ≥ 262144 sur le système Linux de la VM. Le script d'installation l'applique automatiquement, mais il faut que la VM dispose d'au moins 8 GB de RAM pour que le cluster ES en nœud unique reste stable.

### 1.2 Logiciels à installer sur la machine hôte

- VirtualBox 7.x — https://www.virtualbox.org/wiki/Downloads
- Extension Pack VirtualBox (USB 3, clipboard bidirectionnel)
- Ubuntu 24.04 LTS ISO — https://ubuntu.com/download/desktop
- Git (pour cloner les dépôts DocSearch)
**📦 Architecture en plusieurs dépôts Git**

DocSearch est découpé en 5 dépôts indépendants : docsearch-infra (orchestration, à cloner en premier), docsearch-ingestion (indexation), docsearch-api (recherche), docsearch-ui-vue (interface web Vue 3 + DSFR) et docsearch-docs (documents commerciaux). Ils doivent être clonés côte à côte dans un même dossier parent — voir section 5.

> **💡 Alternative à l'installation manuelle**
> Si vous disposez de Vagrant, le fichier Vagrantfile fourni en annexe provisionne automatiquement la VM Ubuntu avec podman et clone l'ensemble des dépôts DocSearch en une seule commande : vagrant up

## 2. Création de la VM VirtualBox

| **1** | **Créer une nouvelle VM** Machine → Nouvelle → Type : Linux · Version : Ubuntu 24.04 LTS (64-bit) |
|---|---|

### 2.1 Paramètres de la VM

**Onglet Général**

- Nom : DocSearch-Dev
- Type : Linux — Version : Ubuntu (64-bit)
**Onglet Système**

- Mémoire de base : 8192 MB (8 GB minimum)
- Processeurs : 4 vCPU (cocher « Activer PAE/NX »)
- Ordre d'amorçage : Disque optique → Disque dur
**Onglet Affichage**

- Mémoire vidéo : 128 MB
- Contrôleur graphique : VMSVGA
**Onglet Stockage**

- Contrôleur SATA → Ajouter un disque dur → Créer
- Type : VDI · Dynamiquement alloué · Taille : 80 GB
- Contrôleur IDE → Ajouter un lecteur optique → Choisir l'ISO Ubuntu 24.04
**Onglet Réseau**

- Carte 1 : NAT (accès internet depuis la VM)
- Carte 2 : Réseau hôte uniquement (Host-Only) → pour accéder aux services depuis l'hôte
> **💡 Réseau Host-Only — accès aux interfaces DocSearch**
> La carte Host-Only permet d'accéder depuis votre navigateur hôte aux interfaces DocSearch : http://192.168.56.101 (Recherche), http://192.168.56.101:5601 (Kibana), http://192.168.56.101:8000 (API). L'IP 192.168.56.101 est l'adresse par défaut du réseau host-only VirtualBox.

### 2.2 Optimisations VirtualBox

- Activer les additions invité (améliore les performances et active le presse-papiers partagé)
- Presse-papiers partagé : Bidirectionnel (Appareils → Presse-papiers partagé)
- Glisser-déposer : Bidirectionnel
- Activer l'accélération 3D si disponible

## 3. Installation d'Ubuntu 24.04 LTS

| **2** | **Démarrer la VM et lancer l'installation** Sélectionner l'ISO Ubuntu 24.04 — suivre l'assistant d'installation |
|---|---|

### 3.1 Options d'installation recommandées

- Langue : Français
- Disposition clavier : French (AZERTY) ou selon votre préférence
- Type d'installation : Installation minimale (suffisant pour podman)
- Partitionnement : Utiliser tout le disque (pas de chiffrement en dev)
- Nom de la machine : docsearch-dev
- Nom d'utilisateur : devuser (ou votre choix)
- Mot de passe : choisir un mot de passe fort
> **⚠️  Installation minimale recommandée**
> Choisir « Installation minimale » (sans LibreOffice ni applications bureautiques) économise 2 GB de disque. podman et les dépendances DocSearch seront installés ensuite.

### 3.2 Post-installation — Additions invité VirtualBox

Une fois Ubuntu démarré, installer les Additions invité pour activer le presse-papiers partagé et le redimensionnement automatique de l'écran :

```bash
# Mise à jour du système
sudo apt-get update && sudo apt-get upgrade -y

# Dépendances pour les Additions invité
sudo apt-get install -y build-essential dkms linux-headers-$(uname -r)

# Dans VirtualBox : Appareils → Insérer l'image des Additions invité
# Puis dans le terminal Ubuntu :
sudo mount /dev/cdrom /mnt
sudo /mnt/VBoxLinuxAdditions.run

# Redémarrer la VM
sudo reboot
```

## 4. Installation de podman

| **3** | **Installer podman et ses dépendances réseau** Paquets officiels Ubuntu 24.04 — podman 4.9, au-delà du minimum exigé par Quadlet (4.4) |
|---|---|

### 4.1 Désinstaller Docker s'il est présent

```bash
# Docker n'est plus utilisé ; le laisser installé peut créer des conflits de sous-réseau
for pkg in docker-ce docker-ce-cli containerd.io docker-compose-plugin docker.io docker-compose; do
    sudo apt-get remove -y $pkg 2>/dev/null || true
done
```

### 4.2 Installer podman

```bash
# podman, son moteur réseau (netavark) et son serveur DNS interne (aardvark-dns)
sudo apt-get update && sudo apt-get install -y podman netavark aardvark-dns

# aardvark-dns est INDISPENSABLE : sans lui, aucun conteneur ne résout le nom
# d'un autre et toute la pile tombe en boucle de redémarrage.
```

### 4.3 Vérifier l'installation

```bash
podman --version
# → podman version 4.9.x (4.4 minimum pour Quadlet)

# Le générateur Quadlet doit être présent :
ls /usr/libexec/podman/quadlet
```

### 4.4 Mode rootful : podman s'utilise avec sudo

```bash
# Aucun groupe à rejoindre, contrairement à Docker : les unités systemd
# tournent en root, et le magasin d'images de root est DISTINCT de celui
# de votre utilisateur. Une image construite sans sudo est invisible pour
# les unités — c'est le piège le plus courant.

# Vérification
sudo podman run --rm docker.io/library/hello-world
```

### 4.5 Paramètre vm.max_map_count (requis par Elasticsearch)

```bash
# Appliquer immédiatement
sudo sysctl -w vm.max_map_count=262144

# Rendre permanent au redémarrage
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf

# Vérification
sysctl vm.max_map_count
# → vm.max_map_count = 262144
```

## 5. Installation de DocSearch

| **4** | **Cloner les dépôts et configurer l'environnement** 5 dépôts clonés côte à côte + configuration dans /etc/docsearch |
|---|---|

### 5.1 Installer les dépendances système

```bash
sudo apt-get install -y \
    git \
    curl \
    gettext-base
```

### 5.2 Cloner les dépôts DocSearch

Les 5 dépôts doivent être clonés côte à côte dans un même dossier parent — docsearch-infra référence les autres par chemin relatif (../docsearch-ingestion, etc.) :

```bash
mkdir ~/docsearch && cd ~/docsearch

git clone https://github.com/votre-organisation/docsearch-infra.git
git clone https://github.com/votre-organisation/docsearch-ingestion.git
git clone https://github.com/votre-organisation/docsearch-api.git
git clone https://github.com/votre-organisation/docsearch-ui-vue.git
git clone https://github.com/votre-organisation/docsearch-docs.git

# Vérifier la structure obtenue
ls -la
# docsearch-infra/  docsearch-ingestion/  docsearch-api/
# docsearch-ui-vue/     docsearch-docs/
```

**📁 Convention de dossiers**

Tous les dépôts doivent rester au même niveau : « manage.sh build » construit les images depuis des chemins relatifs (../docsearch-api, ../docsearch-ingestion, ../docsearch-ui-vue).

### 5.3 Construire les images et installer les unités

```bash
cd ~/docsearch/docsearch-infra

# Construire les 3 images applicatives (nécessite un accès Internet)
sudo ./manage.sh build all

# Installer les unités systemd de la pile mono-hôte
sudo ./quadlet/install-units.sh dev
```

Adapter ensuite les variables dans /etc/docsearch/docsearch.env :

```bash
# ── Chemin des documents sur l'hôte ─────────────────
SOURCES_HOST_PATH=/documents

# ⚠️ Ce chemin est AUSSI écrit en dur dans les unités (Volume=/documents:/sources:ro)
# Les deux doivent correspondre — Quadlet ne substitue aucune variable.
SOURCES_MOUNT=/sources

# ── Authentification (VM de développement) ──────────
API_ENV=development       # 'production' verrouillerait les 3 lignes suivantes
DEV_USER=devuser          # identité par défaut de toute requête

# ── LDAP (désactivé en dev) ──────────────────────────
LDAP_ENABLED=false

# ⚠️ OBLIGATOIRE ici : sans annuaire, aucun groupe ne peut être établi,
# et le contrôle d'accès refuse TOUT — y compris avec DEV_USER renseigné.
# Chaque page répondrait 403 « Vérification des groupes impossible ».
ACCESS_AUTH_DISABLED=true
ADMIN_AUTH_DISABLED=true

# ── Ressources ES réduites pour la VM ────────────────
ES_JAVA_OPTS=-Xms1g -Xmx1g

# ── Watcher (surveillance de dossier) ────────────────
# Obligatoire si /documents est un montage réseau (CIFS/NFS/SMB) :
# inotify ne fonctionne pas sur ces montages, le watcher
# utilise le mode polling à la place.
WATCHER_POLL_INTERVAL=10
```

> **⚠️  Trouver son UID avant de construire les images**
> Exécuter id -u dans la VM. Si le résultat n'est pas 1000, reconstruire les images avec APP_UID=$(id -u) ./manage.sh build all — l'utilisateur du conteneur doit correspondre au propriétaire de /documents, sinon les conteneurs ne peuvent pas lire les fichiers.

Ces deux dernières lignes ne sont pas de la commodité : depuis la refonte
de l'authentification, l'identité vient d'un jeton signé et les droits sont
résolus par l'annuaire. Une VM sans annuaire n'a aucun moyen d'établir
qu'un utilisateur appartient à `docsearch-users` — le contrôle refuse donc
par défaut, ce qui est le bon comportement en production et rend la VM de
démonstration inutilisable. Les deux contournements lèvent ce seul
contrôle ; ils sont journalisés à chaque démarrage, et `API_ENV=production`
les rendrait fatals.

Pour exercer la **vraie** page de connexion sur cette VM plutôt que de la
contourner, deux possibilités : brancher un annuaire de test
(`~/ldap-test-stack`), ou créer un compte de secours local, qui porte ses
propres groupes et ne dépend donc d'aucun annuaire :

```bash
# Générer d'abord les clés de signature des sessions
sudo install -d -o 1000 -g 1000 -m 700 /etc/docsearch/jwt
sudo podman run --rm -v /etc/docsearch/jwt:/etc/docsearch/jwt:Z \
     localhost/docsearch/api:latest python scripts/generer-cles.py
# reporter les 3 lignes JWT_* dans /etc/docsearch/docsearch.env

sudo podman exec -it docsearch-api python scripts/gerer-comptes-locaux.py \
     creer demo.admin --groupes docsearch-users,docsearch-admins
```

Retirer alors `ACCESS_AUTH_DISABLED`, `ADMIN_AUTH_DISABLED` et `DEV_USER`,
et redémarrer l'API : l'application redirige vers `/connexion`.

### 5.4 Créer le dossier de documents de test

```bash
# Créer le dossier source des documents
sudo mkdir -p /documents
sudo chown $(id -u):$(id -g) /documents
chmod 755 /documents

# Copier quelques documents de test
cp /chemin/vers/documents/*.pdf /documents/
```

**🧪 Générer un jeu de test réaliste**

Le dépôt docsearch-dataset-generator (optionnel) génère des arborescences de dossiers et des documents PDF/DOCX/TXT avec métadonnées aléatoires (auteur, dates) à partir d'un CSV source — utile pour tester l'indexation et le filtrage par ACL avant de brancher de vrais documents.

## 6. Lancement du stack DocSearch

| **5** | **Démarrer les services (systemd)** Les unités installées déterminent ce qui démarre — il n'y a plus de profil à choisir |
|---|---|

### 6.1 Rendre les scripts exécutables

```bash
cd ~/docsearch/docsearch-infra
chmod +x manage.sh quadlet/install-units.sh quadlet/transfer-images.sh
```

### 6.2 Démarrer la pile

```bash
# Démarre docsearch.target, donc toutes les unités de la machine
sudo ./manage.sh start

# Suivre les logs en temps réel
journalctl -u 'docsearch-*' -f

# Attendre que tout soit actif (2-3 minutes, Elasticsearch est le plus lent)
./manage.sh status
```

En mode développement, les services démarrés sont :

- es01-dev (Elasticsearch 9.4.3 — nœud unique, 1 Go RAM)
- kibana (tableau de bord ES)
- tika1 à tika4 (Apache Tika 3.3.1.0)
- kafka (8.3, mode KRaft — sans Zookeeper)
- redis
- worker ×1, watcher (construits depuis docsearch-ingestion)
- api (construite depuis docsearch-api, port 8000)
- ui-vue (construite depuis docsearch-ui-vue, port 8080)
> **💡 Kafka 8.3 en mode KRaft**
> Depuis la version 8.3, Confluent Platform (Kafka 4.3) fonctionne sans Zookeeper : le coordinateur de cluster est intégré directement dans les brokers Kafka. Un service en moins à surveiller, un healthcheck en moins à déboguer.

### 6.3 Vérifier l'état des services

```bash
# État global
sudo ./manage.sh status

# Vérification manuelle Elasticsearch
curl http://localhost:9200/_cluster/health?pretty
# → { "status": "green" ou "yellow" (normal en nœud unique) }

# Vérification Tika
curl http://localhost:9998/tika
# → This is Tika Server (Apache Tika 3.3.1)

# Vérification API
curl http://localhost:8000/health
# → { "status": "ok", "es_version": "9.4.3", "acl_enabled": true }

# Vérification interface web
curl -I http://localhost:8080
# → HTTP/1.1 200 OK
```

## 7. Indexation initiale des documents

| **6** | **Lancer l'indexation initiale** Indexe les documents de /documents avec extraction des ACL POSIX |
|---|---|

### 7.1 Lancer l'indexation

```bash
# Indexation initiale — publie les fichiers sur Kafka
sudo ./manage.sh init

# Suivre la progression en temps réel
./manage.sh logs worker
```

### 7.2 Vérifier les documents indexés

```bash
# Nombre de documents indexés
curl http://localhost:9200/documents/_count?pretty

# Vérifier qu'un document a bien ses ACL
curl http://localhost:9200/documents/_search?pretty \
     -H 'Content-Type: application/json' \
     -d '{"query":{"match_all":{}},"_source":["filename","acl"],"size":3}'
```

```bash
Le résultat doit contenir le champ acl avec owner, group, users, groups et public pour chaque document.
```

### 7.3 Activer la surveillance en temps réel

```bash
# Le watcher démarre automatiquement avec le stack
journalctl -u docsearch-watcher -n 20
# → 👁️  Surveillance démarrée : /documents
#    (mode polling toutes les 10s — compatible CIFS/NFS)

# Tester : ajouter un fichier dans le dossier
cp test.pdf /documents/
journalctl -u docsearch-watcher -f

# Tester la suppression
rm /documents/test.pdf
# → 🗑️  Supprimé de l'index : /documents/test.pdf
```

**🌐 Montage réseau (CIFS/NFS/SMB)**

Si /documents est un partage réseau, la détection se fait par polling (délai de 0 à WATCHER_POLL_INTERVAL secondes) et non instantanément : inotify ne reçoit aucun événement sur ce type de montage. Réduire WATCHER_POLL_INTERVAL dans .env pour une détection plus rapide.

## 8. Accès aux interfaces

| **7** | **Accéder aux interfaces depuis le navigateur** Depuis la VM ou depuis l'hôte via le réseau Host-Only |
|---|---|

| **Interface** | **URL (depuis la VM)** | **URL (depuis l'hôte Host-Only)** |
|---|---|---|
| **Moteur de recherche (UI)** | **http://localhost:8080** | **http://192.168.56.101:8080** |
| **Assistant IA (option RAG)** | **http://localhost:8080/chat.html** | **http://192.168.56.101:8080/chat.html** |
| **API Swagger** | **http://localhost:8000/docs** | **http://192.168.56.101:8000/docs** |
| **Kibana (ES)** | **http://localhost:5601** | **http://192.168.56.101:5601** |
| **Métriques indexation** | **http://localhost:8000/metrics** | **http://192.168.56.101:8000/metrics** |

> **💡 Accès depuis l'hôte — configuration réseau Host-Only**
> Si le réseau Host-Only n'est pas configuré, aller dans VirtualBox → Fichier → Gestionnaire de réseau hôte → Créer → vboxnet0 avec IP 192.168.56.1/24. L'IP de la VM sera automatiquement 192.168.56.101 (visible avec : ip addr show enp0s8 dans la VM).

**🔀 UI et API sur des ports séparés en développement**

Sur cette VM mono-hôte, l'interface (port 8080) et l'API (port 8000) tournent sans reverse proxy, chacune dans son conteneur. En production, la machine frontend porte en plus une unité Nginx qui unifie l'accès sur le port 443 : l'UI est servie sur "/" et l'API sur "/search", "/document", etc. Voir docsearch-infra/nginx/nginx.conf.

## 9. Dépannage courant

### 9.1 Elasticsearch ne démarre pas — manque de mémoire

```bash
# Symptôme : docsearch-es01 redémarre en boucle (OOM)
journalctl -u docsearch-es01 -n 20

# Solution 1 : augmenter la RAM de la VM (VirtualBox → Système → 12 Go)

# Solution 2 : réduire la JVM ES dans /etc/docsearch/elasticsearch.env
ES_JAVA_OPTS=-Xms512m -Xmx512m
sudo systemctl restart docsearch-es01
```

### 9.2 Erreur "cluster.initial_master_nodes is not allowed"

```bash
# Symptôme : ES refuse de démarrer avec cette erreur en mode dev
# Cause : cluster.initial_master_nodes et discovery.type=single-node
# sont mutuellement exclusifs en ES 9.x

# Solution : l'unité docsearch-es01.container de la pile mono-hôte
# utilise discovery.type=single-node SANS cluster.initial_master_nodes.
# Les unités de production (rôle es-data) font l'inverse.
sudo ./manage.sh start        # → unités installées par install-units.sh dev
sudo ./quadlet/install-units.sh es-data   # → cluster 3 nœuds, sur serveur dédié
```

### 9.3 Erreur vm.max_map_count

```bash
# Symptôme : « max virtual memory areas vm.max_map_count [65530] is too low »
sudo sysctl -w vm.max_map_count=262144
sudo systemctl restart docsearch-es01
```

### 9.4 "Permission denied" sur /documents

```bash
# Symptôme : ls: cannot open directory '/documents': Permission denied
# dans un conteneur (worker, watcher, api)

# Trouver l'UID propriétaire réel de /documents
id -u

# Reconstruire les images avec cet UID (ARG APP_UID des Dockerfiles)
APP_UID=$(id -u) sudo -E ./manage.sh build all

# Puis redémarrer les unités concernées
sudo systemctl restart docsearch.target
```

### 9.5 Le watcher ne détecte rien

```bash
# Vérifier le mode de surveillance dans les logs
journalctl -u docsearch-watcher -n 5
# → doit afficher "mode polling" et non une erreur inotify

# Sur un montage CIFS/NFS, le délai de détection est normal :
# 0 à WATCHER_POLL_INTERVAL secondes (10s par défaut)

# Vérifier les ACL indexées après ajout d'un fichier
sudo podman exec docsearch-watcher python3 -c \
  "from acl_extractor import extract_acl; print(extract_acl('/documents/test.pdf'))"
```

### 9.6 Erreur "ModuleNotFoundError: kafka.vendor.six.moves"

```bash
# Cause : kafka-python 2.0.2 est incompatible avec Python 3.12
# Déjà corrigé dans requirements.txt (kafka-python-ng==2.2.3)
# Si l'erreur persiste, reconstruire sans cache :
APP_UID=$(id -u) sudo -E ./manage.sh build ingestion && sudo systemctl restart docsearch.target
```

### 9.7 Commandes de gestion utiles

```bash
# Voir l'état de tous les services
./manage.sh status

# Logs d'un service spécifique
./manage.sh logs api
./manage.sh logs worker
./manage.sh logs es01

# Reconstruire après modification d'un dépôt (une image par dépôt)
./manage.sh build api        && sudo systemctl restart docsearch-api docsearch-alert-worker
./manage.sh build ingestion  && sudo systemctl restart 'docsearch-worker-*' docsearch-watcher
./manage.sh build ui         && sudo systemctl restart docsearch-ui-vue

# Arrêter proprement
sudo ./manage.sh stop

# Réinitialiser complètement (supprime les données)
sudo ./manage.sh reset
```

## Annexe — Vagrantfile (provisioning automatique)

Alternative à l'installation manuelle : ce Vagrantfile provisionne automatiquement la VM Ubuntu avec podman, clone les 5 dépôts DocSearch et applique le paramètre vm.max_map_count.

```bash
# Vagrantfile — DocSearch Dev VM
Vagrant.configure("2") do |config|
  config.vm.box      = "ubuntu/noble64"   # Ubuntu 24.04 LTS
  config.vm.hostname = "docsearch-dev"

  # Réseau host-only
  config.vm.network "private_network", ip: "192.168.56.101"

  # Ressources VM
  config.vm.provider "virtualbox" do |vb|
    vb.name   = "DocSearch-Dev"
    vb.memory = 8192
    vb.cpus   = 4
  end

  # Dossier partagé (documents sources)
  config.vm.synced_folder "./documents", "/documents",
    owner: "vagrant", group: "vagrant"

  # Provisioning
  config.vm.provision "shell", inline: <<-SHELL
    apt-get update -qq

    # vm.max_map_count pour Elasticsearch
    sysctl -w vm.max_map_count=262144
    echo "vm.max_map_count=262144" >> /etc/sysctl.conf

    # podman (Ubuntu 24.04 fournit 4.9, suffisant pour Quadlet)
    apt-get update && apt-get install -y podman netavark aardvark-dns

    # Cloner les 5 dépôts DocSearch côte à côte
    ORG="https://github.com/votre-organisation"
    sudo -u vagrant mkdir -p /home/vagrant/docsearch
    cd /home/vagrant/docsearch
    for repo in infra ingestion api ui docs; do
      sudo -u vagrant git clone $ORG/docsearch-$repo.git
    done

    cd docsearch-infra
    sudo -u vagrant ./manage.sh build all
    ./quadlet/install-units.sh dev
    sed -i "s|DEV_USER=.*|DEV_USER=vagrant|" /etc/docsearch/docsearch.env
    sed -i "s|ES_JAVA_OPTS=.*|ES_JAVA_OPTS=-Xms1g -Xmx1g|" /etc/docsearch/elasticsearch.env
    sed -i "s|SOURCES_HOST_PATH=.*|SOURCES_HOST_PATH=/documents|" /etc/docsearch/docsearch.env

    chmod +x manage.sh quadlet/install-units.sh
    echo "✅ DocSearch prêt — lancer : sudo systemctl start docsearch.target"
  SHELL
end
```

**🚀 Lancement avec Vagrant**

Une fois le Vagrantfile configuré avec l'URL de votre organisation GitHub : vagrant up (15-20 min la première fois) puis vagrant ssh pour entrer dans la VM. DocSearch se lance ensuite avec : cd docsearch/docsearch-infra && ./manage.sh start && ./manage.sh init
