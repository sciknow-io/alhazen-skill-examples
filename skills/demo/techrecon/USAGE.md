# Tech Recon — Usage Reference

## Web Interface

A Next.js dashboard is available for browsing investigations, systems, and architecture maps.

**Start the dashboard:**
```bash
make dashboard-dev    # starts on http://localhost:3000
```

**Views:**
- **Investigations** (`/techrecon`) — Grid of all active and completed investigations
- **System Detail** (`/techrecon/system/{id}`) — Full system profile: components, concepts, data models, notes
- **Architecture** (`/techrecon/architecture/{id}`) — Architecture map for a system
- **Investigation Detail** (`/techrecon/investigation/{id}`) — Investigation progress and linked systems
- **Artifact Viewer** (`/techrecon/artifact/{id}`) — Raw ingested content (READMEs, source, docs)

**Internal organization** (for contributors):
- Pages: `dashboard/src/app/(techrecon)/techrecon/`
- Components: `dashboard/src/components/techrecon/`
- API routes: `dashboard/src/app/api/techrecon/`
- TypeScript wrapper: `dashboard/src/lib/techrecon.ts`

---

## Starting an Investigation

**Triggers:** "investigate", "study", "research [system]", "look into", "tech recon"

### Start Investigation

```bash
uv run python .claude/skills/techrecon/techrecon.py start-investigation \
    --name "mediKanren Investigation" \
    --goal "Understand mediKanren's architecture and data model to inform APM skill design"
```

### Ingest a Repository

```bash
uv run python .claude/skills/techrecon/techrecon.py ingest-repo \
    --url "https://github.com/webyrd/mediKanren" \
    --investigation "investigation-abc123" \
    --tags "biomedical" "knowledge-graph" "reasoning"
```

This fetches:
- Repository metadata (stars, language, license)
- README content (stored as `techrecon-readme` artifact)
- File tree (stored as `techrecon-file-tree` artifact)
- Creates a `techrecon-system` entity with extracted metadata

---

## Sensemaking: Claude Analyzes Artifacts

### Get Artifacts

```bash
# List artifacts needing analysis
uv run python .claude/skills/techrecon/techrecon.py list-artifacts --status raw

# Read artifact content
uv run python .claude/skills/techrecon/techrecon.py show-artifact --id "artifact-xyz"
```

### Sensemaking Workflow

**When user says "analyze this system" or "make sense of [repo]":**

1. **Read the README artifact**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py show-artifact --id "artifact-readme-xyz"
   ```

2. **Read the file tree artifact**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py show-artifact --id "artifact-tree-xyz"
   ```

3. **Identify architectural components**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py add-component \
       --name "Query Engine" \
       --system "system-abc123" \
       --type "module" \
       --role "Processes miniKanren queries against biomedical knowledge graphs" \
       --file-path "medikanren2/"
   ```

4. **Identify key concepts**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py add-concept \
       --name "miniKanren" \
       --category "algorithm" \
       --description "Relational logic programming language for constraint-based reasoning"
   ```

5. **Link concepts to components**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py link-concept \
       --component "component-xyz" \
       --concept "concept-abc"
   ```

6. **Identify data models**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py add-data-model \
       --name "Biolink Model" \
       --system "system-abc123" \
       --format "RDF-OWL" \
       --description "Standardized biomedical knowledge representation"
   ```

7. **Create architecture note**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py add-note \
       --about "system-abc123" \
       --type architecture \
       --name "mediKanren Architecture Overview" \
       --content "Three-layer architecture: (1) Data ingestion from UMLS/SemMedDB/RTX-KG2... (2) Indexed graph store... (3) miniKanren query engine..."
   ```

8. **Create integration assessment**
   ```bash
   uv run python .claude/skills/techrecon/techrecon.py add-note \
       --about "system-abc123" \
       --type integration \
       --name "Integration with APM Skill" \
       --content "mediKanren's drug repurposing queries could power APM Phase 2..." \
       --priority high \
       --complexity moderate
   ```

---

## Deep Investigation: Source Code Analysis

```bash
# Ingest a key source file
uv run python .claude/skills/techrecon/techrecon.py ingest-source \
    --url "https://github.com/webyrd/mediKanren/blob/master/medikanren2/neo/dbKanren/dbk/index.rkt" \
    --file-path "medikanren2/neo/dbKanren/dbk/index.rkt" \
    --language "Racket" \
    --system "system-abc123"

# Ingest documentation
uv run python .claude/skills/techrecon/techrecon.py ingest-doc \
    --url "https://biolink.github.io/biolink-model/" \
    --system "system-abc123" \
    --tags "data-model" "biolink"

# Ingest a schema file
uv run python .claude/skills/techrecon/techrecon.py ingest-schema \
    --url "https://github.com/biolink/biolink-model/blob/master/biolink-model.yaml" \
    --format "custom" \
    --system "system-abc123"

# Ingest a HuggingFace model card
uv run python .claude/skills/techrecon/techrecon.py ingest-model-card \
    --model-id "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract" \
    --system "system-abc123"
```

### Extracting Code Snippets

```bash
uv run python .claude/skills/techrecon/techrecon.py add-fragment \
    --type code-snippet \
    --source "artifact-xyz" \
    --about "component-abc" \
    --language "Racket" \
    --name "Query pattern for drug-disease paths" \
    --content "(run* (drug disease) (fresh (gene) (edge drug gene 'treats') (edge gene disease 'causes')))"
```

---

## Queries

```bash
uv run python .claude/skills/techrecon/techrecon.py list-systems
uv run python .claude/skills/techrecon/techrecon.py show-system --id "system-abc123"
uv run python .claude/skills/techrecon/techrecon.py show-architecture --id "system-abc123"
uv run python .claude/skills/techrecon/techrecon.py show-component --id "component-xyz"
uv run python .claude/skills/techrecon/techrecon.py show-concept --id "concept-xyz"
uv run python .claude/skills/techrecon/techrecon.py show-data-model --id "datamodel-xyz"
```

---

## Tagging

```bash
uv run python .claude/skills/techrecon/techrecon.py tag \
    --entity "system-abc123" --tag "biomedical"

uv run python .claude/skills/techrecon/techrecon.py search-tag --tag "biomedical"
```

**Common tag patterns:**
- `domain:biomedical`, `domain:nlp`, `domain:knowledge-graph`
- `lang:python`, `lang:racket`, `lang:rust`
- `status:deep-dive`, `status:surveyed`, `status:rejected`
- `integration:high-priority`, `integration:blocked`
- `relates-to:apm`, `relates-to:jobhunt`

---

## Data Model

### Entity Types

| Type | Description |
|------|-------------|
| `techrecon-investigation` | An investigation (collection) |
| `techrecon-system` | Software system/library/framework |
| `techrecon-component` | Module/subsystem |
| `techrecon-concept` | Key concept/pattern/algorithm |
| `techrecon-data-model` | Data model/schema/ontology |

### Artifact Types

| Type | Description |
|------|-------------|
| `techrecon-readme` | Repository README |
| `techrecon-source-file` | Source code file |
| `techrecon-doc-page` | Documentation page |
| `techrecon-schema-file` | Schema/model definition |
| `techrecon-model-card` | HuggingFace model card |
| `techrecon-file-tree` | Repository file tree |

### Fragment Types

| Type | Description |
|------|-------------|
| `techrecon-code-snippet` | Extracted code snippet |
| `techrecon-api-spec` | API specification excerpt |
| `techrecon-schema-excerpt` | Schema excerpt |
| `techrecon-config-excerpt` | Config file excerpt |

### Note Types

| Type | Purpose |
|------|---------|
| `techrecon-architecture-note` | System architecture analysis |
| `techrecon-design-pattern-note` | Design pattern analysis |
| `techrecon-integration-note` | Integration assessment (has priority, complexity) |
| `techrecon-comparison-note` | Cross-system comparison |
| `techrecon-data-model-note` | Data model analysis |
| `techrecon-assessment-note` | Overall system assessment |

### Relations

| Relation | Description |
|----------|-------------|
| `techrecon-has-component` | System contains component |
| `techrecon-uses-concept` | Component uses concept |
| `techrecon-has-data-model` | System uses data model |
| `techrecon-system-dependency` | System depends on system |
| `techrecon-component-dependency` | Component depends on component |

---

## Command Reference

| Command | Description | Key Args |
|---------|-------------|----------|
| `start-investigation` | Start investigation | `--name`, `--goal` |
| `list-investigations` | List investigations | `--status` |
| `update-investigation` | Update status | `--id`, `--status` |
| `add-system` | Add system | `--name`, `--repo-url` |
| `add-component` | Add component | `--name`, `--system`, `--type` |
| `add-concept` | Add concept | `--name`, `--category` |
| `add-data-model` | Add data model | `--name`, `--format` |
| `ingest-repo` | Ingest GitHub repo | `--url` |
| `ingest-doc` | Ingest doc page | `--url` |
| `ingest-source` | Ingest source file | `--url`, `--language` |
| `ingest-schema` | Ingest schema file | `--url`/`--file`, `--format` |
| `ingest-model-card` | Ingest HF model | `--model-id` |
| `link-component` | Link component | `--system`, `--component` |
| `link-concept` | Link concept | `--component`, `--concept` |
| `link-data-model` | Link data model | `--system`, `--data-model` |
| `link-dependency` | Link dependency | `--system`, `--dependency` |
| `list-systems` | List systems | |
| `show-system` | System details | `--id` |
| `show-architecture` | Architecture map | `--id` |
| `list-artifacts` | List artifacts | `--status`, `--system`, `--type` |
| `show-artifact` | Artifact content | `--id` |
| `add-note` | Add note | `--about`, `--type`, `--content` |
| `add-fragment` | Add fragment | `--type`, `--content`, `--source` |
| `tag` | Tag entity | `--entity`, `--tag` |
| `search-tag` | Search by tag | `--tag` |

---

## Cross-Skill Integration

### TechRecon + APM
Investigating biomedical tools (mediKanren, Monarch, OpenTargets) to inform APM skill's knowledge base sources and reasoning approaches.

### TechRecon + EPMC Search
Papers about tools can be searched via epmc-search, then linked to techrecon systems via tags or notes.

---

## TypeDB Reference

- **TechRecon Schema:** `local_resources/typedb/namespaces/techrecon.tql`
- **Core Schema:** `local_resources/typedb/alhazen_notebook.tql`

### Common Pitfalls (TypeDB 3.x)

- **Fetch syntax** — Use `fetch { "key": $var.attr };` (JSON-style)
- **No sessions** — Use `driver.transaction(database, TransactionType.X)` directly
- **Update = delete + insert** — Can't modify attributes in place
