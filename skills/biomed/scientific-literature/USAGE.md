# Scientific Literature Skill -- Usage Reference

Multi-source scientific literature search and ingestion for the Alhazen knowledge graph.
Sources: Europe PMC (EPMC), PubMed (NCBI), OpenAlex, bioRxiv/medRxiv.

---

## Commands

### `search` -- Search a source and store results

```bash
# Search Europe PMC (cursor-based, handles large corpora)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "CRISPR AND gene editing" \
    --collection "CRISPR Papers" \
    --max-results 500

# Search PubMed
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source pubmed --query "CRISPR off-target effects" \
    --collection "collection-abc123" --max-results 30

# Search OpenAlex (broad interdisciplinary coverage)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source openalex --query "base editing precision genome" --max-results 20

# Search bioRxiv/medRxiv (last 30 days, client-side keyword filter)
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source biorxiv --query "spatial transcriptomics" --max-results 20
```

**Options:**
- `--source` (required): `epmc`, `pubmed`, `openalex`, `biorxiv`, `medrxiv`
- `--query` (required): Search query
- `--collection`: Collection name (EPMC: creates new collection; others: collection ID to add to)
- `--collection-id`: Specific collection ID (EPMC only)
- `--max-results`: Limit number of papers fetched
- `--page-size`: Results per API call, EPMC only (default: 1000)

**Returns (EPMC):**
```json
{
  "success": true,
  "collection_id": "collection-abc123",
  "collection_name": "CRISPR Papers",
  "query": "CRISPR AND gene editing",
  "total_count": 15234,
  "fetched_count": 500,
  "stored_count": 487,
  "skipped_count": 13
}
```

**Returns (PubMed/OpenAlex/bioRxiv):**
```json
{
  "success": true,
  "source": "pubmed",
  "query": "CRISPR off-target",
  "inserted": 18,
  "skipped": 2,
  "papers": [{"id": "scilit-paper-abc", "title": "...", "status": "inserted"}, ...]
}
```

**Deduplication:** Papers already in the graph (matched by DOI or PMID) are skipped.

---

### `count` -- Count EPMC results without storing

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py count \
    --query "COVID-19 AND vaccine"
```

Returns: `{"success": true, "query": "...", "count": 42819}`

---

### `ingest` -- Fetch a single paper by DOI

```bash
# By DOI (tries OpenAlex first, then PubMed as fallback)
uv run python .claude/skills/scientific-literature/scientific_literature.py ingest \
    --doi "10.1038/s41587-020-0700-8" [--collection collection-abc123]

# By PMID (EPMC lookup)
uv run python .claude/skills/scientific-literature/scientific_literature.py ingest \
    --pmid "32015507" [--collection collection-abc123]
```

---

### `show` -- Show paper details for sensemaking

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py show \
    --id "scilit-paper-abc123"
```

Returns title, abstract, identifiers, and any notes already stored about this paper.

---

### `list` -- List papers

```bash
# All papers in graph
uv run python .claude/skills/scientific-literature/scientific_literature.py list

# Papers in a specific corpus
uv run python .claude/skills/scientific-literature/scientific_literature.py list \
    --collection "collection-abc123"
```

---

### `list-collections` -- List all scilit corpora

```bash
uv run python .claude/skills/scientific-literature/scientific_literature.py list-collections
```

---

### `embed` -- Generate Voyage AI embeddings and load Qdrant

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py embed \
    --collection collection-abc123 [--reembed] [--limit 500]
```

**Prerequisites:** Qdrant running (`make qdrant-start`), `VOYAGE_API_KEY` set.

- Fetches all `scilit-paper` members of the collection from TypeDB
- Checks which paper IDs already exist in Qdrant (skips unless `--reembed`)
- Builds embedding text: `title + "\n\n" + abstract`
- Calls Voyage AI `voyage-3-lite` in batches of 128 (1,024-dim vectors)
- Upserts into the `alhazen_papers` Qdrant collection

**Cost estimate:** ~$0.012 per 1,000 papers (voyage-3-lite is $0.02/M tokens; avg ~600 tokens/paper)

---

### `search-semantic` -- Find similar papers by meaning

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py search-semantic \
    --query "cardiac microRNA energy homeostasis" \
    --collection collection-abc123 --limit 10
```

Returns ranked papers with similarity scores.

---

### `cluster` -- HDBSCAN thematic clustering

```bash
# Step 1: dry-run to inspect clusters
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 --dry-run

# Step 2: write theme tags back to TypeDB
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 \
    --labels 0:transcription-regulation 1:chromatin-remodeling 2:cell-cycle-control
```

**Tuning `--min-cluster-size`:** Start with 15 for large corpora (>500 papers); use 5-10 for small corpora.

---

### `plot-clusters` -- 2D UMAP scatter plot

```bash
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py plot-clusters \
    --collection collection-abc123 --min-cluster-size 10 \
    --output clusters.png --labels 0:theme-a 1:theme-b
```

---

## EPMC Query Syntax

### Boolean Operators
- `AND`, `OR`, `NOT`
- `""` for exact phrase
- `*` for wildcard
- `()` for grouping

### Field-Specific Searches

| Field | Example |
|-------|---------|
| `TITLE:` | `TITLE:CRISPR` |
| `ABSTRACT:` | `ABSTRACT:"gene editing"` |
| `AUTH:` | `AUTH:"Smith J"` |
| `JOURNAL:` | `JOURNAL:Nature` |
| `DOI:` | `DOI:"10.1038/..."` |
| `PMID:` | `PMID:12345678` |
| `GRANT_ID:` | `GRANT_ID:R01GM123456` |
| `GRANT_AGENCY:` | `GRANT_AGENCY:NIH` |

### Date Filters
```
PUB_YEAR:2023
FIRST_PDATE:[2020-01-01 TO 2024-12-31]
FIRST_PDATE:[2023-01-01 TO *]
```

### Publication Type
```
PUB_TYPE:"journal article"
PUB_TYPE:review
PUB_TYPE:preprint
OPEN_ACCESS:y
```

### Complex Query Examples

```bash
# CRISPR papers from 2022 onwards
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "CRISPR AND (Cas9 OR Cas12) AND FIRST_PDATE:[2022-01-01 TO *]" \
    --collection "Recent CRISPR"

# Open access single-cell papers
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query '"single cell" AND (RNA-seq OR transcriptomics) AND OPEN_ACCESS:y' \
    --collection "Open Access scRNA-seq"
```

---

## Typical Workflow

```bash
# 1. Estimate EPMC corpus size
uv run python .claude/skills/scientific-literature/scientific_literature.py count \
    --query "your query"

# 2. Create collection (via typedb-notebook)
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-collection \
    --name "CRISPR Off-Target Review"
# -> {"collection_id": "collection-abc123"}

# 3. Search and ingest from multiple sources
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc --query "CRISPR off-target" \
    --collection "CRISPR Off-Target Review" --max-results 500

uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source pubmed --query "CRISPR off-target effects" \
    --collection "collection-abc123" --max-results 30

# 4. List ingested papers
uv run python .claude/skills/scientific-literature/scientific_literature.py list \
    --collection "collection-abc123"

# 5. Show a paper for sensemaking
uv run python .claude/skills/scientific-literature/scientific_literature.py show \
    --id "scilit-paper-abc123"

# 6. Add a note (via typedb-notebook)
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-note \
    --subject "scilit-paper-abc123" \
    --content "Key finding: off-target rate <0.1% with high-fidelity Cas9 variants"
```

---

## Semantic Search Workflow

```bash
# 1. Embed collection (one-time, incremental)
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py embed \
    --collection collection-abc123

# 2. Semantic search
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py search-semantic \
    --query "CDK8 kinase module stress response" \
    --collection "collection-abc123" --limit 10

# 3. Cluster (dry-run first)
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 --dry-run
# Claude reads representative titles and proposes theme names, then:
VOYAGE_API_KEY=xxx uv run python .claude/skills/scientific-literature/scientific_literature.py cluster \
    --collection collection-abc123 --min-cluster-size 15 \
    --labels 0:transcription-regulation 1:chromatin-remodeling
```

### Semantic Search Architecture

```
TypeDB (authoritative graph)     Qdrant (semantic index)
-----------------------------    -------------------------
scilit-paper                     collection: "alhazen_papers"
  id, name, abstract-text          point id = uuid5(paper_id)
  doi, year, keyword               vector = voyage-3-lite(title+abstract)
   (theme tags written back) <-    payload = {paper_id, collection_ids[], title, doi, year}
```

**Environment variables:**
- `VOYAGE_API_KEY` -- from https://dash.voyageai.com/
- `QDRANT_HOST` -- Qdrant host (default: localhost)
- `QDRANT_PORT` -- Qdrant port (default: 6333)

---

## Source Connector Details

### Europe PMC
- **API:** `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
- **Pagination:** Cursor-based (handles corpora of 50k+ papers reliably)
- **Coverage:** ~45M+ records including PubMed and preprints
- **Best for:** Large-scale corpus building, combined PubMed + preprint coverage
- **Docs:** https://europepmc.org/RestfulWebService

### PubMed (NCBI Entrez)
- **API:** `esearch.fcgi` (get PMIDs) + `efetch.fcgi` (get full XML records)
- **Rate limit:** 3 req/s without key; 10 req/s with `NCBI_API_KEY`
- **API key:** Free from https://www.ncbi.nlm.nih.gov/account/
- **Best for:** Precise biomedical queries, MeSH-filtered searches

### OpenAlex
- **API:** `https://api.openalex.org/works?search=...`
- **API key:** Free from https://openalex.org/settings/api
- **Coverage:** 240M+ works across all disciplines
- **Note:** Abstracts stored as inverted indexes; reconstructed automatically
- **Best for:** Broad interdisciplinary searches

### bioRxiv / medRxiv
- **API:** `https://api.biorxiv.org/pubs/biorxiv/30d/{cursor}` (date range only)
- **Limitation:** No full-text search -- fetches last 30 days, filters client-side by keyword
- **Best for:** Recent preprints

---

## Cross-Skill: Literature as Learning Resources

Paper collections can serve as learning resources for the **jobhunt** skill.

```bash
# 1. Search for papers on a skill gap topic
uv run python .claude/skills/scientific-literature/scientific_literature.py search \
    --source epmc \
    --query "machine learning systems design" \
    --collection "ML Systems Reading List" \
    --max-results 20

# 2. Link the collection to a skill gap in jobhunt
uv run python .claude/skills/jobhunt/jobhunt.py link-collection \
    --collection "<collection-id>" --skill "machine-learning"

# 3. View updated learning plan
uv run python .claude/skills/jobhunt/jobhunt.py learning-plan
```

---

## Data Model

Papers are stored as `scilit-paper` entities (sub `domain-thing`) using the `schema.tql` schema:

| Attribute | Type | Notes |
|-----------|------|-------|
| `id` | string @key | Auto-generated (`scilit-paper-xxxxxxxx`) or `doi-...` for EPMC |
| `name` | string | Paper title |
| `abstract-text` | string | Full abstract |
| `doi` | string | DOI (without https://doi.org/ prefix) |
| `pmid` | string | PubMed ID |
| `pmcid` | string | PubMed Central ID |
| `arxiv-id` | string | arXiv ID |
| `publication-year` | integer | Year of publication |
| `journal-name` | string | Journal or preprint server name |
| `source-uri` | string | Canonical URL for this paper |
| `keyword` | string (multi) | Keywords and theme tags |
