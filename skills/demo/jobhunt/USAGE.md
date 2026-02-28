# Job Hunting Notebook — Usage Reference

## Web Interface

A Next.js dashboard is available for visualizing your job search pipeline.

**Start the dashboard:**
```bash
make dashboard-dev    # starts on http://localhost:3000
```

**Views:**
- **Pipeline Board** (`/jobhunt`) — Kanban columns by application status
- **Position Detail** (`/jobhunt/position/{id}`) — Full position profile: requirements, notes, gap analysis, fit score
- **Collection Detail** (`/jobhunt/collection/{id}`) — Notes and resources grouped by collection

**Internal organization** (for contributors):
- Pages: `dashboard/src/app/(jobhunt)/jobhunt/`
- Components: `dashboard/src/components/jobhunt/`
- API routes: `dashboard/src/app/api/jobhunt/`
- TypeScript wrapper: `dashboard/src/lib/jobhunt.ts`

---

## Your Skill Profile

Before analyzing jobs, set up your skill profile for gap analysis.

### Add Your Skills

```bash
uv run python .claude/skills/jobhunt/jobhunt.py add-skill \
    --name "Python" --level "strong"

uv run python .claude/skills/jobhunt/jobhunt.py add-skill \
    --name "Distributed Systems" --level "some" \
    --description "Built caching layer, some k8s experience"

uv run python .claude/skills/jobhunt/jobhunt.py add-skill \
    --name "Rust" --level "learning"
```

**Skill levels:** `strong` | `some` | `learning` | `none`

### View Your Skills

```bash
uv run python .claude/skills/jobhunt/jobhunt.py list-skills
```

---

## Ingestion: Adding Job Postings

### From URL

**Triggers:** "add job", "ingest job", "new position", "found a job posting", "here's a job"

```bash
uv run python .claude/skills/jobhunt/jobhunt.py ingest-job \
    --url "https://boards.greenhouse.io/anthropic/jobs/123456" \
    --priority high \
    --tags "ai" "ml" "safety"
```

**Options:**
- `--url` (required): Job posting URL
- `--priority`: Set priority (high/medium/low)
- `--tags`: Space-separated tags

**Returns:**
```json
{
  "success": true,
  "position_id": "position-abc123",
  "artifact_id": "artifact-xyz789",
  "status": "raw",
  "message": "Artifact stored - ask Claude to 'analyze this job posting' for sensemaking."
}
```

---

## Sensemaking: Claude Analyzes Artifacts

### List Artifacts Needing Analysis

```bash
uv run python .claude/skills/jobhunt/jobhunt.py list-artifacts --status raw
uv run python .claude/skills/jobhunt/jobhunt.py list-artifacts --status all
```

### Get Artifact Content

```bash
uv run python .claude/skills/jobhunt/jobhunt.py show-artifact --id "artifact-xyz789"
```

### Sensemaking Workflow

**When user says "analyze this job posting" or "make sense of [position]":**

1. **Get the artifact content**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py show-artifact --id "artifact-xyz"
   ```

2. **Read and comprehend the content**
   - Look for: company name, job title, location, salary, remote policy
   - Identify: requirements, responsibilities, qualifications
   - Note: team info, culture signals, growth opportunities

3. **Create/update the company**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py add-company \
       --name "Anthropic" \
       --url "https://anthropic.com" \
       --description "AI safety research company"
   ```

4. **Extract requirements as fragments**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py add-requirement \
       --position "position-abc123" \
       --skill "Python" \
       --level "required" \
       --your-level "strong" \
       --content "5+ years Python experience, focus on ML systems"
   ```

5. **Create analysis notes**

   **Fit Analysis Note:**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py add-note \
       --about "position-abc123" \
       --type fit-analysis \
       --content "Strong fit for core requirements. Gap in distributed systems." \
       --fit-score 0.82 \
       --fit-summary "Strong technical fit, one gap to address"
   ```

   **Research Note:**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py add-note \
       --about "company-xyz" \
       --type research \
       --content "Series C, $4B raised. Strong safety focus."
   ```

   **Skill Gap Note:**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py add-note \
       --about "position-abc123" \
       --type skill-gap \
       --content "Distributed systems is required. Recommend: DDIA book, MIT 6.824 course."
   ```

6. **Flag uncertainties**
   ```bash
   uv run python .claude/skills/jobhunt/jobhunt.py tag \
       --entity "requirement-xyz" \
       --tag "uncertain"
   ```

7. **Report findings to user**: company overview, fit score breakdown, key gaps, suggested next steps

---

## Application Tracking

### Update Status

```bash
uv run python .claude/skills/jobhunt/jobhunt.py update-status \
    --position "position-abc123" \
    --status "applied" \
    --date "2025-02-05"
```

**Status values:** `researching` | `applied` | `phone-screen` | `interviewing` | `offer` | `rejected` | `withdrawn`

### Add Notes

```bash
# Interaction note
uv run python .claude/skills/jobhunt/jobhunt.py add-note \
    --about "position-abc123" \
    --type interaction \
    --content "Phone screen went well, moving to technical round." \
    --interaction-type "call" \
    --interaction-date "2025-02-05"

# Strategy note
uv run python .claude/skills/jobhunt/jobhunt.py add-note \
    --about "position-abc123" \
    --type strategy \
    --content "Lead with distributed systems experience from caching project."
```

**Note types:** `research` | `strategy` | `interview` | `interaction` | `skill-gap` | `fit-analysis` | `general`

### Add Learning Resources

```bash
uv run python .claude/skills/jobhunt/jobhunt.py add-resource \
    --name "Designing Data-Intensive Applications" \
    --type "book" \
    --url "https://dataintensive.net" \
    --hours 30 \
    --skills "distributed-systems" "system-design"
```

---

## Query Commands

```bash
# All positions
uv run python .claude/skills/jobhunt/jobhunt.py list-pipeline

# Filter
uv run python .claude/skills/jobhunt/jobhunt.py list-pipeline --status "interviewing"
uv run python .claude/skills/jobhunt/jobhunt.py list-pipeline --priority "high"

# Details
uv run python .claude/skills/jobhunt/jobhunt.py show-position --id "position-abc123"
uv run python .claude/skills/jobhunt/jobhunt.py show-company --id "company-xyz"
uv run python .claude/skills/jobhunt/jobhunt.py show-gaps
uv run python .claude/skills/jobhunt/jobhunt.py learning-plan
```

---

## Reports (Markdown Output)

```bash
uv run python .claude/skills/jobhunt/jobhunt.py report-pipeline   # Pipeline overview
uv run python .claude/skills/jobhunt/jobhunt.py report-stats      # Stats summary
uv run python .claude/skills/jobhunt/jobhunt.py report-gaps       # Skill gaps
uv run python .claude/skills/jobhunt/jobhunt.py report-position --id "position-xyz"  # Position detail
```

Use reports (Markdown) for displaying to users in chat. Use JSON commands (`list-pipeline`, `show-position`) for programmatic processing.

---

## Automated Foraging (Job Forager)

Automates discovery by searching job boards and aggregators, filtered by your skill profile.

### Setup: Add Search Sources

```bash
# Company board sources
uv run python .claude/skills/jobhunt/job_forager.py add-source \
    --name "Anthropic" --platform greenhouse --token anthropic

# Aggregator sources
uv run python .claude/skills/jobhunt/job_forager.py add-source \
    --name "ML Jobs" --platform linkedin --query "machine learning" --location "San Francisco"
uv run python .claude/skills/jobhunt/job_forager.py add-source \
    --name "Remote ML" --platform remotive --query "machine learning"
```

### Search and Heartbeat

```bash
# Search one source
uv run python .claude/skills/jobhunt/job_forager.py search-source --source "ML Jobs"

# Full heartbeat: search all sources, filter, dedup, store
uv run python .claude/skills/jobhunt/job_forager.py heartbeat --min-relevance 0.1
```

### Triage Candidates

```bash
uv run python .claude/skills/jobhunt/job_forager.py list-candidates --status new
uv run python .claude/skills/jobhunt/job_forager.py triage --id candidate-abc123 --action reviewed
uv run python .claude/skills/jobhunt/job_forager.py promote --id candidate-abc123
```

### Platform Details

| Platform | Type | Auth | Args |
|----------|------|------|------|
| `greenhouse` | Company board | None | `--token` (slug) |
| `lever` | Company board | None | `--token` (slug) |
| `ashby` | Company board | None | `--token` (slug) |
| `linkedin` | Aggregator | None | `--query`, `--location` |
| `remotive` | Aggregator | None | `--query`, `--location` |
| `adzuna` | Aggregator | API key | `--query`, `--location` |

### Forager Command Reference

| Command | Description | Key Args |
|---------|-------------|----------|
| `add-source` | Add a search source | `--name`, `--platform`, `--token`/`--query` |
| `list-sources` | List search sources | |
| `remove-source` | Remove a source | `--id`, `--token`, or `--name` |
| `suggest-sources` | Profile-driven suggestions | |
| `search-source` | Search one source | `--source` |
| `heartbeat` | Full discovery cycle | `--min-relevance` |
| `list-candidates` | List candidates | `--status`, `--source` |
| `triage` | Review/dismiss candidate | `--id`, `--action` |
| `promote` | Promote to position | `--id` |

---

## Cross-Skill Integration

### Link Literature to Learning Plan

```bash
# Search for papers on a skill gap topic
uv run python .claude/skills/epmc-search/epmc_search.py search \
    --query "machine learning systems design" \
    --collection "ML Systems Reading List"

# Link collection to skill gap
uv run python .claude/skills/jobhunt/jobhunt.py link-collection \
    --collection "<collection-id>" \
    --skill "machine-learning"

# View updated plan
uv run python .claude/skills/jobhunt/jobhunt.py learning-plan
```

---

## Data Model

### Entity Types

| Type | Description |
|------|-------------|
| `your-skill` | Your skills for gap analysis |
| `jobhunt-company` | An employer organization |
| `jobhunt-position` | A specific job posting |
| `jobhunt-learning-resource` | Course, book, tutorial |
| `jobhunt-contact` | Person at a company |
| `jobhunt-search-source` | Company board for forager |
| `jobhunt-candidate` | Discovered posting (forager) |

### Note Types

| Type | Purpose |
|------|---------|
| `jobhunt-application-note` | Status tracking |
| `jobhunt-research-note` | Company research |
| `jobhunt-interview-note` | Interview prep/feedback |
| `jobhunt-strategy-note` | Talking points, approach |
| `jobhunt-skill-gap-note` | Learning needs |
| `jobhunt-fit-analysis-note` | Fit assessment |
| `jobhunt-interaction-note` | Contact logs |

---

## Command Reference

| Command | Description | Key Args |
|---------|-------------|----------|
| `ingest-job` | Fetch job URL, store raw | `--url` |
| `add-skill` | Add to your skill profile | `--name`, `--level` |
| `list-skills` | Show your skills | |
| `list-artifacts` | List artifacts by status | `--status` |
| `show-artifact` | Get artifact content | `--id` |
| `add-company` | Add company | `--name` |
| `add-position` | Add position manually | `--title` |
| `add-requirement` | Add skill requirement | `--position`, `--skill` |
| `update-status` | Change application status | `--position`, `--status` |
| `add-note` | Create any note type | `--about`, `--type`, `--content` |
| `add-resource` | Add learning resource | `--name`, `--type` |
| `link-collection` | Link paper collection to skill gap | `--collection`, `--skill` |
| `link-paper` | Link resource to paper | `--resource`, `--paper` |
| `list-pipeline` | Show applications | `--status`, `--priority` |
| `show-position` | Position details | `--id` |
| `show-company` | Company details | `--id` |
| `show-gaps` | Skill gap analysis | |
| `learning-plan` | Prioritized study list | |
| `tag` | Tag an entity | `--entity`, `--tag` |
| `search-tag` | Find by tag | `--tag` |
| `report-pipeline` | Pipeline overview (Markdown) | |
| `report-stats` | Stats summary (Markdown) | |
| `report-gaps` | Skill gaps report (Markdown) | |
| `report-position` | Position detail (Markdown) | `--id` |

---

## TypeDB Reference

- **JobHunt Schema:** `local_resources/typedb/namespaces/jobhunt.tql`
- **Core Schema:** `local_resources/typedb/alhazen_notebook.tql`

### Common Pitfalls (TypeDB 3.x)

- **Fetch syntax** — Use `fetch { "key": $var.attr };` (JSON-style)
- **No sessions** — Use `driver.transaction(database, TransactionType.X)` directly
- **Update = delete + insert** — Can't modify attributes in place
