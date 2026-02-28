---
name: rare-disease
description: Investigate a MONDO rare disease: pull curated KG data, build phenome/genome/therapeutome, synthesize mechanism and treatment landscape
---

# Rare Disease Investigation Skill

Use this skill to build a comprehensive disease knowledge graph starting from a MONDO
disease ID. Pulls curated phenotypes, causal genes, similar diseases, clinical trials,
and drug candidates from Monarch Initiative + ClinicalTrials.gov + ChEMBL. Claude
synthesizes mechanism, diagnostic criteria, therapeutic landscape, and research gaps.

**When to use:** "investigate disease", "MONDO disease", "rare disease profile",
"disease phenome", "therapeutic landscape", "similar diseases", "what genes cause X",
"build disease KG", "disease mechanism", "treatment options for rare disease"

## Prerequisites

- TypeDB must be running: `make db-start`
- Dependencies installed: `uv sync --all-extras` (from project root)

## Environment Variables

- `TYPEDB_HOST`: TypeDB server (default: localhost)
- `TYPEDB_PORT`: TypeDB port (default: 1729)
- `TYPEDB_DATABASE`: Database name (default: alhazen_notebook)

## Quick Start

```bash
# 1. Search for a disease by name
uv run python .claude/skills/rare-disease/rare_disease.py search-disease --query "NGLY1 deficiency"

# 2. Initialize full knowledge graph from MONDO ID
uv run python .claude/skills/rare-disease/rare_disease.py init-disease --mondo-id "MONDO:0800044"

# 3. Ingest associations (use disease-id from step 2)
uv run python .claude/skills/rare-disease/rare_disease.py ingest-phenotypes --disease <disease-id>
uv run python .claude/skills/rare-disease/rare_disease.py ingest-genes --disease <disease-id>
uv run python .claude/skills/rare-disease/rare_disease.py ingest-hierarchy --disease <disease-id>
uv run python .claude/skills/rare-disease/rare_disease.py ingest-clintrials --disease <disease-id>

# 4. Build a literature corpus
uv run python .claude/skills/rare-disease/rare_disease.py build-corpus --disease <disease-id>

# 5. Query
uv run python .claude/skills/rare-disease/rare_disease.py show-disease --id <disease-id>
uv run python .claude/skills/rare-disease/rare_disease.py show-phenome --id <disease-id>
```

**Before executing commands, read `USAGE.md` in this directory for the complete reference.**
