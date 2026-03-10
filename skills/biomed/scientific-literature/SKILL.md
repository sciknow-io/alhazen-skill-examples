---
name: scientific-literature
triggers:
  - "search epmc"
  - "search pubmed"
  - "search openalex"
  - "search biorxiv"
  - "search medrxiv"
  - "find papers about"
  - "build a corpus"
  - "search literature"
  - "count papers"
  - "ingest paper"
  - "fetch paper by DOI"
  - "look up paper"
  - "add paper to corpus"
  - "embed papers"
  - "semantic search"
  - "find similar papers"
  - "cluster papers"
  - "thematic clustering"
prerequisites:
  - TypeDB running (make db-start)
  - uv sync --all-extras
  - Qdrant running for semantic commands (make qdrant-start)
  - VOYAGE_API_KEY set for embed/search-semantic/cluster
---

# Scientific Literature Skill

Multi-source scientific literature search, ingestion, and analysis.
Sources: Europe PMC, PubMed (NCBI), OpenAlex, bioRxiv/medRxiv.

## Quick Start

```bash
# Count papers before committing (EPMC)
uv run python .claude/skills/scientific-literature/scientific_literature.py count \
    --query "CRISPR AND gene editing"

# Search EPMC and store results in a corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc --query "CRISPR AND gene editing" --collection "CRISPR Papers" \
    --max-results 500

# Ingest a single paper by DOI (OpenAlex + PubMed fallback)
uv run python .claude/skills/scientific-literature/scientific_literature.py ingest \
    --doi "10.1038/s41587-020-0700-8"

# List papers in a corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py list \
    --collection "collection-abc123"
```

**Read USAGE.md before executing commands** -- full command reference, source-specific options,
query syntax, semantic search workflow, and clustering guide.
