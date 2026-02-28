---
name: epmc-search
description: Search Europe PMC for scientific papers and store them in the TypeDB knowledge graph
---

# Europe PMC Search Skill

Search Europe PMC (EPMC) for scientific literature and store results in the Alhazen TypeDB knowledge graph. Use this to build corpora of papers on research topics.

**When to use:** "search epmc", "search for papers", "find papers about", "build a corpus", "search pubmed", "search literature", "count papers", "fetch paper by DOI", "list collections"

## Prerequisites

- TypeDB must be running: `make db-start`
- Dependencies installed: `uv sync --all-extras` (from project root)

## Environment Variables

- `TYPEDB_HOST`: TypeDB server (default: localhost)
- `TYPEDB_PORT`: TypeDB port (default: 1729)
- `TYPEDB_DATABASE`: Database name (default: alhazen_notebook)

## Quick Start

```bash
# Count papers before committing
uv run python .claude/skills/epmc-search/epmc_search.py count --query "CRISPR AND gene editing"

# Search and store papers
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "CRISPR AND gene editing" \
    --collection "CRISPR Papers" \
    --max-results 500
```

**Before executing any commands, read `USAGE.md` in this directory for the complete command reference, query syntax, and workflow examples.**
