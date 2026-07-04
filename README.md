# docsearch-docs

Documents commerciaux et de présentation du projet **DocSearch**. Séparé
du code pour ne pas mélanger contexte commercial et contexte technique.

| Dépôt | Rôle |
|---|---|
| [docsearch-ingestion](../docsearch-ingestion) | Extraction, ACL, indexation |
| [docsearch-api](../docsearch-api) | API de recherche |
| [docsearch-ui](../docsearch-ui) | Interface web statique |
| [docsearch-infra](../docsearch-infra) | Orchestration Docker Compose |
| **docsearch-docs** (ce dépôt) | Documents commerciaux |

## Contenu

| Fichier | Description |
|---|---|
| `proposition_docsearch.docx` | Proposition de déploiement (contexte, architecture, coûts, planning) |
| `guide_install_virtualbox.docx` | Guide d'installation pas à pas sur VM VirtualBox |
| `docsearch_dsfr_v2.pptx` | Présentation PowerPoint de synthèse (charte DSFR) |

## Chiffres clés (à jour au 02/07/2026)

- **400 utilisateurs**, **4 000 000 documents**
- Investissement initial : **0 € HT** (infrastructure et prestation en interne)
- Coût récurrent : **4 400 €/an**
- ROI sur 3 ans : **× 52**
- Stack : Elasticsearch 9.4.3, Apache Tika 3.3.1.0, Kafka 8.3 (KRaft)

## Mise à jour de ces documents

Ces documents sont générés via des scripts Python (docx/pptx) — voir les
skills `docx` et `pptx` pour la méthode de génération et de mise en page
DSFR (Bleu France `#000091`, Vert succès `#18753C`, Rouge Marianne `#E1000F`).

Toute mise à jour de version technique (ES, Tika, Kafka) ou de périmètre
(utilisateurs, documents) doit être répercutée à la fois ici et dans les
README techniques des autres dépôts.
