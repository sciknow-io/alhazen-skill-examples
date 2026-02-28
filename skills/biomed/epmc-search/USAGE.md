# Europe PMC Search — Usage Reference

## Commands

### Search and Store Papers

Search EPMC and store results in TypeDB as a collection.

**Triggers:** "search epmc", "search for papers", "find papers about", "build a corpus", "search pubmed", "search literature"

```bash
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "CRISPR AND gene editing" \
    --collection "CRISPR Papers" \
    --max-results 500
```

**Options:**
- `--query` (required): EPMC search query
- `--collection`: Name for the collection (auto-generated if not provided)
- `--collection-id`: Specific collection ID
- `--max-results`: Limit number of papers fetched
- `--page-size`: Results per API call (default: 1000)

**Returns:**
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

### Count Results

Count papers matching a query without storing anything.

**Triggers:** "how many papers", "count papers", "estimate corpus size"

```bash
uv run python .claude/skills/epmc-search/epmc_search.py count --query "COVID-19 AND vaccine"
```

### Fetch Single Paper

```bash
# By DOI
uv run python .claude/skills/epmc-search/epmc_search.py fetch-paper --doi "10.1038/s41586-020-2008-3"

# By PMID
uv run python .claude/skills/epmc-search/epmc_search.py fetch-paper --pmid "32015507"

# Add to existing collection
uv run python .claude/skills/epmc-search/epmc_search.py fetch-paper \
    --doi "10.1038/s41586-020-2008-3" --collection "collection-abc123"
```

### List Collections

```bash
uv run python .claude/skills/epmc-search/epmc_search.py list-collections
```

---

## Query Syntax

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
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "CRISPR AND (Cas9 OR Cas12) AND FIRST_PDATE:[2022-01-01 TO *]" \
    --collection "Recent CRISPR"

# Open access single-cell papers
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query '"single cell" AND (RNA-seq OR transcriptomics) AND OPEN_ACCESS:y' \
    --collection "Open Access scRNA-seq"

# Papers by author in specific journal
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query 'AUTH:"Doudna J" AND JOURNAL:Science' \
    --collection "Doudna Science Papers"
```

---

## Workflows

### Literature Corpus Building

```bash
# 1. Estimate size
uv run python .claude/skills/epmc-search/epmc_search.py count --query "your query"

# 2. Search and store (adjust max-results based on count)
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "your query" \
    --collection "Descriptive Name" \
    --max-results 1000

# 3. Review collection
uv run python .claude/skills/typedb-notebook/typedb_notebook.py query-collection --id "collection-xxx"

# 4. Add notes about papers
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-note \
    --subject "paper-id" \
    --content "Key finding: ..."
```

### Targeted Paper Import

```bash
# 1. Create collection
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-collection --name "Key Papers"

# 2. Fetch specific papers
uv run python .claude/skills/epmc-search/epmc_search.py fetch-paper \
    --doi "10.1234/paper1" --collection "collection-xxx"

# 3. Add analysis notes
uv run python .claude/skills/typedb-notebook/typedb_notebook.py insert-note \
    --subject "doi-10_1234-paper1" \
    --content "Analysis: ..."
```

---

## Cross-Skill: Literature as Learning Resources

Paper collections created by EPMC searches can serve as learning resources for the **jobhunt** skill.

```bash
# 1. Search for papers on a skill gap topic
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "machine learning systems design" \
    --collection "ML Systems Reading List" \
    --max-results 20

# 2. Link the collection to a skill gap in jobhunt
uv run python .claude/skills/jobhunt/jobhunt.py link-collection \
    --collection "<collection-id>" \
    --skill "machine-learning"

# 3. View updated learning plan
uv run python .claude/skills/jobhunt/jobhunt.py learning-plan
```

---

## API Documentation

- Europe PMC REST API: https://europepmc.org/RestfulWebService
- Search syntax: https://europepmc.org/searchsyntax
- API endpoint: `https://www.ebi.ac.uk/europepmc/webservices/rest/search`

The script uses `resultType=core` to get full metadata including abstracts.
