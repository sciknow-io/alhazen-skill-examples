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
  - TypeDB running (install alhazen-core first and run /alhazen-core:init)
  - uv installed
  - Qdrant running for semantic commands (docker run -d -p 6333:6333 qdrant/qdrant)
  - VOYAGE_API_KEY set for embed/search-semantic/cluster
---

# Scientific Literature Skill

Multi-source scientific literature search, ingestion, and analysis.
Sources: Europe PMC, PubMed (NCBI), OpenAlex, bioRxiv/medRxiv.

## Quick Start

> **Path note:** Replace `<skill-path>` with your installation directory
> (e.g. `~/.claude/plugins/cache/scientific-literature/` when installed as a plugin).

```bash
# Count papers before committing (EPMC)
uv run --project <skill-path> python <skill-path>/scientific_literature.py count \
    --query "CRISPR AND gene editing"

# Search EPMC and store results in a corpus
uv run --project <skill-path> python <skill-path>/scientific_literature.py search \
    --source epmc --query "CRISPR AND gene editing" --collection "CRISPR Papers" \
    --max-results 500

# Ingest a single paper by DOI (OpenAlex + PubMed fallback)
uv run --project <skill-path> python <skill-path>/scientific_literature.py ingest \
    --doi "10.1038/s41587-020-0700-8"

# List papers in a corpus
uv run --project <skill-path> python <skill-path>/scientific_literature.py list \
    --collection "collection-abc123"
```

## Full-Text Ingestion & Per-Paper Cache — REQUIRED convention

This is the ONLY correct way to ingest a paper's full text and cache its files. It is
**mandatory and uniform across every scilit investigation** (search corpora, deep-dives,
CAIS, etc.) — never improvise an alternate layout.

### 1. Paper identity (deterministic)
Every paper is a `scilit-paper` whose id is a **pure function of its best stable
identifier**: `DOI → PMID → arXiv → content-hash(title|first-author|year)`. Compute it
with `paper_identity()` in `paper_identity.py`; create/find papers only via
`kqed.upsert_paper(driver, meta)`. Same paper → same id, always. The tier is recorded in
`scilit-identity-basis` / `scilit-identity-value`. (Full design: `docs/paper-identity-design.md`.)

### 2. One directory per paper holds ALL of its content
```
~/.alhazen/cache/fulltext/<paper-id>/
    source.pdf                  # the source PDF
    text.md                     # full text extracted by kreuzberg
    tables/<n>.md               # kreuzberg-extracted tables
    figures/<n>.png             # extracted figures
    supplement/<original-name>  # supplementary files
    data/<original-name>        # associated datasets / data files
```
**EVERY file derived from, or supplied with, a specific paper goes in that paper's
`fulltext/<paper-id>/` subdirectory — and nowhere else.** This explicitly includes
kreuzberg text/table extraction (do NOT leave it in `cache/extracted/` or `cache/text/`),
the source PDF (NOT `cache/pdf/` or `cache/papers/`), and all supplemental / data files.

### 3. Rules
- **MOVE files into place** (copy, then remove the original) — **never symlink**, and never
  leave a paper's content scattered in `cache/pdf/`, `cache/text/`, `cache/extracted/`, or
  `cache/papers/`.
- **Register every cached file** as an `alh-artifact` with id
  `scilit-fulltext-<paper-hash>-<kind>` (paper-hash = the paper id's 12-hex suffix), attribute
  `scilit-fulltext-kind` ∈ `pdf | text | table | figure | supplement | data`, and
  `cache-path = fulltext/<paper-id>/<file>`, linked to the paper via `alh-representation`.
- **The path is computable from the paper id** — `paper → fulltext/<paper-id>/source.pdf`
  needs no graph lookup. Keep it that way.
- A paper with a local source PDF must carry `scilit-acquisition-status = held`; a
  cited-but-undownloaded reference is `needed`.

### 4. Ingestion flow (per paper)
1. `upsert_paper(meta)` → deterministic `<paper-id>`.
2. Download the source PDF → **move** to `fulltext/<paper-id>/source.pdf`; register the `pdf` artifact; set status `held`.
3. Extract text/tables with kreuzberg → write `text.md`, `tables/*` **into the same dir**; register `text`/`table` artifacts.
4. Any figures / supplemental / data files → same dir, registered with the matching `kind`.
5. Never write any of the above outside `fulltext/<paper-id>/`.

> `cache/pdf/` may still hold OTHER skills' documents (tech-recon, health-coach) — those are
> out of scope for this convention; do not touch them. This convention governs `scilit-paper`
> content only.

Reconciliation prototypes that retrofit existing data to this layout live in
`prototypes/reconcile_*_fulltext.py` (they MOVE sources into `fulltext/<paper-id>/`).

---

**Read USAGE.md before executing commands** -- full command reference, source-specific options,
query syntax, semantic search workflow, and clustering guide.
