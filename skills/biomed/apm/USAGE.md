# Algorithm for Precision Medicine (APM) — Usage Reference

## Starting an Investigation

### Create a Case

**Triggers:** "new case", "investigate patient", "start APM", "rare disease case"

```bash
uv run python .claude/skills/apm/apm.py add-case \
    --name "NGLY1 Patient Case" \
    --diagnostic-status "unsolved" \
    --phase "diagnostic"
```

### Add Phenotypes

```bash
uv run python .claude/skills/apm/apm.py add-phenotype \
    --hpo-id "HP:0000522" --label "Alacrima" \
    --onset "infantile" --severity "severe"

uv run python .claude/skills/apm/apm.py add-phenotype \
    --hpo-id "HP:0001250" --label "Seizures"
```

### Link Phenotypes to Case

```bash
uv run python .claude/skills/apm/apm.py link-case-phenotype \
    --case "<case-id>" --phenotype "<phenotype-id>" \
    --onset "infantile" --severity "severe"
```

### Add Genes and Variants

```bash
uv run python .claude/skills/apm/apm.py add-gene \
    --symbol "NGLY1" --entrez-id "55768" --ensembl-id "ENSG00000151092"

uv run python .claude/skills/apm/apm.py add-variant \
    --gene "<gene-id>" \
    --hgvs-c "c.1201A>T" --hgvs-p "p.Arg401Ter" \
    --acmg-class "pathogenic" --zygosity "compound-het"
```

### Add Disease

```bash
uv run python .claude/skills/apm/apm.py add-disease \
    --name "NGLY1 deficiency" \
    --omim-id "615273" \
    --inheritance "autosomal-recessive"
```

---

## Ingestion: Storing Evidence

```bash
# Ingest sequencing report (PDF)
uv run python .claude/skills/apm/apm.py ingest-report \
    --file /path/to/exome_report.pdf \
    --name "Exome Sequencing Report"

# ClinVar record
uv run python .claude/skills/apm/apm.py ingest-record \
    --type clinvar --source-id "VCV000012345" \
    --url "https://www.ncbi.nlm.nih.gov/clinvar/variation/12345/"

# OMIM record
uv run python .claude/skills/apm/apm.py ingest-record \
    --type omim --source-id "615273" \
    --url "https://omim.org/entry/615273"
```

---

## Sensemaking: Claude Analyzes Evidence

### List Artifacts Needing Analysis

```bash
uv run python .claude/skills/apm/apm.py list-artifacts --status raw
```

### Get Artifact Content

```bash
uv run python .claude/skills/apm/apm.py show-artifact --id "<artifact-id>"
```

### Sensemaking Workflow

**When user says "analyze this report" or "make sense of [artifact]":**

1. **Get the artifact content**
   ```bash
   uv run python .claude/skills/apm/apm.py show-artifact --id "<artifact-id>"
   ```

2. **Read and extract clues**
   - From sequencing reports: variant calls, phenotype features
   - From ClinVar: pathogenicity evidence, ACMG criteria
   - From OMIM: disease descriptions, inheritance patterns
   - From papers: mechanism claims, functional data

3. **Promote fragments to Things** (when a variant is confirmed significant)
   ```bash
   uv run python .claude/skills/apm/apm.py add-variant \
       --gene "<gene-id>" --hgvs-c "c.1201A>T" \
       --acmg-class "pathogenic"
   ```

4. **Build the diagnostic chain**
   ```bash
   uv run python .claude/skills/apm/apm.py link-case-variant \
       --case "<case-id>" --variant "<variant-id>" --zygosity "compound-het"

   uv run python .claude/skills/apm/apm.py link-variant-gene \
       --variant "<variant-id>" --gene "<gene-id>"

   uv run python .claude/skills/apm/apm.py link-variant-disease \
       --variant "<variant-id>" --disease "<disease-id>" \
       --acmg-class "pathogenic" --confidence 0.95

   uv run python .claude/skills/apm/apm.py link-case-diagnosis \
       --case "<case-id>" --disease "<disease-id>" \
       --status "confirmed" --confidence 0.9
   ```

5. **Create interpretive notes**

   **Variant Interpretation Note (ACMG):**
   ```bash
   uv run python .claude/skills/apm/apm.py add-note \
       --about "<variant-id>" \
       --type variant-interpretation \
       --content "Pathogenic. PS1: same AA change known pathogenic. PM2: absent from gnomAD. PP3: PolyPhen2 damaging." \
       --acmg-class "pathogenic" \
       --acmg-criteria "PS1,PM2,PP3"
   ```

   **Diagnosis Hypothesis Note:**
   ```bash
   uv run python .claude/skills/apm/apm.py add-note \
       --about "<case-id>" \
       --type diagnosis-hypothesis \
       --content "Compound heterozygous LOF mutations in NGLY1. Phenotype matches: alacrima, seizures, developmental delay." \
       --diagnostic-status "confirmed" \
       --acmg-class "pathogenic"
   ```

   **Mechanism Analysis Note (bridges Phase 1 → Phase 2):**
   ```bash
   uv run python .claude/skills/apm/apm.py add-note \
       --about "<gene-id>" \
       --type mechanism-analysis \
       --content "Total loss of NGLY1 function. Both alleles carry LOF mutations. PNGase activity absent, ERAD pathway dysfunction." \
       --mechanism-type "total-loss" \
       --functional-impact "absence"
   ```

   **Therapeutic Strategy Note:**
   ```bash
   uv run python .claude/skills/apm/apm.py add-note \
       --about "<case-id>" \
       --type therapeutic-strategy \
       --content "Absence of enzyme function suggests compensation: ERT, gene therapy, or substrate reduction therapy." \
       --therapeutic-approach "ERT" \
       --functional-impact "absence"
   ```

6. **Build the therapeutic chain**
   ```bash
   uv run python .claude/skills/apm/apm.py link-mechanism \
       --variant "<variant-id>" --gene "<gene-id>" \
       --mechanism-type "total-loss" --functional-impact "absence"

   uv run python .claude/skills/apm/apm.py link-gene-protein \
       --gene "<gene-id>" --protein "<protein-id>"

   uv run python .claude/skills/apm/apm.py link-drug-target \
       --drug "<drug-id>" --gene "<gene-id>" \
       --approach "gene-therapy"
   ```

7. **Report findings**: diagnostic chain, ACMG evidence, mechanism, therapeutic options

---

## Query Commands

```bash
uv run python .claude/skills/apm/apm.py show-case --id "<case-id>"
uv run python .claude/skills/apm/apm.py list-cases
uv run python .claude/skills/apm/apm.py list-cases --status "unsolved"
uv run python .claude/skills/apm/apm.py show-diagnostic-chain --case "<case-id>"
uv run python .claude/skills/apm/apm.py show-therapeutic-chain --case "<case-id>"
uv run python .claude/skills/apm/apm.py list-genes
uv run python .claude/skills/apm/apm.py list-variants
uv run python .claude/skills/apm/apm.py list-diseases
uv run python .claude/skills/apm/apm.py list-phenotypes
uv run python .claude/skills/apm/apm.py list-drugs
```

---

## Data Model

### Entity Types (Things)

| Type | Description |
|------|-------------|
| `apm-case` | Patient investigation |
| `apm-gene` | Gene implicated in investigation |
| `apm-variant` | Specific genomic variant |
| `apm-disease` | Disease or condition |
| `apm-phenotype` | Clinical phenotype (HPO concept) |
| `apm-protein` | Protein product |
| `apm-pathway` | Biological pathway |
| `apm-drug` | Therapeutic compound |
| `apm-disease-model` | Experimental model system |
| `apm-assay` | Functional test |

### Artifact Types

| Type | Description |
|------|-------------|
| `apm-sequencing-report` | Clinical WES/WGS report |
| `apm-clinvar-record` | ClinVar entry |
| `apm-omim-record` | OMIM entry |
| `apm-gnomad-record` | Population frequency data |
| `apm-prediction-record` | In silico prediction |
| `apm-drug-record` | DrugBank/ChEMBL entry |

### Note Types

| Type | Purpose |
|------|---------|
| `apm-diagnosis-hypothesis-note` | Candidate diagnosis |
| `apm-variant-interpretation-note` | ACMG classification |
| `apm-mechanism-analysis-note` | Variant → disease mechanism |
| `apm-therapeutic-strategy-note` | Treatment strategy |
| `apm-phenotype-genotype-note` | Symptom-gene links |
| `apm-reanalysis-note` | Re-analysis attempts |
| `apm-cross-case-synthesis-note` | Cross-case findings |
| `apm-screening-analysis-note` | Drug screening analysis |

### Key Relations

| Relation | Purpose |
|----------|---------|
| `apm-case-has-phenotype` | Patient presents symptom |
| `apm-case-has-variant` | Patient carries variant |
| `apm-case-has-diagnosis` | Working/confirmed diagnosis |
| `apm-variant-in-gene` | Variant location |
| `apm-variant-pathogenicity` | Variant causes disease |
| `apm-mechanism-of-harm` | How variant disrupts function |
| `apm-gene-encodes` | Gene → protein |
| `apm-drug-target` | Drug acts on target |
| `apm-drug-indication` | Drug treats disease |

---

## Command Reference

| Command | Description | Key Args |
|---------|-------------|----------|
| `add-case` | Create investigation case | `--name`, `--diagnostic-status` |
| `add-gene` | Add gene | `--symbol`, `--entrez-id` |
| `add-variant` | Add variant | `--gene`, `--hgvs-c`, `--acmg-class` |
| `add-disease` | Add disease | `--name`, `--omim-id` |
| `add-phenotype` | Add HPO phenotype | `--hpo-id`, `--label` |
| `add-protein` | Add protein | `--name`, `--uniprot-id` |
| `add-drug` | Add drug | `--name`, `--drugbank-id` |
| `ingest-report` | Ingest sequencing report | `--file`, `--name` |
| `ingest-record` | Ingest database record | `--type`, `--url` |
| `link-case-phenotype` | Link phenotype to case | `--case`, `--phenotype` |
| `link-case-variant` | Link variant to case | `--case`, `--variant` |
| `link-case-diagnosis` | Link diagnosis to case | `--case`, `--disease` |
| `link-variant-gene` | Link variant to gene | `--variant`, `--gene` |
| `link-variant-disease` | Variant pathogenicity | `--variant`, `--disease` |
| `link-mechanism` | Mechanism of harm | `--variant`, `--gene` |
| `link-gene-protein` | Gene encodes protein | `--gene`, `--protein` |
| `link-drug-target` | Drug targets gene/protein | `--drug`, `--gene` |
| `add-note` | Create any note type | `--about`, `--type`, `--content` |
| `show-case` | Full case details | `--id` |
| `show-diagnostic-chain` | Diagnostic reasoning chain | `--case` |
| `show-therapeutic-chain` | Therapeutic reasoning chain | `--case` |
| `list-cases` | List investigations | `--status` |
| `list-artifacts` | List artifacts | `--status` |
| `show-artifact` | Artifact content | `--id` |
| `tag` | Tag an entity | `--entity`, `--tag` |
| `search-tag` | Find by tag | `--tag` |

---

## Cross-Skill Integration

- **Literature**: Use `epmc-search` to find papers about genes/variants/diseases. Link to investigation collection via `collection-membership`.
- **Collections**: Each investigation is a `Collection`. Use sub-collections for Phase 1 (Diagnostic) and Phase 2 (Therapeutic).

---

## TypeDB Reference

- **APM Schema:** `local_resources/typedb/namespaces/apm.tql`
- **Core Schema:** `local_resources/typedb/alhazen_notebook.tql`

### Common Pitfalls (TypeDB 3.x)

- **Fetch syntax** — Use `fetch { "key": $var.attr };` (JSON-style)
- **No sessions** — Use `driver.transaction(database, TransactionType.X)` directly
- **Update = delete + insert** — Can't modify attributes in place
