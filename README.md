# docsearch-docs

Documents commerciaux et de présentation du projet **DocSearch**. Séparé
du code pour ne pas mélanger contexte commercial et contexte technique.

| Dépôt | Rôle |
|---|---|
| [docsearch-ingestion](../docsearch-ingestion) | Extraction, ACL, indexation |
| [docsearch-api](../docsearch-api) | API de recherche |
| [docsearch-ui-vue](../docsearch-ui-vue) | Interface web (Vue 3, conforme au Système de Design de l'État) |
| [docsearch-infra](../docsearch-infra) | Orchestration Docker Compose |
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
