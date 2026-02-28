---
name: apm
description: Investigate rare diseases using the Algorithm for Precision Medicine - from symptoms to diagnosis to treatment
---

# Algorithm for Precision Medicine (APM) Skill

Use this skill to investigate rare diseases following Matt Might's Algorithm for Precision Medicine. Claude acts as a diagnostic detective, building a knowledge graph from symptoms through molecular diagnosis to therapeutic strategy.

**When to use:** "new case", "investigate patient", "start APM", "rare disease case", "analyze this report", "diagnostic chain", "therapeutic options", "ACMG classification", "gene variant"

## The APM Workflow

1. **Phase 1 (Diagnostic)** — symptoms → variants → gene → disease
2. **Phase 2 (Therapeutic)** — mechanism of harm → protein → drug targets

## Prerequisites

- TypeDB must be running: `make db-start`
- Dependencies installed: `uv sync --all-extras` (from project root)

## Environment Variables

- `TYPEDB_HOST`: TypeDB server (default: localhost)
- `TYPEDB_PORT`: TypeDB port (default: 1729)
- `TYPEDB_DATABASE`: Database name (default: alhazen_notebook)

## Quick Start

```bash
# Create a case
uv run python .claude/skills/apm/apm.py add-case \
    --name "Patient Case" --diagnostic-status "unsolved" --phase "diagnostic"

# Add phenotypes
uv run python .claude/skills/apm/apm.py add-phenotype \
    --hpo-id "HP:0000522" --label "Alacrima"
```

**Before executing any commands, read `USAGE.md` in this directory for the complete command reference, sensemaking workflow, data model, and full investigation example.**
