# alhazen-skill-examples

> [!IMPORTANT]
> **This repo is being phased out (June 2026).** Skillful Alhazen moved to a **per-repo database** architecture — each skill's data now lives in the repo that owns it. Four skills here have **migrated to dedicated repos** and are maintained there going forward:
>
> | Skill | New home | Shared database |
> |-------|----------|-----------------|
> | `scientific-literature` | [alhazen-skill-deep-research](https://github.com/sciknow-io/alhazen-skill-deep-research) | `alh_deep_research` |
> | `literature-trends` | [alhazen-skill-deep-research](https://github.com/sciknow-io/alhazen-skill-deep-research) | `alh_deep_research` |
> | `jobhunt` | [alhazen-skill-personal-assistant](https://github.com/sciknow-io/alhazen-skill-personal-assistant) | `alh_personal` |
> | `coach` | [alhazen-skill-personal-assistant](https://github.com/sciknow-io/alhazen-skill-personal-assistant) | `alh_personal` |
>
> **Please install these four from their new repos.** The copies here are frozen and no longer updated, but remain installable so existing setups don't break. The other example skills (`alg-precision-therapeutics`, `they-said-whaaa`) are unaffected and stay here as references.

Example skills for the [Skillful Alhazen](https://github.com/sciknow-io/skillful-alhazen) knowledge notebook framework — a TypeDB-powered scientific notebook for researchers building knowledge graphs from papers, notes, and domain data.

## What is this?

This repo serves two purposes:

1. **Claude Code plugin marketplace** — install skills directly into Claude Code (v1.0.33+) without a full Skillful Alhazen project. Each skill is a self-contained plugin with its own dependencies.
2. **Skillful Alhazen skills registry** — add skills to `skills-registry.yaml` in a Skillful Alhazen project and `make build-skills` wires them in.

---

## Skills

| Skill | Plugin type | Description |
|-------|-------------|-------------|
| [jobhunt](plugins/jobhunt/) ⚠️ **moved** | self-contained | Track job applications, identify skill gaps, plan learning — now in [alhazen-skill-personal-assistant](https://github.com/sciknow-io/alhazen-skill-personal-assistant) |
| [alhazen-core](skills/core/alhazen-core/) | infrastructure | Starts TypeDB, loads base schema — required by multi-plugin installs |
| [they-said-whaaa](skills/journalism/they-said-whaaa/) | standard | Credibility tracker — ingest YouTube + news, detect contradictions |
| [scientific-literature](skills/biomed/scientific-literature/) ⚠️ **moved** | standard | Multi-source literature search (EPMC, PubMed, OpenAlex, bioRxiv) — now in [alhazen-skill-deep-research](https://github.com/sciknow-io/alhazen-skill-deep-research) |
| [alg-precision-therapeutics](skills/biomed/alg-precision-therapeutics/) | standard | Rare disease mechanism investigation from a MONDO diagnosis |
| [literature-trends](skills/biomed/literature-trends/) ⚠️ **moved** | biomed | Trace hypothesis evolution across time windows in a literature cluster — now in [alhazen-skill-deep-research](https://github.com/sciknow-io/alhazen-skill-deep-research) |
| [coach](skills/health/coach/) ⚠️ **moved** | standard | Personal health & fitness monitoring — now in [alhazen-skill-personal-assistant](https://github.com/sciknow-io/alhazen-skill-personal-assistant) |

---

## Install via Claude Code Marketplace (recommended)

Requires Claude Code v1.0.33+. There are two plugin types with different install flows.

### Self-contained plugins (zero-setup)

Self-contained plugins bundle everything they need — including the TypeDB init logic and base schema. TypeDB starts automatically on every session start via a SessionStart hook. No manual init required.

**Currently available:** `jobhunt`

```
/plugin marketplace add sciknow-io/alhazen-skill-examples
/plugin install jobhunt@alhazen-skills
```

That's it. On the next session start, the SessionStart hook runs:
```bash
uv run --project <plugin-root>/skills/jobhunt python <plugin-root>/skills/jobhunt/alhazen_core.py init
```

This starts the TypeDB Docker container (pulling the image if needed), creates the `alhazen_notebook` database, and loads both the base schema and jobhunt's domain schema. Subsequent session starts complete in under a second.

Expected output on first run:
```json
{
  "success": true,
  "typedb": "running",
  "database": "alhazen_notebook",
  "database_created": true,
  "schema": "loaded",
  "extra_schema": "loaded",
  "message": "Alhazen core ready. Base schema and skill schema loaded."
}
```

Then use the skill:
```bash
uv run --project <skill-path> python <skill-path>/jobhunt.py list-pipeline
```

### Standard plugins (install alhazen-core first)

Standard plugins depend on the `alhazen-core` infrastructure plugin. Install it first, then install domain skills individually.

**Step 1 — Install the `alhazen-core` infrastructure plugin (from the skillful-alhazen marketplace):**
```
/plugin marketplace add sciknow-io/skillful-alhazen
/plugin install alhazen-core@skillful-alhazen
```

Initialize the infrastructure (one-time):
```
/alhazen-core:init
```

Expected output:
```json
{
  "success": true,
  "typedb": "running",
  "database": "alhazen_notebook",
  "schema": "loaded",
  "message": "Alhazen core ready."
}
```

**Step 2 — Add this marketplace and install a domain skill:**
```
/plugin marketplace add sciknow-io/alhazen-skill-examples
/plugin install they-said-whaaa@alhazen-skills
```

Then use it:
```bash
# Replace <skill-path> with your plugin cache path
# e.g. ~/.claude/plugins/cache/they-said-whaaa/
uv run --project <skill-path> python <skill-path>/they_said_whaaa.py list-figures
```

### Marketplace structure

The repo-level catalog is at [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).

**Self-contained plugin bundle** (`plugins/<name>/`):
```
plugins/<name>/
  .claude-plugin/
    plugin.json             # Plugin metadata (no "requires": ["alhazen-core"])
  hooks/
    hooks.json              # SessionStart hook: runs alhazen_core.py init
  skills/<name>/
    SKILL.md                # Loaded at startup: triggers, quick start
    USAGE.md                # Full reference: commands, workflows, data model
    <name>.py               # CLI entry point
    alhazen_core.py         # Bundled copy of alhazen-core init logic
    alhazen_notebook.tql    # Bundled copy of the base schema
    schema.tql              # This skill's domain schema (auto-loaded by init)
    pyproject.toml          # uv dependency declaration
```

**Standard skill** (`skills/<category>/<name>/`):
```
skills/<category>/<name>/
  .claude-plugin/
    plugin.json             # Includes "requires": {"plugins": ["alhazen-core"]}
  SKILL.md / USAGE.md / skill.yaml
  <name>.py / pyproject.toml / schema.tql
```

---

## Install via Skillful Alhazen (full project)

Add entries to `skillful-alhazen/skills-registry.yaml`:

```yaml
skills:
  - name: jobhunt
    git: https://github.com/sciknow-io/alhazen-skill-examples
    ref: main
    subdir: skills/demo/jobhunt

  - name: scientific-literature
    git: https://github.com/sciknow-io/alhazen-skill-examples
    ref: main
    subdir: skills/biomed/scientific-literature
```

Then build:

```bash
make build-skills   # clones skills into local_skills/, wires .claude/skills/ symlinks
make build-db       # loads all schemas (including new skill schemas) into TypeDB
```

In this mode, `make build-db` handles the base schema and all skill schemas automatically. The `alhazen-core` plugin is not needed.

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| [Docker](https://www.docker.com/) | Runs the TypeDB container |
| [uv](https://docs.astral.sh/uv/) | Runs skill Python CLIs with isolated deps |
| TypeDB 3.8.0+ | Launched by `alhazen-core init` or `make build-db` |

Optional per-skill:
- **they-said-whaaa**: `uv add youtube-transcript-api` for YouTube ingestion
- **scientific-literature**: `VOYAGE_API_KEY` + Qdrant for semantic search

---

## Skill File Structure

Every skill directory contains:

```
skills/<category>/<name>/
  SKILL.md          Slim discovery file (~30 lines): frontmatter, overview, triggers,
                    prerequisites, quick-start snippet, pointer to USAGE.md.
                    Loaded by Claude Code at startup for every conversation.
  USAGE.md          Full reference (read on demand): all commands, workflows,
                    data model, TypeDB patterns, sensemaking guidance, examples.
  skill.yaml        Structured manifest (name, description, operations, entity types)
  <name>.py         CLI entry point — self-contained, no skillful_alhazen package needed
  pyproject.toml    uv dependency declaration (run standalone with uv run --project .)
  schema.tql        TypeDB schema extension (sub-types of alhazen_notebook.tql)
  .claude-plugin/
    plugin.json     Claude Code marketplace metadata
```

**Why the SKILL.md / USAGE.md split?** Claude Code loads every `SKILL.md` into context at startup. Keeping them slim (~30 lines each) reduces static context overhead by ~90% vs. a single large file, while still giving Claude enough to select the right skill. Claude reads `USAGE.md` when it decides to actually use the skill.

**Self-contained CLIs:** Each skill's Python script includes all required utility functions inline (cache management, TypeQL helpers). `uv run --project <skill-dir>` installs only the skill's own deps — no `skillful_alhazen` package needed.

### `SKILL.md` format

```yaml
---
name: <skill-name>
description: <one-liner — when to use it, not just what it is>
---

# <Skill Name>

<2-3 sentences: what it does, when to use, Claude's role>

**Triggers:** <comma-separated trigger phrases>

## Prerequisites
...

## Quick Start
<2-4 key commands only — use <skill-path> placeholder>

**Before executing commands, read USAGE.md for the complete reference.**
```

### `plugin.json` format

```json
{
  "name": "<skill-name>",
  "display_name": "<Display Name>",
  "description": "<one-line description>",
  "version": "0.1.0",
  "license": "Apache-2.0",
  "requires": {
    "plugins": ["alhazen-core"],
    "system": {
      "bins": ["uv", "docker"],
      "description": "Run /alhazen-core:init first to set up TypeDB and base schema"
    }
  }
}
```

---

## Repo Structure

```
.claude-plugin/
  marketplace.json          # Repo-level plugin catalog

plugins/                    # Self-contained plugin bundles (zero-setup installs)
  jobhunt/                  # Self-contained jobhunt plugin
    .claude-plugin/
      plugin.json           # Standalone manifest (no alhazen-core dependency)
    hooks/
      hooks.json            # SessionStart hook: runs alhazen_core.py init
    skills/jobhunt/
      SKILL.md / USAGE.md   # Discovery and reference docs
      jobhunt.py            # CLI: ingest-job, list-pipeline, show-gaps, ...
      alhazen_core.py       # Bundled: TypeDB init logic
      alhazen_notebook.tql  # Bundled: base schema
      schema.tql            # jobhunt domain schema (auto-loaded by init)
      pyproject.toml / uv.lock

skills/                     # Canonical skill sources (standard plugins + skillful-alhazen)
  core/
    alhazen-core/           # Infrastructure: TypeDB setup + base schema
      alhazen_core.py       # CLI: init, status, reset
      alhazen_notebook.tql  # Base schema
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml
      .claude-plugin/plugin.json

  demo/
    jobhunt/                # Canonical jobhunt source (mirrored into plugins/jobhunt/)
      jobhunt.py            # CLI: ingest-job, list-pipeline, show-gaps, ...
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml / schema.tql
      .claude-plugin/plugin.json
      dashboard/            # Next.js components (for demo app)

  journalism/
    they-said-whaaa/        # Credibility and consistency tracker
      they_said_whaaa.py    # CLI: add-figure, ingest-youtube, add-claim, ...
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml / schema.tql
      .claude-plugin/plugin.json
      dashboard/

  biomed/
    scientific-literature/  # Multi-source literature search and ingestion
      scientific_literature.py  # CLI: search, ingest, embed, search-semantic, ...
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml / schema.tql
      .claude-plugin/plugin.json

    alg-precision-therapeutics/  # Rare disease investigation
      alg_precision_therapeutics.py  # CLI: init-investigation, ingest-disease, ...
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml / schema.tql
      .claude-plugin/plugin.json

    literature-trends/      # Abductive argumentation analysis
      literature_trends.py  # CLI: create-thread, record-hypothesis, show-thread, ...
      SKILL.md / USAGE.md / skill.yaml / pyproject.toml / schema.tql
      .claude-plugin/plugin.json

demo/                       # Shared Next.js base app
  docker-compose.yml        # Full stack: TypeDB + dashboard
  Dockerfile
  skills.config.ts          # Registry of installed skills for the demo
  src/app/                  # Hub page + skill pages
  src/lib/                  # Utility libraries
```

---

## Building a New Skill

See the [Alhazen Skill Architecture](https://github.com/sciknow-io/skillful-alhazen/wiki/Skill-Architecture) wiki for a full guide.

**Standard skill** (depends on alhazen-core):

1. Copy the template: `cp -r skills/_template skills/<category>/<skill-name>`
2. Write `SKILL.md` (triggers, prereqs, quick start, pointer to USAGE.md)
3. Write `USAGE.md` (all commands, workflows, data model)
4. Write `skill.yaml` (name, operations, entity types)
5. Write `<skill-name>.py` — **inline all utilities** (copy cache + escape_string blocks from an existing skill; no `skillful_alhazen` imports)
6. Write `schema.tql` — extend `domain-thing`, `artifact`, `note`, etc. from the base schema
7. Write `pyproject.toml` with direct deps (`typedb-driver>=3.8.0`, `requests`, etc.)
8. Write `.claude-plugin/plugin.json` with `"requires": {"plugins": ["alhazen-core"]}`
9. Add to `.claude-plugin/marketplace.json`

**Self-contained plugin** (zero-setup, TypeDB auto-inits):

Follow steps 1-9 above, then additionally:

10. Create `plugins/<skill-name>/` mirroring the structure of `plugins/jobhunt/`
11. Copy skill files into `plugins/<skill-name>/skills/<skill-name>/`
12. Copy `alhazen_core.py` and `alhazen_notebook.tql` from `skills/core/alhazen-core/` into that directory — `alhazen_core.py init` will auto-detect `schema.tql` alongside it and load both schemas
13. Write `plugins/<skill-name>/hooks/hooks.json` with the SessionStart hook pointing to the bundled `alhazen_core.py`
14. Write `plugins/<skill-name>/.claude-plugin/plugin.json` without the `alhazen-core` requirement
15. Update `.claude-plugin/marketplace.json` to point `source` at `plugins/<skill-name>`

The jobhunt skill is the reference implementation of the **curation pattern**:
1. **Foraging** — discover items of interest
2. **Ingestion** — fetch and store raw content
3. **Sensemaking** — Claude analyzes and annotates
4. **Analysis** — query across notes and entities
5. **Reporting** — dashboard views

---

## License

Apache-2.0
