# Rare Disease Investigation Skill — Full Reference

## Philosophy

Unlike APM (which starts from a patient case and works toward diagnosis), this skill
**starts from a known disease** (MONDO ID) and builds a 360° knowledge graph:

| APM | rare-disease |
|-----|--------------|
| Patient case → diagnosis | MONDO ID → full disease profile |
| Symptom-driven | Disease-driven |
| Diagnostic chain | Phenome + genome + therapeutome |
| Single patient focus | Population-level disease characterization |

The mechanism model is **shared with APM** (4 categories: gain-of-function, partial-loss,
total-loss, dominant-negative, toxification). This enables cross-skill reasoning when
a patient case (APM) leads to a known disease (rare-disease).

---

## Curation Workflow (5 Phases)

### Phase 1: FORAGING — Identify the Disease

```bash
# Find the MONDO ID for a disease by name
uv run python .claude/skills/rare-disease/rare_disease.py search-disease --query "NGLY1 deficiency"
# → returns list of MONDO IDs + names
# → pick the right one, note the MONDO ID (e.g., MONDO:0800044)
```

### Phase 2: INGESTION — Pull Curated Knowledge

```bash
# 1. Initialize from MONDO (creates disease entity + investigation + MONDO record artifact)
uv run python .claude/skills/rare-disease/rare_disease.py init-disease --mondo-id "MONDO:0800044"
# → returns disease-id (e.g., rd-disease-abc123def456)

DISEASE_ID=rd-disease-abc123def456

# 2. Ingest HPO phenotypes from Monarch
uv run python .claude/skills/rare-disease/rare_disease.py ingest-phenotypes --disease $DISEASE_ID

# 3. Ingest causal and associated genes
uv run python .claude/skills/rare-disease/rare_disease.py ingest-genes --disease $DISEASE_ID

# 4. Ingest MONDO hierarchy (parent classes)
uv run python .claude/skills/rare-disease/rare_disease.py ingest-hierarchy --disease $DISEASE_ID

# 5. Ingest phenotypically similar diseases
uv run python .claude/skills/rare-disease/rare_disease.py ingest-similar --disease $DISEASE_ID --limit 20

# 6. Ingest clinical trials
uv run python .claude/skills/rare-disease/rare_disease.py ingest-clintrials --disease $DISEASE_ID

# 7. Ingest drug candidates via ChEMBL (uses causal genes)
uv run python .claude/skills/rare-disease/rare_disease.py ingest-drugs --disease $DISEASE_ID
```

### Phase 3: SENSEMAKING — Claude Reads Artifacts

```bash
# Get the MONDO record artifact (raw Monarch entity JSON)
uv run python .claude/skills/rare-disease/rare_disease.py list-artifacts --disease $DISEASE_ID
uv run python .claude/skills/rare-disease/rare_disease.py show-artifact --id <artifact-id>
```

Ask Claude: *"Analyze this MONDO record and extract: synonyms, inheritance pattern, age of onset,
prevalence, OMIM/ORPHA cross-references, and any mentioned causal genes."*

### Phase 4: ANALYSIS — Claude Synthesizes Notes

Use `add-note` after Claude's sensemaking to record interpretations:

```bash
# Record disease overview
uv run python .claude/skills/rare-disease/rare_disease.py add-note \
    --about $DISEASE_ID \
    --type disease-overview \
    --name "NGLY1 Deficiency Overview" \
    --content "NGLY1 deficiency (MONDO:0800044) is an ultra-rare autosomal recessive..."

# Record mechanism analysis
uv run python .claude/skills/rare-disease/rare_disease.py add-note \
    --about $DISEASE_ID \
    --type mechanism \
    --mechanism-type total-loss \
    --functional-impact absence \
    --content "NGLY1 encodes N-glycanase 1, the only known enzyme that cleaves N-glycans..."

# Record therapeutic landscape
uv run python .claude/skills/rare-disease/rare_disease.py add-note \
    --about $DISEASE_ID \
    --type therapeutic-landscape \
    --content "No approved therapies. Clinical trials exploring proteasome pathway..."
```

### Phase 5: REPORTING — Query the Knowledge Graph

```bash
uv run python .claude/skills/rare-disease/rare_disease.py show-disease --id $DISEASE_ID
uv run python .claude/skills/rare-disease/rare_disease.py show-phenome --id $DISEASE_ID --min-freq frequent
uv run python .claude/skills/rare-disease/rare_disease.py show-therapeutome --id $DISEASE_ID
uv run python .claude/skills/rare-disease/rare_disease.py show-similar --id $DISEASE_ID
uv run python .claude/skills/rare-disease/rare_disease.py show-hierarchy --id $DISEASE_ID
```

---

## All Commands

### Discovery Commands

#### `search-disease`
Search Monarch Initiative for diseases matching a query.

```bash
uv run python .claude/skills/rare-disease/rare_disease.py search-disease \
    --query "NGLY1 deficiency" \
    --limit 10
```

**Output:**
```json
{
  "success": true,
  "count": 3,
  "diseases": [
    {
      "mondo_id": "MONDO:0800044",
      "name": "NGLY1-related congenital disorder of deglycosylation",
      "description": "A rare autosomal recessive disorder...",
      "matching_text": "NGLY1 deficiency"
    }
  ]
}
```

#### `init-disease`
Initialize the disease knowledge graph from a MONDO ID.

```bash
uv run python .claude/skills/rare-disease/rare_disease.py init-disease \
    --mondo-id "MONDO:0800044"
```

Creates:
- `rd-disease` entity with MONDO ID, name, xrefs, inheritance
- `rd-investigation` collection linked via `collection-membership`
- `rd-mondo-record` artifact with raw Monarch JSON, linked via `representation`

**Idempotent:** re-running returns the existing disease ID.

---

### Ingestion Commands

#### `ingest-phenotypes --disease <id>`
Pull HPO phenotype associations from Monarch.

Maps HP frequency qualifier codes:
- `HP:0040280` → `obligate` (100%)
- `HP:0040281` → `very-frequent` (80-99%)
- `HP:0040282` → `frequent` (30-79%)
- `HP:0040283` → `occasional` (5-29%)
- `HP:0040284` → `rare` (1-4%)
- `HP:0040285` → `very-rare` (<1%)

#### `ingest-genes --disease <id>`
Pull causal and correlated gene associations from Monarch.
- `CausalGeneToDiseaseAssociation` → `rd-gene-causes-disease`
- `CorrelatedGeneToDiseaseAssociation` → `rd-gene-associated-with`

#### `ingest-hierarchy --disease <id>`
Parse `node_hierarchy.super_classes` from the stored `rd-mondo-record` artifact.
Creates parent `rd-disease` entities + `rd-disease-subclass-of` relations.
**Note:** Requires `init-disease` to have been run first.

#### `ingest-similar --disease <id> [--limit N]`
Query Monarch SemSim using the disease's HPO phenotype list.
Creates `rd-disease-similar-to` relations with similarity scores.
**Note:** Requires `ingest-phenotypes` to have been run first.

#### `ingest-clintrials --disease <id>`
Query ClinicalTrials.gov API v2 with the disease name.
Creates `rd-clinical-trial` entities + `rd-trial-studies` relations.

#### `ingest-drugs --disease <id>`
For each causal gene: look up ChEMBL targets, then drug mechanisms.
Creates `rd-drug` entities + `rd-drug-targets` relations.
**Note:** Requires `ingest-genes` to have been run first.

#### `build-corpus --disease <id>`
Print ready-to-run `epmc-search` CLI commands for literature ingestion.
Does NOT execute the commands — copy-paste to run.

```bash
uv run python .claude/skills/rare-disease/rare_disease.py build-corpus --disease $DISEASE_ID
```

Output includes 3-5 targeted queries covering: disease overview, gene mechanism,
gene therapy, and natural history.

---

### Query Commands

#### `list-diseases`
List all `rd-disease` entities in the knowledge graph.

#### `show-disease --id <id>`
Full disease profile: metadata, xrefs, causal/associated genes, notes, investigation.

#### `show-phenome --id <id> [--min-freq <tier>]`
Phenotypes grouped by frequency tier. Optional `--min-freq` filters to show only
phenotypes at or more frequent than the specified tier.

```bash
# All phenotypes
uv run python .claude/skills/rare-disease/rare_disease.py show-phenome --id $DISEASE_ID

# Only obligate + very-frequent + frequent
uv run python .claude/skills/rare-disease/rare_disease.py show-phenome --id $DISEASE_ID --min-freq frequent
```

#### `show-therapeutome --id <id>`
Drug targets (via causal genes), indicated drugs (direct), clinical trials, therapeutic notes.

#### `show-similar --id <id>`
Phenotypically similar diseases from SemSim, sorted by similarity score (desc).

#### `show-hierarchy --id <id>`
Parent MONDO classes (broader disease categories) and child classes (subtypes).

---

### Standard Commands

#### `list-artifacts [--disease <id>]`
List artifacts. If `--disease` specified, lists only artifacts linked to that disease.

#### `show-artifact --id <id>`
Get artifact content. Loads from cache if available, else inline.

#### `add-note --about <entity-id> --type <type> --content "..."`
Create an interpretive note about any entity. Note types:
- `disease-overview` — high-level disease summary
- `mechanism` — mechanism of harm (use `--mechanism-type`, `--functional-impact`)
- `phenotypic-spectrum` — phenotype variability analysis
- `diagnostic-criteria` — diagnostic criteria synthesis
- `differential` — differential diagnosis
- `therapeutic-landscape` — drug and trial landscape
- `expert-landscape` — research groups and experts
- `research-gaps` — open questions
- `natural-history` — progression, prognosis, survival
- `general` — uncategorized note

#### `tag --entity <id> --tag <name>`
Add a tag to any entity.

#### `search-tag --tag <name>`
Find all entities with a given tag.

---

## Sensemaking Workflows

### Mechanism Analysis

After running `ingest-genes`, ask Claude to analyze the MONDO record artifact:

1. `show-artifact --id <mondo-artifact-id>` to load the raw JSON
2. Ask: *"Based on this MONDO record and your knowledge of [gene], classify the mechanism
   of harm using the 4-category APM model: total-loss, partial-loss, gain-of-function,
   dominant-negative, or toxification. What is the functional impact?"*
3. Store with `add-note --type mechanism --mechanism-type total-loss --functional-impact absence`

### Therapeutic Landscape

After `ingest-drugs` + `ingest-clintrials`:

1. `show-therapeutome --id $DISEASE_ID` to get current landscape
2. Ask Claude: *"Analyze the drug targets and clinical trials for [disease]. What is the
   therapeutic rationale? Are there approved therapies? What are the most promising
   investigational approaches?"*
3. Store with `add-note --type therapeutic-landscape`

### Differential Diagnosis

After `ingest-similar`:

1. `show-similar --id $DISEASE_ID` to get phenotypically similar diseases
2. `show-phenome --id $DISEASE_ID --min-freq frequent` for core phenotype profile
3. Ask Claude: *"Compare the phenotype of [disease] to these similar diseases. What
   distinguishing features separate them? What diagnostic tests would differentiate?"*
4. Store with `add-note --type differential`

### Cross-Skill Integration with APM

When an APM case reaches a molecular diagnosis matching a MONDO disease:

```bash
# Check if the APM disease has a rare-disease profile
uv run python .claude/skills/rare-disease/rare_disease.py search-disease --query "<APM disease name>"

# If found, link the investigation for cross-context synthesis
uv run python .claude/skills/rare-disease/rare_disease.py show-therapeutome --id $DISEASE_ID
```

---

## Data Model

### Entity Types

| Type | Description | Key Attributes |
|------|-------------|----------------|
| `rd-disease` | Disease identified by MONDO | mondo-id, omim-id, orpha-id, inheritance-pattern, prevalence |
| `rd-gene` | Causal/associated gene | gene-symbol, hgnc-id, ensembl-id, entrez-id |
| `rd-protein` | Protein product | uniprot-id |
| `rd-phenotype` | HPO phenotype concept | hpo-id, hpo-label |
| `rd-drug` | Therapeutic compound | chembl-id, drugbank-id, drug-class, mechanism-of-action, development-stage |
| `rd-clinical-trial` | Clinical trial | nct-id, trial-phase, trial-status |
| `rd-disease-model` | Experimental model | model-type, model-species |
| `rd-biomarker` | Disease biomarker | biomarker-type |
| `rd-research-group` | Expert lab/group | — |

### Collection Types

| Type | Description |
|------|-------------|
| `rd-investigation` | Investigation container (owns investigation-status) |
| `rd-patient-cohort` | Set of patients sharing criteria |

### Relation Types

| Relation | Roles | Attributes |
|----------|-------|------------|
| `rd-disease-has-phenotype` | disease, phenotype | frequency-qualifier, evidence-code |
| `rd-gene-causes-disease` | gene, disease | confidence |
| `rd-gene-associated-with` | gene, disease | association-type, confidence |
| `rd-disease-subclass-of` | child-disease, parent-disease | — |
| `rd-disease-similar-to` | disease-a, disease-b | similarity-score |
| `rd-drug-targets` | drug, target-gene, target-protein | mechanism-of-action, confidence |
| `rd-drug-indicated-for` | drug, indication | development-stage, confidence |
| `rd-trial-studies` | trial, disease | — |
| `rd-biomarker-for` | biomarker, disease | biomarker-type |
| `rd-model-recapitulates` | model, disease | confidence |
| `rd-research-group-focuses-on` | research-group, disease | — |

---

## End-to-End Example: NGLY1 Deficiency

```bash
# 1. Find the disease
uv run python .claude/skills/rare-disease/rare_disease.py search-disease --query "NGLY1 deficiency"
# → MONDO:0800044

# 2. Initialize
uv run python .claude/skills/rare-disease/rare_disease.py init-disease --mondo-id "MONDO:0800044"
# → disease_id: rd-disease-<hash>

DISEASE_ID=rd-disease-<hash>

# 3. Ingest all
uv run python .claude/skills/rare-disease/rare_disease.py ingest-phenotypes --disease $DISEASE_ID
# → ~167 phenotypes (alacrima, global dev delay, seizures...)

uv run python .claude/skills/rare-disease/rare_disease.py ingest-genes --disease $DISEASE_ID
# → NGLY1 as causal gene (HGNC:17646)

uv run python .claude/skills/rare-disease/rare_disease.py ingest-hierarchy --disease $DISEASE_ID
# → congenital disorder of deglycosylation, rare disease (MONDO:0000001)

uv run python .claude/skills/rare-disease/rare_disease.py ingest-similar --disease $DISEASE_ID
# → similar diseases by HPO profile

uv run python .claude/skills/rare-disease/rare_disease.py ingest-clintrials --disease $DISEASE_ID
# → active trials (including Grace Science Foundation trial)

uv run python .claude/skills/rare-disease/rare_disease.py ingest-drugs --disease $DISEASE_ID
# → drug candidates targeting NGLY1

# 4. Build literature corpus
uv run python .claude/skills/rare-disease/rare_disease.py build-corpus --disease $DISEASE_ID
# → epmc-search commands to run

# 5. Query
uv run python .claude/skills/rare-disease/rare_disease.py show-disease --id $DISEASE_ID
uv run python .claude/skills/rare-disease/rare_disease.py show-phenome --id $DISEASE_ID --min-freq frequent
uv run python .claude/skills/rare-disease/rare_disease.py show-therapeutome --id $DISEASE_ID
```

---

## TypeDB Query Examples

```typeql
# Get all diseases with their causal genes
match
    $d isa rd-disease;
    (gene: $g, disease: $d) isa rd-gene-causes-disease;
fetch {
    "disease": $d.name,
    "mondo_id": $d.rd-mondo-id,
    "gene": $g.rd-gene-symbol
};

# Get phenotypes for a specific disease, sorted by frequency
match
    $d isa rd-disease, has rd-mondo-id "MONDO:0800044";
    (disease: $d, phenotype: $p) isa rd-disease-has-phenotype,
        has rd-frequency-qualifier $freq;
fetch {
    "hpo_id": $p.rd-hpo-id,
    "label": $p.rd-hpo-label,
    "frequency": $freq
};

# Find drugs targeting causal genes of a disease
match
    $d isa rd-disease, has id "<disease-id>";
    (gene: $g, disease: $d) isa rd-gene-causes-disease;
    (drug: $dr, target-gene: $g) isa rd-drug-targets;
fetch {
    "drug": $dr.name,
    "chembl_id": $dr.rd-chembl-id,
    "target_gene": $g.rd-gene-symbol,
    "moa": $dr.rd-mechanism-of-action
};
```

---

## API Rate Limits and Caching

- **Monarch API**: No authentication required. Reasonable rate limits for research use.
- **ClinicalTrials.gov**: Public API, no auth. 10 requests/second.
- **ChEMBL**: Public API, no auth. Responses > 50KB cached to `~/.alhazen/cache/json/`.

Large API responses (>50KB) are automatically cached to disk and referenced via
`cache-path` in TypeDB rather than stored inline.
