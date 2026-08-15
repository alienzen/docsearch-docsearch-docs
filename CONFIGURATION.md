# Valeurs par défaut de la configuration DocSearch

État au 2026-08-15. Ce document recense les valeurs par défaut **du code**, pas
celles d'une installation donnée : dès qu'un réglage a été modifié depuis le
panneau d'administration, c'est la valeur stockée dans Redis qui s'applique et
ce qui suit ne sert plus que de repli.

## Les trois niveaux de configuration

| Niveau | Support | Modifiable à chaud | Où c'est écrit |
|---|---|---|---|
| Variables d'environnement | fichier `.env` monté par l'unité Quadlet | non, redémarrage requis | `quadlet/common/docsearch.env.example` |
| Réglages à chaud | clés Redis `docsearch:config:*` | oui, panneau d'administration | `runtime_config.py`, `ui_config.py`, `engagement_config.py` |
| Configuration par source | clés Redis suffixées par le nom de source | oui, panneau d'administration | `filetype_config.py`, `path_filter.py`, `file_sources_config.py` |

Les réglages à chaud reprennent une variable d'environnement comme valeur de
départ. Une fois modifiés, ils vivent dans Redis ; la variable d'environnement
ne sert plus que si Redis est injoignable.

---

## 1. Réglages opérationnels — `runtime_config.py`

Clé Redis `docsearch:config:runtime`. Fichier dupliqué entre `docsearch-api` et
`docsearch-ingestion` : la clé Redis et la logique sont identiques, mais chaque
dépôt ne déclare que les paramètres dont il est propriétaire. `set_param()`
refuse une clé absente du `DEFAULT_RUNTIME` local.

| Paramètre | Défaut | Variable d'environnement | Déclaré côté |
|---|---|---|---|
| `archive_max_files` | `5000` | `ARCHIVE_MAX_FILES` | API + ingestion |
| `archive_max_total_size_mb` | `1000` | `ARCHIVE_MAX_TOTAL_SIZE_MB` | API + ingestion |
| `archive_max_depth` | `1` | `ARCHIVE_MAX_DEPTH` | API + ingestion |
| `worker_batch_size` | `200` | `WORKER_BATCH_SIZE` | API + ingestion |
| `worker_flush_interval` | `10` s | `WORKER_FLUSH_INTERVAL` | API + ingestion |
| `watcher_poll_interval` | `10` s | `WATCHER_POLL_INTERVAL` | API + ingestion |
| `ocr_languages` | `"fra"` | `OCR_LANGUAGES` | API + ingestion |
| `ocr_strategy` | `"auto"` | `OCR_STRATEGY` | API + ingestion |
| `search_boost_filename` | `6.0` | `SEARCH_BOOST_FILENAME` | API seule |
| `search_boost_title` | `4.0` | `SEARCH_BOOST_TITLE` | API seule |
| `search_boost_keywords` | `2.0` | `SEARCH_BOOST_KEYWORDS` | API seule |
| `sso_kerberos_enabled` | `"false"` | `SSO_KERBEROS_ENABLED` | API seule |
| `retention_search_logs_days` | `365` | `RETENTION_SEARCH_LOGS_DAYS` | API seule |
| `retention_login_events_days` | `365` | `RETENTION_LOGIN_EVENTS_DAYS` | API seule |
| `retention_audit_log_days` | `1095` | `RETENTION_AUDIT_LOG_DAYS` | API seule |
| `retention_nps_days` | `730` | `RETENTION_NPS_DAYS` | API seule |
| `retention_suggestions_days` | `730` | `RETENTION_SUGGESTIONS_DAYS` | API seule |

Points d'attention :

- **Poids de pertinence** : ce sont des multiplicateurs du score BM25 du champ,
  pas des pourcentages. `content` et `author` valent 1 et ne sont pas réglables :
  ce sont les références auxquelles les autres se comparent. Bornes `0.1` à
  `100.0` (`BOOST_MIN` / `BOOST_MAX`), hors bornes `set_param()` refuse.
- **Types** : les poids sont déclarés en `float` pour que 2.5 soit saisissable
  (`set_param()` coerce via `type(DEFAULT_RUNTIME[clé])`). Les réglages OCR et
  SSO sont des **chaînes** et non des booléens : `bool("false")` vaut `True` en
  Python.
- **Rétention** : `0` = conservation illimitée. Les défauts ne sont pas
  uniformes à dessein — douze mois pour comparer d'une année sur l'autre, deux
  ans pour une tendance de satisfaction, trois ans pour le journal d'audit, qui
  se garde plus longtemps que ce qu'il trace.
- Certains réglages exigent une action côté appelant pour être vraiment pris en
  compte (le watcher doit redémarrer son observateur si `watcher_poll_interval`
  change, un consumer Kafka doit être recréé).

## 2. Bascules d'interface — `ui_config.py`

Clé Redis `docsearch:config:ui`. Propre à `docsearch-api`, aucune copie côté
ingestion.

### Règle des défauts

Un flag qui **masque** une fonctionnalité déjà présente démarre à `True` ; un
flag qui en **ajoute** une sur l'écran de tous les utilisateurs démarre à
`False` et s'allume à la demande d'un administrateur.

**Sept bascules dérogent à cette règle depuis le 2026-08-15** : `chat_enabled`,
`admin_links_enabled`, `export_enabled`, `alerts_enabled`, `sort_enabled`,
`score_enabled` et `acl_visible_enabled` ont été passées à `False` sur demande
explicite, alors qu'elles masquent des fonctionnalités existantes. Ce n'est pas
une dérive : ne les « corrigez » pas vers `True` par souci d'uniformité. La
règle continue de s'appliquer aux flags à venir.

### Fonctionnalités

| Bascule | Défaut | Effet |
|---|---|---|
| `chat_enabled` | `False` | lien « Assistant IA » dans l'en-tête |
| `admin_links_enabled` | `False` | liens « Administration » / « Statistiques » — combiné en ET avec `/is-admin` |
| `export_enabled` | `False` | boutons d'export XLSX/DOCX ; `POST /search/export` refuse aussi côté API |
| `alerts_enabled` | `False` | alertes sur recherches sauvegardées ; routes `/alerts*` en 403 si désactivé |
| `sort_enabled` | `False` | sélecteur « Trier par » ; désactivé, tri par pertinence |
| `score_enabled` | `False` | badge de pourcentage de pertinence sur les cartes |
| `acl_visible_enabled` | `False` | section « Droits d'accès » visible des non-administrateurs |
| `help_enabled` | `True` | lien « ❓ Aide » + raccourci `?` ; n'empêche pas l'accès direct à `/help.html` |
| `collections_enabled` | `True` | collections personnelles ; désactivé, toutes les routes `/collections` en 403 |
| `custom_keywords_enabled` | `True` | mots-clés personnalisés ; désactivé, `POST`/`DELETE /document/{id}/keywords` en 403 |
| `footer_enabled` | `True` | pied de page des pages « recherche » |
| `footer_enabled_admin` | `True` | pied de page des pages « administration » |
| `shortcuts_link_enabled` | `True` | lien « Raccourcis » ; la touche `?` reste active |
| `empty_state_animation_enabled` | `True` | animation d'accueil ; respecte `prefers-reduced-motion` quoi qu'il arrive |
| `show_current_user_enabled` | `True` | badge « Connecté : … » sur la recherche |
| `show_current_user_groups_enabled` | `True` | inclut les groupes dans ce badge |
| `show_current_user_enabled_admin` | `True` | même badge sur les pages d'administration |
| `show_current_user_groups_enabled_admin` | `True` | inclut les groupes dans le badge d'administration |
| `search_history_enabled` | `False` | « Mes recherches récentes » (`GET /me/searches`) |
| `recent_documents_enabled` | `False` | « Vos derniers documents consultés » (`GET /me/recent-documents`) |
| `collections_shared_enabled` | `False` | partage d'une collection avec des groupes |
| `autocomplete_enabled` | `False` | suggestions sous la barre de recherche (`GET /suggest`) |
| `search_time_enabled` | `False` | affichage du temps de recherche |
| `header_shrink_enabled` | `False` | en-tête réduit au défilement (`docsearch-ui-vue` uniquement) |
| `login_proconnect_enabled` | `False` | bouton ProConnect, affiché **désactivé** — jalon visible, jamais un bouton qui échoue |

Aucune de ces bascules n'est un contrôle d'accès : masquer une section d'écran
ne protège rien. Le filtrage ACL des résultats, le classement par pertinence et
la journalisation ont lieu quel que soit l'état de ces flags. Les bascules qui
ont un effet côté API (`export`, `collections`, `custom_keywords`, `alerts`,
`search_history`, `autocomplete`) sont signalées ci-dessus.

### Apparence et textes

| Réglage | Défaut |
|---|---|
| `theme` | `"system"` (valeurs acceptées : `system`, `light`, `dark`) |
| `theme_admin` | `"system"` |
| `header_logo_text` | `"DocSearch"` |
| `header_subtitle_text` | `"Explorez, trouvez, comprenez"` |
| `logo_text` | `"République\nFrançaise"` (une ligne saisie = une ligne affichée) |
| `footer_text` | `"DocSearch — Explorez, trouvez, comprenez"` |
| `header_logo_url` | `""` (repli sur le monogramme générique ; ignoré par l'UI Vue, l'en-tête DSFR portant le bloc-marque) |
| `favicon_url` | `""` (repli sur `/favicon.svg`) |
| `footer_bottom_text` | `""` (vide = ligne masquée) |
| `login_inscription_url` | `""` (vide = lien masqué) |
| `login_mot_de_passe_oublie_url` | `""` (vide = lien masqué) |
| `sources_mount_display` | `""` (le chemin brut est copié tel quel) |

Les sept thèmes de couleur maison (`slate`, `red`, `contrast`…) ont été retirés
avec la migration DSFR ; les valeurs héritées encore stockées dans Redis sont
ramenées à `system` côté interface (`normalizeScheme()`).

### Repli côté interface

`docsearch-ui-vue/src/stores/uiConfig.ts` porte sa propre copie de ces défauts,
utilisée quand `/ui-config` échoue. **Règle : le repli vaut le défaut de
l'API**, sinon une fonctionnalité apparaîtrait précisément quand la
configuration n'a pas pu être lue. Toute modification d'un défaut dans
`ui_config.py` doit être répercutée là.

## 3. Signaux de satisfaction — `engagement_config.py`

Clé Redis `docsearch:config:engagement`.

| Bascule | Défaut | Effet |
|---|---|---|
| `feedback_enabled` | `True` | pouce haut/bas après chaque recherche |
| `nps_enabled` | `True` | popup « recommanderiez-vous… », périodique |
| `suggestions_enabled` | `True` | lien « Suggérer une idée » dans l'en-tête |

Le repli côté interface vaut `false` pour les trois — contrairement aux
bascules d'interface : mieux vaut ne pas solliciter l'utilisateur quand on ne
sait pas.

## 4. Types de fichiers — `filetype_config.py`

Une clé Redis **par source** : `docsearch:config:filetypes` pour la source par
défaut, `docsearch:config:filetypes:<source>` pour les autres. Fichier
dupliqué à l'identique entre `docsearch-api` et `docsearch-ingestion`.

| Type | Activé | Taille max |
|---|---|---|
| `pdf` | oui | 50 Mo |
| `docx`, `doc` | oui | 20 Mo |
| `pptx`, `ppt` | oui | 100 Mo |
| `xlsx`, `xls` | oui | 30 Mo |
| `txt` | oui | 5 Mo |
| `pst` | oui | 2000 Mo |
| `zip`, `tar`, `tar.gz`, `tgz`, `tar.bz2`, `tbz2`, `tar.xz`, `txz`, `7z` | oui | 500 Mo |
| `default` (toute extension non listée) | **non** | 10 Mo |

Pour les archives, `max_size_mb` limite la taille du **fichier archive** avant
extraction — distinct de `archive_max_total_size_mb`, qui limite la taille
décompressée totale. La clé correspond à `archive_extractor.archive_kind()` et
non au suffixe du chemin (`tar.gz`, pas `gz`).

## 5. Filtres de chemins — `path_filter.py`

Une clé Redis par source. Défaut : `{"excluded": [], "included": []}` — aucun
filtre, tout est indexé. Une liste blanche non vide restreint aux seuls chemins
correspondants ; l'élagage de parcours (`is_dir_excluded`) n'applique que la
liste noire, sans quoi un dossier parent d'un motif inclus ne serait jamais
visité.

## 6. Sources

### Source fichier par défaut — `file_sources_config.py`

| Champ | Défaut |
|---|---|
| nom | `documents` (non supprimable) |
| `subfolder` | `documents` (`DEFAULT_SOURCE_SUBFOLDER`) |
| `es_index` | `documents` (`ES_INDEX`) |
| `label` | `Documents` |
| `searchable` | `True` |
| `collectable` | `True` |
| `description` | `""` |

Défauts d'une source nouvellement créée : `collectable=True`, `description=""`,
`ocr_enabled=False` (l'OCR est coûteux en CPU, à activer explicitement),
`allowed_groups=()` (vide = aucune restriction au niveau source ; l'ACL par
document s'applique quand même).

### Sources SQL et web

| Réglage | Défaut |
|---|---|
| `sql_sources_config.DEFAULT_POLL_INTERVAL_SECONDS` | `300` |
| `web_sources_config.DEFAULT_POLL_INTERVAL_SECONDS` | `3600` |
| types de base acceptés | `postgresql`, `mysql` |
| types ES acceptés | `keyword`, `text`, `long`, `double`, `date`, `boolean` |

## 7. Variables d'environnement

### Infrastructure et indexation

| Variable | Défaut |
|---|---|
| `ES_HOST` | `http://localhost:9200` (API) / `http://es01:9200` (ingestion) |
| `ES_INDEX` | `documents` |
| `ES_SEARCH_ALIAS` | `docsearch-all` |
| `SAVED_COLLECTIONS_INDEX` | `saved_collections` |
| `CUSTOM_KEYWORDS_INDEX` | `custom_keywords` |
| `LOGIN_EVENTS_INDEX` | `login_events` |
| `KAFKA_BOOTSTRAP` | `kafka:9092` |
| `KAFKA_TOPIC` | `documents-to-index` |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` |
| `TIKA_SERVERS` | `http://tika1:9998` (jusqu'à quatre en production) |
| `SOURCES_MOUNT` | `/sources` |
| `DEFAULT_SOURCE_SUBFOLDER` | `documents` |
| `SQL_WORKER_MAX_PARALLEL` | `4` |
| `LOG_LEVEL` | `INFO` |
| `SLOW_SEARCH_MS` | `2000` |
| `APP_UID` / `DOCKER_UID` | `1000` |

Tous les TTL de cache de configuration valent **10 secondes** :
`FILETYPE_CONFIG_CACHE_TTL`, `RUNTIME_CONFIG_CACHE_TTL`, `PATHFILTER_CACHE_TTL`,
`SOURCES_CONFIG_CACHE_TTL`, `SQL_SOURCES_CACHE_TTL`,
`SQL_DSN_REGISTRY_CACHE_TTL`, `WEB_SOURCES_CACHE_TTL`, `UI_CONFIG_CACHE_TTL`.

### Authentification — `docsearch-api/app/auth/config.py`

| Variable | Défaut |
|---|---|
| `API_ENV` | `development` |
| `JWT_ISSUER` | `docsearch-api` |
| `JWT_AUDIENCE` | `docsearch` |
| `JWT_ACCESS_TOKEN_TTL_MINUTES` | `15` |
| `JWT_REFRESH_TOKEN_TTL_DAYS` | `7` |
| `REFRESH_ROTATION_GRACE_SECONDS` | `30` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `strict` |
| `RATE_LIMIT_MAX_ATTEMPTS` | `5` (tentatives **échouées**, par identifiant et par IP) |
| `RATE_LIMIT_WINDOW_SECONDS` | `900` |
| `ACCESS_GROUP` / `ADMIN_GROUP` | `""` — vides, donc **refus par défaut** |

Noms de cookies fixes, non configurables : `docsearch_access`,
`docsearch_refresh`.

`API_ENV=production` est le seul mot qui verrouille les contournements de
développement (`guardrails.py`) ; toute autre valeur, vide comprise, vaut
« développement ». Noter que `quadlet/common/docsearch.env.example` pose
`API_ENV=production` alors que le défaut du code est `development`.

`ACCESS_GROUP` et `ADMIN_GROUP` valent `""` dans le code — personne n'a accès
tant qu'ils ne sont pas renseignés. Les fichiers d'exemple proposent
`docsearch-users` et `docsearch-admins`.

### LDAP

| Variable | Défaut |
|---|---|
| `LDAP_ENABLED` | `false` |
| `LDAP_USE_SSL` | déduit du schéma de `LDAP_HOST` (`true` si `ldaps://`) |
| `LDAP_PORT` | `636` si SSL, sinon `389` |
| `LDAP_USER_SEARCH_BASE` | vide → retombe sur `LDAP_BASE` |
| `LDAP_USER_FILTER_TEMPLATE` | `(\|(uid={username})(sAMAccountName={username}))` |
| `LDAP_GROUP_SEARCH_BASE` | `""` (vide = pas de recherche inverse) |
| `LDAP_GROUP_FILTER_TEMPLATE` | `(\|(member={user_dn})(uniqueMember={user_dn}))` |
| `LDAP_CONNECT_TIMEOUT_SECONDS` | `5` |
| `LDAP_RECEIVE_TIMEOUT_SECONDS` | `10` |
| `LDAP_GROUP_CACHE_TTL_SECONDS` | `60` |
| `LDAP_ALLOW_PLAINTEXT_INSECURE` | `false` |
| `LDAP_USE_STARTTLS` | `false` |
| `LDAP_CA_CERT_FILE` | `""` (magasin de certificats système) |

`LDAP_ENABLED=false` : filtrage ACL sur les seuls groupes POSIX, et plus
personne ne peut se connecter en dehors des comptes de secours. Le filtre
utilisateur par défaut couvre OpenLDAP (`uid`) et Active Directory
(`sAMAccountName`) ; `{username}` est **toujours** échappé avant formatage — ne
jamais reconstruire ce filtre ailleurs.

Le bind en clair reste autorisé en production (beaucoup d'annuaires internes
n'exposent pas LDAPS) mais exige `LDAP_ALLOW_PLAINTEXT_INSECURE=true` et est
journalisé en `WARNING` à chaque connexion.

### Kerberos / SPNEGO

| Variable | Défaut |
|---|---|
| `KERBEROS_REALM` | `""` |
| `KERBEROS_KEYTAB` | `""` (l'exemple propose `/etc/docsearch/krb5/docsearch.keytab`) |
| `KERBEROS_SPN` | `""` |

L'interrupteur fonctionnel est le réglage à chaud `sso_kerberos_enabled`
(désactivé par défaut) : ce qui est ici ne peut pas se changer à chaud.

### Contournements de développement

Tous inertes par défaut, et **tous refusés au démarrage** si
`API_ENV=production` — l'API ne sert alors aucune requête plutôt que de les
ignorer en silence.

| Variable | Défaut |
|---|---|
| `DEV_USER` | `""` |
| `TRUST_X_USER_HEADER` | `false` |
| `KERBEROS_DEV_PRINCIPAL` | `""` |
| `ACCESS_AUTH_DISABLED` | `false` |
| `ADMIN_AUTH_DISABLED` | `false` |

`ACCESS_AUTH_DISABLED` et `ADMIN_AUTH_DISABLED` contournent le contrôle de
**groupe** uniquement : l'authentification reste exigée.

---

## Pièges connus

- **Guillemets dans un `EnvironmentFile`** : systemd ne déquote rien.
  `COOKIE_SECURE="true"` transmet la chaîne `"true"`, guillemets compris, et le
  réglage est silencieusement inversé. `auth/config.py:_nettoyer()` retire
  espaces et guillemets pour cette raison — constaté le 2026-08-06.
- **`COOKIE_SECURE` mal réglé** : le symptôme est muet. La connexion réussit,
  puis le navigateur refuse de renvoyer un cookie `Secure` sur du clair et
  chaque page ramène au formulaire. L'API l'avertit une fois par démarrage.
- **`COOKIE_SAMESITE=strict`** protège le mieux mais renvoie au formulaire
  quiconque arrive par un lien collé dans un mail ou un portail intranet.
  Passer à `lax` si c'est le mode d'accès normal des utilisateurs.
- **Timeouts LDAP en flottant** : `ldap3` 2.9.1 casse sur Python 3.14 quand
  `connect_timeout` et `receive_timeout` sont tous deux des `float`. D'où
  `_int()` dans `auth/config.py`.
- **Redis injoignable** : la lecture retombe silencieusement sur les défauts
  (avec un `WARNING` une seule fois), mais l'écriture lève — pas de sens à
  faire semblant d'avoir enregistré.
