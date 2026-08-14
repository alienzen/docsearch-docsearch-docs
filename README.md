# docsearch-docs

Documents commerciaux et de présentation du projet **DocSearch**. Séparé
du code pour ne pas mélanger contexte commercial et contexte technique.

| Dépôt | Rôle |
|---|---|
| [docsearch-ingestion](../docsearch-ingestion) | Extraction, ACL, indexation |
| [docsearch-api](../docsearch-api) | API de recherche |
| [docsearch-ui-vue](../docsearch-ui-vue) | Interface web (Vue 3, conforme au Système de Design de l'État) |
| [docsearch-infra](../docsearch-infra) | Orchestration par unités systemd Quadlet (Podman rootless) |
| **docsearch-docs** (ce dépôt) | Documents commerciaux |

## Contenu

| Fichier | Description |
|---|---|
| `proposition_docsearch.docx` | Proposition de déploiement (contexte, architecture, coûts, planning) |
| `guide_install_virtualbox.md` | Guide d'installation pas à pas sur VM VirtualBox |
| `docsearch_dsfr_v2.pptx` | Présentation PowerPoint de synthèse (charte DSFR) |
| `docsearch_presentation_fonctionnelle.docx` | Présentation fonctionnelle (périmètre, publics) |
| `guide_install_production_8_serveurs.md` | Installation en production (8 serveurs) |
| `guide_mise_a_jour_production.md` | Mise à jour d'une installation en production |
| `guide_supervision_zabbix.md` | Installation de la supervision Zabbix des 8 serveurs et de l'application |
| `planning-deploiement-6-mois.html` | Planning de déploiement, septembre 2026 à février 2027 (Gantt mensuel) |
| `planning-pilote-8-semaines.html` | Planning du pilote, 1<sup>er</sup> septembre au 23 octobre 2026 (Gantt hebdomadaire) |
| `planning-pilote-frise.html` | Frise des huit jalons du pilote, positionnés à leur date réelle |
| `architecture-docsearch.html` | Architecture des composants : chaîne de recherche, chaîne d'ingestion, Elasticsearch |

## Les quatre diagrammes

Fichiers HTML autonomes (SVG en ligne, aucune dépendance à l'exécution), produits
avec le skill `diagram-design` et la charte DSFR — Bleu France `#000091` en accent
unique, Rouge Marianne et Vert succès délibérément écartés du dessin puisqu'ils
portent un statut dans l'interface. Les polices viennent de Google Fonts : sur un
poste sans accès Internet, elles retombent sur les polices système, ce qui change
l'aspect sans rien rendre illisible.

Les deux plannings s'appuient sur `proposition_docsearch.docx` §4.1 et §4.2, avec
deux ajouts signalés en pointillé sur les planches : la bascule de
l'authentification et la revue à mi-parcours. Le diagramme d'architecture, lui,
décrit l'existant — unités Quadlet déployées et `guide_install_production_8_serveurs.md` —
et non la proposition, dont la section technique est datée (Docker Compose,
cluster à 4 nœuds).

## Chiffres clés (à jour au 02/07/2026)

- **400 utilisateurs**, **4 000 000 documents**
- Investissement initial : **0 € HT** (infrastructure et prestation en interne)
- Coût récurrent : **4 400 €/an**
- ROI sur 3 ans : **× 52**
- Stack : Elasticsearch 9.4.3, Apache Tika 3.3.1.0, Kafka 8.3 (KRaft)

## Deux formats, et lequel choisir

**Les guides techniques sont en Markdown** — les trois premiers depuis leur
conversion du 2026-08-06, le guide de supervision (2026-08-10) l'ayant été
d'emblée. Ce sont eux qui changent au rythme du code, et un `.docx` ne se relit pas
dans un diff : une modification y est invisible à la revue, et deux
personnes qui éditent le même fichier produisent un conflit binaire
irréconciliable. Leurs versions Word restent récupérables dans
l'historique Git (`git show 81fcfc5^:guide_install_production_8_serveurs.docx`).

La conversion a été faite par [`outils/docx-vers-md.py`](outils/docx-vers-md.py),
conservé pour la prochaine fois : `pandoc` ne convient pas sur ces
documents — il perd les titres, dont les styles Word ne sont pas reconnus,
et rend en tableaux HTML les blocs de code, qui y sont des tableaux à une
cellule composés à chasse fixe.

Les documents **commerciaux** (proposition, présentation fonctionnelle,
support PowerPoint) restent en Word et PowerPoint : ils sont mis en page,
diffusés hors de l'équipe, et changent rarement.

## Mise à jour de ces documents

Les documents Word et PowerPoint sont générés via des scripts Python
(docx/pptx) — voir les skills `docx` et `pptx` pour la méthode de
génération et de mise en page DSFR (Bleu France `#000091`, Vert succès
`#18753C`, Rouge Marianne `#E1000F`). Les guides en Markdown s'éditent
directement.

Toute mise à jour de version technique (ES, Tika, Kafka) ou de périmètre
(utilisateurs, documents) doit être répercutée à la fois ici et dans les
README techniques des autres dépôts.
