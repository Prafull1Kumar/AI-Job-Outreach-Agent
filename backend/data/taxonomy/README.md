# Taxonomy Files

You can place technology/skill taxonomies here to enrich keyword extraction.

Supported formats:
- `tech_phrases.json`
  - Either `{ "alias": "Canonical Label" }` or `["term1", "term2"]`
- `tech_phrases.csv`
  - A column named one of: `skill`, `technology`, `name`, `preferred_label`, `label`, `term`
- `tech_phrases.txt`
  - One term per line
- `onet_technology_skills.txt`
  - Raw O*NET Technology Skills TXT format

By default, `job_service.py` auto-loads these files if present.

Optional override:
- Set `TECH_TAXONOMY_PATHS` in `.env` with comma-separated file paths.
