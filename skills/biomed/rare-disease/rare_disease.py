#!/usr/bin/env python3
"""
Rare Disease Investigation CLI - MONDO-based disease knowledge graph builder.

This script handles INGESTION and QUERIES. Claude handles SENSEMAKING via SKILL.md.

Usage:
    python .claude/skills/rare-disease/rare_disease.py <command> [options]

Commands:
    # Disease Discovery
    search-disease      Search Monarch Initiative for diseases by name
    init-disease        Initialize disease KG from MONDO ID

    # Ingestion (Monarch + external APIs -> TypeDB)
    ingest-phenotypes   Ingest HPO phenotype associations from Monarch
    ingest-genes        Ingest causal and correlated gene associations from Monarch
    ingest-hierarchy    Ingest disease hierarchy (MONDO subclass-of relations)
    ingest-similar      Ingest phenotypically similar diseases via Monarch SemSim
    ingest-clintrials   Ingest clinical trials from ClinicalTrials.gov
    ingest-drugs        Ingest drug candidates from ChEMBL (per causal gene)

    # Sensemaking Scaffold
    build-corpus        Print ready-to-run epmc-search CLI commands

    # Queries
    list-diseases       List all rd-disease entities
    show-disease        Full disease profile (metadata, genes, inheritance, xrefs)
    show-phenome        Phenotypes grouped by frequency tier
    show-therapeutome   Drugs, clinical trials, and therapeutic notes
    show-similar        Phenotypically similar diseases with scores
    show-hierarchy      Parent MONDO classes

    # Standard
    list-artifacts      List artifacts (optionally filtered by disease)
    show-artifact       Get artifact content for sensemaking
    add-note            Create a note about any entity
    tag                 Tag an entity
    search-tag          Search entities by tag

Environment:
    TYPEDB_HOST       TypeDB server host (default: localhost)
    TYPEDB_PORT       TypeDB server port (default: 1729)
    TYPEDB_DATABASE   Database name (default: alhazen_notebook)
    TYPEDB_USERNAME   TypeDB username (default: admin)
    TYPEDB_PASSWORD   TypeDB password (default: password)
    ALHAZEN_CACHE_DIR File cache directory (default: ~/.alhazen/cache)
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB

    TYPEDB_AVAILABLE = True
except ImportError:
    TYPEDB_AVAILABLE = False
    print(
        "Warning: typedb-driver not installed. Install with: pip install 'typedb-driver>=3.8.0'",
        file=sys.stderr,
    )

try:
    from skillful_alhazen.utils.cache import (
        format_size,
        get_cache_stats,
        load_from_cache_text,
        save_to_cache,
        should_cache,
    )

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

    def should_cache(content):
        return False

    def get_cache_stats():
        return {"error": "Cache module not available"}

    def format_size(size):
        return f"{size} bytes"


# =============================================================================
# CONFIGURATION
# =============================================================================

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = int(os.getenv("TYPEDB_PORT", "1729"))
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "alhazen_notebook")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")

MONARCH_BASE_URL = "https://api-v3.monarchinitiative.org/v3/api"
CLINTRIALS_BASE_URL = "https://clinicaltrials.gov/api/v2"
CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

# HP frequency qualifier mapping (HP codes → string labels)
HPO_FREQUENCY_MAP = {
    "HP:0040280": "obligate",       # 100%
    "HP:0040281": "very-frequent",  # 80-99%
    "HP:0040282": "frequent",       # 30-79%
    "HP:0040283": "occasional",     # 5-29%
    "HP:0040284": "rare",           # 1-4%
    "HP:0040285": "very-rare",      # <1%
}

FREQUENCY_ORDER = ["obligate", "very-frequent", "frequent", "occasional", "rare", "very-rare", "unknown"]


# =============================================================================
# UTILITIES
# =============================================================================


def get_driver():
    """Get TypeDB driver connection."""
    return TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )


def generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def escape_string(s: str) -> str:
    """Escape special characters for TypeQL."""
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def get_timestamp() -> str:
    """Get current timestamp for TypeDB."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def monarch_get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to the Monarch Initiative API."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed. Run: uv sync --all-extras"}
    url = f"{MONARCH_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json", "User-Agent": "Alhazen-RareDisease/1.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def get_disease_info(disease_id: str) -> dict | None:
    """Get disease metadata from TypeDB entity ID."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(f'''
                match $d isa rd-disease, has id "{escape_string(disease_id)}";
                fetch {{
                    "id": $d.id,
                    "name": $d.name,
                    "mondo_id": $d.rd-mondo-id,
                    "description": $d.description
                }};
            ''').resolve())
    if not results:
        return None
    return results[0]


def get_mondo_id(disease_id: str) -> str | None:
    """Get MONDO ID from TypeDB disease entity ID."""
    info = get_disease_info(disease_id)
    if not info:
        return None
    return info.get("mondo_id")


def save_artifact(artifact_id: str, artifact_type: str, name: str, content: str,
                  mime_type: str, source_uri: str, extra_attrs: str = "") -> str:
    """Save an artifact to TypeDB, caching large content."""
    timestamp = get_timestamp()
    if CACHE_AVAILABLE and should_cache(content):
        cache_result = save_to_cache(artifact_id=artifact_id, content=content, mime_type=mime_type)
        query = f'''insert $a isa {artifact_type},
            has id "{artifact_id}",
            has name "{escape_string(name)}",
            has cache-path "{cache_result['cache_path']}",
            has mime-type "{mime_type}",
            has file-size {cache_result['file_size']},
            has source-uri "{escape_string(source_uri)}",
            has created-at {timestamp}{extra_attrs};'''
    else:
        safe_content = content[:50000] if len(content) > 50000 else content
        query = f'''insert $a isa {artifact_type},
            has id "{artifact_id}",
            has name "{escape_string(name)}",
            has content "{escape_string(safe_content)}",
            has mime-type "{mime_type}",
            has source-uri "{escape_string(source_uri)}",
            has created-at {timestamp}{extra_attrs};'''
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(query).resolve()
            tx.commit()
    return artifact_id


# =============================================================================
# INGESTION COMMANDS
# =============================================================================


def cmd_search_disease(args):
    """Search Monarch Initiative for diseases by name."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    params = {
        "q": args.query,
        "category": "biolink:Disease",
        "limit": args.limit or 10,
    }
    data = monarch_get("/search", params)
    if "error" in data:
        print(json.dumps({"success": False, "error": data["error"]}))
        return

    results = []
    for item in data.get("items", []):
        results.append({
            "mondo_id": item.get("id", ""),
            "name": item.get("name", ""),
            "description": (item.get("description") or "")[:200],
            "matching_text": item.get("matching_text", ""),
        })

    print(json.dumps({"success": True, "count": len(results), "diseases": results}, indent=2))


def cmd_init_disease(args):
    """Initialize disease knowledge graph from MONDO ID."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    # Check if already in TypeDB (idempotent)
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing = list(tx.query(f'''
                match $d isa rd-disease, has rd-mondo-id "{escape_string(mondo_id)}";
                fetch {{ "id": $d.id, "name": $d.name }};
            ''').resolve())

    if existing:
        print(json.dumps({
            "success": True,
            "disease_id": existing[0]["id"],
            "name": existing[0]["name"],
            "message": "Disease already initialized",
            "already_exists": True,
        }, indent=2))
        return

    # Fetch from Monarch
    data = monarch_get(f"/entity/{mondo_id}")
    if "error" in data:
        print(json.dumps({"success": False, "error": data["error"]}))
        return

    name = data.get("name") or data.get("full_name") or mondo_id
    description = (data.get("description") or "")[:1000]
    xrefs = data.get("xrefs") or []

    # Parse cross-references
    omim_id = orpha_id = gard_id = doid_id = ncit_id = ""
    for xref in xrefs:
        xref_str = str(xref.get("id", xref) if isinstance(xref, dict) else xref)
        if xref_str.startswith("OMIM:"):
            omim_id = xref_str
        elif xref_str.startswith("Orphanet:") or xref_str.startswith("ORPHA:"):
            orpha_id = xref_str
        elif xref_str.startswith("GARD:"):
            gard_id = xref_str
        elif xref_str.startswith("DOID:"):
            doid_id = xref_str
        elif xref_str.startswith("NCIT:"):
            ncit_id = xref_str

    # Parse inheritance
    inheritance = ""
    inheritance_data = data.get("inheritance") or []
    if inheritance_data and isinstance(inheritance_data, list):
        first = inheritance_data[0]
        inheritance = first.get("label", "") if isinstance(first, dict) else str(first)

    timestamp = get_timestamp()
    disease_id = generate_id("rd-disease")
    investigation_id = generate_id("rd-investigation")
    artifact_id = generate_id("rd-artifact")

    with get_driver() as driver:
        # Insert disease entity
        disease_query = f'''insert $d isa rd-disease,
            has id "{disease_id}",
            has name "{escape_string(name)}",
            has rd-mondo-id "{escape_string(mondo_id)}",
            has created-at {timestamp}'''
        if description:
            disease_query += f', has description "{escape_string(description)}"'
        if omim_id:
            disease_query += f', has rd-omim-id "{escape_string(omim_id)}"'
        if orpha_id:
            disease_query += f', has rd-orpha-id "{escape_string(orpha_id)}"'
        if gard_id:
            disease_query += f', has rd-gard-id "{escape_string(gard_id)}"'
        if doid_id:
            disease_query += f', has rd-doid-id "{escape_string(doid_id)}"'
        if ncit_id:
            disease_query += f', has rd-ncit-id "{escape_string(ncit_id)}"'
        if inheritance:
            disease_query += f', has rd-inheritance-pattern "{escape_string(inheritance)}"'
        disease_query += ";"

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(disease_query).resolve()
            tx.commit()

        # Insert investigation collection
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''insert $i isa rd-investigation,
                has id "{investigation_id}",
                has name "Investigation: {escape_string(name)}",
                has rd-investigation-status "active",
                has created-at {timestamp};''').resolve()
            tx.commit()

        # Add disease to investigation via collection-membership
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $d isa rd-disease, has id "{disease_id}";
                $i isa rd-investigation, has id "{investigation_id}";
            insert (collection: $i, member: $d) isa collection-membership;''').resolve()
            tx.commit()

    # Store MONDO record artifact (outside main driver block to avoid nesting issues)
    raw_json = json.dumps(data, indent=2)
    mondo_extra = f', has rd-mondo-id "{escape_string(mondo_id)}"'
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="rd-mondo-record",
        name=f"MONDO record: {name}",
        content=raw_json,
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}",
        extra_attrs=mondo_extra,
    )

    # Link artifact to disease via representation
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $a isa rd-mondo-record, has id "{artifact_id}";
                $d isa rd-disease, has id "{disease_id}";
            insert (referent: $d, artifact: $a) isa representation;''').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "investigation_id": investigation_id,
        "artifact_id": artifact_id,
        "name": name,
        "mondo_id": mondo_id,
        "omim_id": omim_id,
        "orpha_id": orpha_id,
        "message": (
            f"Initialized. Next steps:\n"
            f"  ingest-phenotypes --disease {disease_id}\n"
            f"  ingest-genes --disease {disease_id}\n"
            f"  ingest-hierarchy --disease {disease_id}"
        ),
    }, indent=2))


def cmd_ingest_phenotypes(args):
    """Ingest HPO phenotype associations from Monarch Initiative."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    mondo_id = get_mondo_id(args.disease)
    if not mondo_id:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    disease_info = get_disease_info(args.disease)
    disease_name = disease_info.get("name", mondo_id) if disease_info else mondo_id

    params = {
        "category": "biolink:DiseaseToPhenotypicFeatureAssociation",
        "limit": 500,
    }
    data = monarch_get(f"/entity/{mondo_id}/associations", params)
    if "error" in data:
        print(json.dumps({"success": False, "error": data["error"]}))
        return

    associations = data.get("items", [])
    timestamp = get_timestamp()
    inserted = skipped = 0

    with get_driver() as driver:
        for assoc in associations:
            obj = assoc.get("object", {})
            hpo_id = obj.get("id", "")
            hpo_label = obj.get("label") or obj.get("name") or hpo_id

            if not hpo_id or not hpo_id.startswith("HP:"):
                skipped += 1
                continue

            # Map frequency qualifier
            freq_qualifier = "unknown"
            # Check qualifiers array
            for q in (assoc.get("qualifiers") or []):
                q_id = q.get("id", "") if isinstance(q, dict) else str(q)
                if q_id in HPO_FREQUENCY_MAP:
                    freq_qualifier = HPO_FREQUENCY_MAP[q_id]
                    break
            # Also check frequency_qualifier field directly
            fq = assoc.get("frequency_qualifier") or ""
            if fq in HPO_FREQUENCY_MAP:
                freq_qualifier = HPO_FREQUENCY_MAP[fq]
            elif fq and freq_qualifier == "unknown":
                freq_qualifier = fq  # use as-is if not in our map

            evidence_code = ""
            for ev in (assoc.get("evidence") or []):
                evidence_code = ev.get("id", "") if isinstance(ev, dict) else str(ev)
                break

            # Upsert phenotype entity
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_p = list(tx.query(f'''
                    match $p isa rd-phenotype, has rd-hpo-id "{escape_string(hpo_id)}";
                    fetch {{ "id": $p.id }};
                ''').resolve())

            if existing_p:
                phenotype_id = existing_p[0]["id"]
            else:
                phenotype_id = generate_id("rd-phenotype")
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(f'''insert $p isa rd-phenotype,
                        has id "{phenotype_id}",
                        has name "{escape_string(hpo_label)}",
                        has rd-hpo-id "{escape_string(hpo_id)}",
                        has rd-hpo-label "{escape_string(hpo_label)}",
                        has created-at {timestamp};''').resolve()
                    tx.commit()

            # Check if relation already exists
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                rel_exists = list(tx.query(f'''
                    match
                        $d isa rd-disease, has id "{escape_string(args.disease)}";
                        $p isa rd-phenotype, has id "{phenotype_id}";
                        $r (disease: $d, phenotype: $p) isa rd-disease-has-phenotype;
                    fetch {{ "r": $r.id }};
                ''').resolve())

            if not rel_exists:
                rel_query = f'''match
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                    $p isa rd-phenotype, has id "{phenotype_id}";
                insert (disease: $d, phenotype: $p) isa rd-disease-has-phenotype,
                    has rd-frequency-qualifier "{escape_string(freq_qualifier)}"'''
                if evidence_code:
                    rel_query += f', has rd-evidence-code "{escape_string(evidence_code)}"'
                rel_query += ";"
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(rel_query).resolve()
                    tx.commit()
                inserted += 1
            else:
                skipped += 1

    # Store association artifact
    artifact_id = generate_id("rd-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="rd-monarch-assoc-record",
        name=f"Phenotype associations: {disease_name}",
        content=json.dumps(data, indent=2),
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}/associations?category=biolink:DiseaseToPhenotypicFeatureAssociation",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "mondo_id": mondo_id,
        "total_associations": len(associations),
        "inserted": inserted,
        "skipped_or_updated": skipped,
        "artifact_id": artifact_id,
        "message": f"Ingested {inserted} phenotypes. Run: show-phenome --id {args.disease}",
    }, indent=2))


def cmd_ingest_genes(args):
    """Ingest causal and correlated gene associations from Monarch Initiative."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    mondo_id = get_mondo_id(args.disease)
    if not mondo_id:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    disease_info = get_disease_info(args.disease)
    disease_name = disease_info.get("name", mondo_id) if disease_info else mondo_id

    timestamp = get_timestamp()
    causal_inserted = assoc_inserted = skipped = 0
    all_data = {}

    # Fetch both causal and correlated associations
    for category, rel_type in [
        ("biolink:CausalGeneToDiseaseAssociation", "causal"),
        ("biolink:CorrelatedGeneToDiseaseAssociation", "correlated"),
    ]:
        params = {"category": category, "limit": 200}
        data = monarch_get(f"/entity/{mondo_id}/associations", params)
        if "error" in data:
            print(json.dumps({"success": False, "error": f"{rel_type}: {data['error']}"}))
            return
        all_data[rel_type] = data

        for assoc in data.get("items", []):
            subj = assoc.get("subject", {})
            gene_id_raw = subj.get("id", "")
            gene_symbol = subj.get("symbol") or subj.get("label") or subj.get("name") or gene_id_raw
            gene_name = subj.get("name") or gene_symbol

            if not gene_id_raw or not gene_id_raw.startswith("HGNC:"):
                # Try NCBIGene as fallback
                if not gene_id_raw.startswith("NCBIGene:"):
                    skipped += 1
                    continue

            # Extract IDs
            hgnc_id = gene_id_raw if gene_id_raw.startswith("HGNC:") else ""
            entrez_id = gene_id_raw.replace("NCBIGene:", "") if gene_id_raw.startswith("NCBIGene:") else ""

            # Upsert gene entity (match by symbol or HGNC ID)
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                    if hgnc_id:
                        existing_g = list(tx.query(f'''
                            match $g isa rd-gene, has rd-hgnc-id "{escape_string(hgnc_id)}";
                            fetch {{ "id": $g.id }};
                        ''').resolve())
                    else:
                        existing_g = list(tx.query(f'''
                            match $g isa rd-gene, has rd-gene-symbol "{escape_string(gene_symbol)}";
                            fetch {{ "id": $g.id }};
                        ''').resolve())

            if existing_g:
                gene_entity_id = existing_g[0]["id"]
            else:
                gene_entity_id = generate_id("rd-gene")
                gene_insert = f'''insert $g isa rd-gene,
                    has id "{gene_entity_id}",
                    has name "{escape_string(gene_name)}",
                    has rd-gene-symbol "{escape_string(gene_symbol)}",
                    has created-at {timestamp}'''
                if hgnc_id:
                    gene_insert += f', has rd-hgnc-id "{escape_string(hgnc_id)}"'
                if entrez_id:
                    gene_insert += f', has rd-entrez-id "{escape_string(entrez_id)}"'
                gene_insert += ";"
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        tx.query(gene_insert).resolve()
                        tx.commit()

            # Extract confidence from association score
            confidence = assoc.get("score")
            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = None

            # Insert relation
            if rel_type == "causal":
                rel_query = f'''match
                    $g isa rd-gene, has id "{gene_entity_id}";
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                insert (gene: $g, disease: $d) isa rd-gene-causes-disease'''
                if confidence is not None:
                    rel_query += f", has confidence {confidence}"
                rel_query += ";"
                causal_inserted += 1
            else:
                assoc_type = "correlated"
                rel_query = f'''match
                    $g isa rd-gene, has id "{gene_entity_id}";
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                insert (gene: $g, disease: $d) isa rd-gene-associated-with,
                    has rd-association-type "{assoc_type}"'''
                if confidence is not None:
                    rel_query += f", has confidence {confidence}"
                rel_query += ";"
                assoc_inserted += 1

            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(rel_query).resolve()
                    tx.commit()

    # Store association artifact
    artifact_id = generate_id("rd-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="rd-monarch-assoc-record",
        name=f"Gene associations: {disease_name}",
        content=json.dumps(all_data, indent=2),
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}/associations",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "mondo_id": mondo_id,
        "causal_genes_inserted": causal_inserted,
        "associated_genes_inserted": assoc_inserted,
        "skipped": skipped,
        "artifact_id": artifact_id,
        "message": f"Inserted {causal_inserted} causal + {assoc_inserted} associated genes.",
    }, indent=2))


def cmd_ingest_hierarchy(args):
    """Ingest MONDO disease hierarchy (subclass-of relations) from stored artifact."""
    mondo_id = get_mondo_id(args.disease)
    if not mondo_id:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    # Find the stored MONDO record artifact
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            artifacts = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                    (referent: $d, artifact: $a) isa representation;
                    $a isa rd-mondo-record;
                fetch {{
                    "id": $a.id,
                    "content": $a.content,
                    "cache-path": $a.cache-path
                }};
            ''').resolve())

    if not artifacts:
        print(json.dumps({
            "success": False,
            "error": "No MONDO record artifact found. Run init-disease first.",
        }))
        return

    # Load artifact content
    art = artifacts[0]
    cache_path = art.get("cache-path")
    if cache_path and CACHE_AVAILABLE:
        try:
            content = load_from_cache_text(cache_path)
        except FileNotFoundError:
            content = art.get("content", "")
    else:
        content = art.get("content", "")

    if not content:
        print(json.dumps({"success": False, "error": "Artifact content is empty"}))
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"JSON parse error: {e}"}))
        return

    # Extract hierarchy from node_hierarchy.super_classes or inheritance_chain
    super_classes = []
    node_hierarchy = data.get("node_hierarchy", {})
    if isinstance(node_hierarchy, dict):
        super_classes = node_hierarchy.get("super_classes", [])

    # Also check taxon_closure or category_tags
    if not super_classes:
        # Try alternate field names
        for field in ["superClasses", "super_classes", "ancestors"]:
            val = data.get(field, [])
            if val:
                super_classes = val
                break

    timestamp = get_timestamp()
    inserted = skipped = 0

    for sc in super_classes:
        parent_mondo_id = sc.get("id", "") if isinstance(sc, dict) else str(sc)
        parent_name = sc.get("label") or sc.get("name") or parent_mondo_id if isinstance(sc, dict) else parent_mondo_id

        if not parent_mondo_id.startswith("MONDO:"):
            skipped += 1
            continue
        if parent_mondo_id == mondo_id:
            skipped += 1
            continue

        # Upsert parent disease
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_parent = list(tx.query(f'''
                    match $d isa rd-disease, has rd-mondo-id "{escape_string(parent_mondo_id)}";
                    fetch {{ "id": $d.id }};
                ''').resolve())

        if existing_parent:
            parent_id = existing_parent[0]["id"]
        else:
            parent_id = generate_id("rd-disease")
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(f'''insert $d isa rd-disease,
                        has id "{parent_id}",
                        has name "{escape_string(parent_name)}",
                        has rd-mondo-id "{escape_string(parent_mondo_id)}",
                        has created-at {timestamp};''').resolve()
                    tx.commit()

        # Insert subclass-of relation
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''match
                    $child isa rd-disease, has id "{escape_string(args.disease)}";
                    $parent isa rd-disease, has id "{parent_id}";
                insert (child-disease: $child, parent-disease: $parent) isa rd-disease-subclass-of;''').resolve()
                tx.commit()
        inserted += 1

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "mondo_id": mondo_id,
        "hierarchy_entries_inserted": inserted,
        "skipped": skipped,
        "message": (
            f"Inserted {inserted} parent disease nodes."
            if inserted else
            "No hierarchy data found in MONDO artifact. The API may not return this for all diseases."
        ),
    }, indent=2))


def cmd_ingest_similar(args):
    """Ingest phenotypically similar diseases via Monarch SemSim."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    mondo_id = get_mondo_id(args.disease)
    if not mondo_id:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    disease_info = get_disease_info(args.disease)
    disease_name = disease_info.get("name", mondo_id) if disease_info else mondo_id

    # Get the disease's HPO phenotype list for semsim query
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            phenotypes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                    (disease: $d, phenotype: $p) isa rd-disease-has-phenotype;
                fetch {{ "hpo_id": $p.rd-hpo-id }};
            ''').resolve())

    if not phenotypes:
        print(json.dumps({
            "success": False,
            "error": "No phenotypes found. Run ingest-phenotypes first.",
        }))
        return

    hpo_ids = [p.get("hpo_id") for p in phenotypes if p.get("hpo_id")]
    limit = args.limit or 20

    # Monarch SemSim search: find diseases similar to this disease
    params = {
        "subjects": ",".join(hpo_ids[:50]),  # API limit
        "metric": "ancestor_information_content",
        "limit": limit,
    }
    data = monarch_get("/semsim/search", params)
    if "error" in data:
        # Fallback: try using the disease ID directly
        params2 = {
            "subjects": mondo_id,
            "metric": "ancestor_information_content",
            "limit": limit,
        }
        data = monarch_get("/semsim/search", params2)
        if "error" in data:
            print(json.dumps({"success": False, "error": data["error"]}))
            return

    timestamp = get_timestamp()
    inserted = skipped = 0

    for match_item in data.get("matches", []) or data.get("items", []):
        similar_mondo_id = match_item.get("id", "") or match_item.get("subject_id", "")
        similar_name = match_item.get("name") or match_item.get("label") or similar_mondo_id
        score = match_item.get("score") or match_item.get("similarity_score")

        if not similar_mondo_id.startswith("MONDO:"):
            skipped += 1
            continue
        if similar_mondo_id == mondo_id:
            skipped += 1
            continue

        try:
            score_float = float(score) if score is not None else 0.0
        except (ValueError, TypeError):
            score_float = 0.0

        # Upsert similar disease
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_sim = list(tx.query(f'''
                    match $d isa rd-disease, has rd-mondo-id "{escape_string(similar_mondo_id)}";
                    fetch {{ "id": $d.id }};
                ''').resolve())

        if existing_sim:
            sim_id = existing_sim[0]["id"]
        else:
            sim_id = generate_id("rd-disease")
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(f'''insert $d isa rd-disease,
                        has id "{sim_id}",
                        has name "{escape_string(similar_name)}",
                        has rd-mondo-id "{escape_string(similar_mondo_id)}",
                        has created-at {timestamp};''').resolve()
                    tx.commit()

        # Insert similarity relation
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''match
                    $a isa rd-disease, has id "{escape_string(args.disease)}";
                    $b isa rd-disease, has id "{sim_id}";
                insert (disease-a: $a, disease-b: $b) isa rd-disease-similar-to,
                    has rd-similarity-score {score_float};''').resolve()
                tx.commit()
        inserted += 1

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "mondo_id": mondo_id,
        "similar_diseases_inserted": inserted,
        "skipped": skipped,
        "message": f"Inserted {inserted} similar disease relations.",
    }, indent=2))


def cmd_ingest_clintrials(args):
    """Ingest clinical trials from ClinicalTrials.gov."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    disease_info = get_disease_info(args.disease)
    if not disease_info:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    disease_name = disease_info.get("name", "")

    params = {
        "query.cond": disease_name,
        "pageSize": 50,
        "format": "json",
    }
    url = f"{CLINTRIALS_BASE_URL}/studies"
    headers = {"Accept": "application/json", "User-Agent": "Alhazen-RareDisease/1.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        return

    studies = data.get("studies", [])
    timestamp = get_timestamp()
    inserted = skipped = 0

    for study in studies:
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status_mod = protocol.get("statusModule", {})
        design_mod = protocol.get("designModule", {})

        nct_id = ident.get("nctId", "")
        if not nct_id:
            skipped += 1
            continue

        title = ident.get("briefTitle") or ident.get("officialTitle") or nct_id
        trial_status = status_mod.get("overallStatus", "")
        phases = design_mod.get("phases", [])
        trial_phase = phases[0] if phases else "N/A"

        # Check if trial already exists
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_t = list(tx.query(f'''
                    match $t isa rd-clinical-trial, has rd-nct-id "{escape_string(nct_id)}";
                    fetch {{ "id": $t.id }};
                ''').resolve())

        if existing_t:
            trial_id = existing_t[0]["id"]
        else:
            trial_id = generate_id("rd-trial")
            trial_insert = f'''insert $t isa rd-clinical-trial,
                has id "{trial_id}",
                has name "{escape_string(title[:200])}",
                has rd-nct-id "{escape_string(nct_id)}",
                has rd-trial-status "{escape_string(trial_status)}",
                has rd-trial-phase "{escape_string(trial_phase)}",
                has created-at {timestamp};'''
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(trial_insert).resolve()
                    tx.commit()

        # Link trial to disease
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''match
                    $t isa rd-clinical-trial, has id "{trial_id}";
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                insert (trial: $t, disease: $d) isa rd-trial-studies;''').resolve()
                tx.commit()
        inserted += 1

    # Store artifact
    artifact_id = generate_id("rd-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="rd-clintrials-record",
        name=f"Clinical trials: {disease_name}",
        content=json.dumps(data, indent=2),
        mime_type="application/json",
        source_uri=f"{CLINTRIALS_BASE_URL}/studies?query.cond={disease_name}",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "disease_name": disease_name,
        "total_studies": len(studies),
        "inserted": inserted,
        "skipped": skipped,
        "artifact_id": artifact_id,
    }, indent=2))


def cmd_ingest_drugs(args):
    """Ingest drug candidates from ChEMBL for each causal gene."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    # Get causal genes for this disease
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            genes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                    (gene: $g, disease: $d) isa rd-gene-causes-disease;
                fetch {{
                    "gene_id": $g.id,
                    "gene_symbol": $g.rd-gene-symbol
                }};
            ''').resolve())

    if not genes:
        print(json.dumps({
            "success": False,
            "error": "No causal genes found. Run ingest-genes first.",
        }))
        return

    timestamp = get_timestamp()
    total_drugs = 0
    gene_results = []

    for gene_info in genes:
        gene_id = gene_info.get("gene_id")
        gene_symbol = gene_info.get("gene_symbol", "")
        if not gene_symbol:
            continue

        # ChEMBL target lookup by gene symbol
        chembl_url = f"{CHEMBL_BASE_URL}/target"
        params = {"target_synonym": gene_symbol, "format": "json", "limit": 5}
        headers = {"Accept": "application/json"}

        try:
            resp = requests.get(chembl_url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            target_data = resp.json()
        except Exception as e:
            gene_results.append({"gene": gene_symbol, "error": str(e)})
            continue

        targets = target_data.get("targets", [])
        drugs_for_gene = 0

        for target in targets[:3]:  # Take top 3 targets
            target_chembl_id = target.get("target_chembl_id", "")
            if not target_chembl_id:
                continue

            # Store ChEMBL target artifact
            artifact_id = generate_id("rd-artifact")
            save_artifact(
                artifact_id=artifact_id,
                artifact_type="rd-chembl-record",
                name=f"ChEMBL target: {gene_symbol}",
                content=json.dumps(target, indent=2),
                mime_type="application/json",
                source_uri=f"{CHEMBL_BASE_URL}/target/{target_chembl_id}",
                extra_attrs=f', has rd-chembl-id "{escape_string(target_chembl_id)}"',
            )

            # Get mechanisms for this target
            try:
                mech_resp = requests.get(
                    f"{CHEMBL_BASE_URL}/mechanism",
                    params={"target_chembl_id": target_chembl_id, "format": "json", "limit": 20},
                    headers=headers,
                    timeout=30,
                )
                mech_resp.raise_for_status()
                mech_data = mech_resp.json()
            except Exception:
                mech_data = {"mechanisms": []}

            for mech in mech_data.get("mechanisms", [])[:10]:
                drug_chembl_id = mech.get("molecule_chembl_id", "")
                drug_name = mech.get("molecule_name") or mech.get("pref_name") or drug_chembl_id
                moa = mech.get("mechanism_of_action", "")

                if not drug_chembl_id:
                    continue

                # Upsert drug entity
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                        existing_drug = list(tx.query(f'''
                            match $dr isa rd-drug, has rd-chembl-id "{escape_string(drug_chembl_id)}";
                            fetch {{ "id": $dr.id }};
                        ''').resolve())

                if existing_drug:
                    drug_entity_id = existing_drug[0]["id"]
                else:
                    drug_entity_id = generate_id("rd-drug")
                    drug_insert = f'''insert $dr isa rd-drug,
                        has id "{drug_entity_id}",
                        has name "{escape_string(drug_name)}",
                        has rd-chembl-id "{escape_string(drug_chembl_id)}",
                        has created-at {timestamp}'''
                    if moa:
                        drug_insert += f', has rd-mechanism-of-action "{escape_string(moa)}"'
                    drug_insert += ";"
                    with get_driver() as driver:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            tx.query(drug_insert).resolve()
                            tx.commit()

                # Insert drug-targets relation
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        target_query = f'''match
                            $dr isa rd-drug, has id "{drug_entity_id}";
                            $g isa rd-gene, has id "{gene_id}";
                        insert (drug: $dr, target-gene: $g) isa rd-drug-targets'''
                        if moa:
                            target_query += f', has rd-mechanism-of-action "{escape_string(moa)}"'
                        target_query += ";"
                        tx.query(target_query).resolve()
                        tx.commit()

                drugs_for_gene += 1
                total_drugs += 1

        gene_results.append({"gene": gene_symbol, "drugs_inserted": drugs_for_gene})

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "genes_processed": len(genes),
        "total_drugs_inserted": total_drugs,
        "by_gene": gene_results,
    }, indent=2))


def cmd_build_corpus(args):
    """Print ready-to-run epmc-search CLI commands for literature search."""
    disease_info = get_disease_info(args.disease)
    if not disease_info:
        print(json.dumps({"success": False, "error": f"Disease not found: {args.disease}"}))
        return

    disease_name = disease_info.get("name", "")
    mondo_id = disease_info.get("mondo_id", "")

    # Get causal genes
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            genes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.disease)}";
                    (gene: $g, disease: $d) isa rd-gene-causes-disease;
                fetch {{ "gene_symbol": $g.rd-gene-symbol }};
            ''').resolve())

    gene_symbols = [g.get("gene_symbol") for g in genes if g.get("gene_symbol")]

    commands = []

    # Disease overview search
    commands.append({
        "purpose": "Disease overview literature",
        "command": f'uv run python .claude/skills/epmc-search/epmc_search.py search --query "{disease_name}" --max-results 20',
    })

    # Gene-specific searches
    for sym in gene_symbols[:3]:
        commands.append({
            "purpose": f"Gene {sym} + disease mechanism",
            "command": f'uv run python .claude/skills/epmc-search/epmc_search.py search --query "{sym} {disease_name} mechanism" --max-results 15',
        })
        commands.append({
            "purpose": f"Gene {sym} therapy",
            "command": f'uv run python .claude/skills/epmc-search/epmc_search.py search --query "{sym} therapy treatment" --max-results 10',
        })

    # Natural history / clinical
    commands.append({
        "purpose": "Natural history and clinical features",
        "command": f'uv run python .claude/skills/epmc-search/epmc_search.py search --query "{disease_name} natural history clinical features" --max-results 15',
    })

    output = {
        "success": True,
        "disease": disease_name,
        "mondo_id": mondo_id,
        "causal_genes": gene_symbols,
        "suggested_commands": commands,
        "instructions": "Copy-paste these commands to ingest papers into your corpus. Then ask Claude to analyze them.",
    }
    print(json.dumps(output, indent=2))


# =============================================================================
# QUERY COMMANDS
# =============================================================================


def cmd_list_diseases(args):
    """List all rd-disease entities."""
    query = """match $d isa rd-disease;
fetch {
    "id": $d.id,
    "name": $d.name,
    "rd-mondo-id": $d.rd-mondo-id,
    "rd-omim-id": $d.rd-omim-id,
    "rd-inheritance-pattern": $d.rd-inheritance-pattern,
    "created-at": $d.created-at
};"""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(query).resolve())
    print(json.dumps({"success": True, "diseases": results, "count": len(results)}, indent=2, default=str))


def cmd_show_disease(args):
    """Get full disease profile."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            # Core disease metadata
            disease_result = list(tx.query(f'''
                match $d isa rd-disease, has id "{escape_string(args.id)}";
                fetch {{
                    "id": $d.id,
                    "name": $d.name,
                    "description": $d.description,
                    "rd-mondo-id": $d.rd-mondo-id,
                    "rd-omim-id": $d.rd-omim-id,
                    "rd-orpha-id": $d.rd-orpha-id,
                    "rd-gard-id": $d.rd-gard-id,
                    "rd-doid-id": $d.rd-doid-id,
                    "rd-inheritance-pattern": $d.rd-inheritance-pattern,
                    "rd-prevalence": $d.rd-prevalence,
                    "rd-age-of-onset": $d.rd-age-of-onset
                }};
            ''').resolve())

            if not disease_result:
                print(json.dumps({"success": False, "error": "Disease not found"}))
                return

            # Causal genes
            causal_genes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (gene: $g, disease: $d) isa rd-gene-causes-disease;
                fetch {{
                    "id": $g.id,
                    "rd-gene-symbol": $g.rd-gene-symbol,
                    "rd-hgnc-id": $g.rd-hgnc-id,
                    "rd-entrez-id": $g.rd-entrez-id
                }};
            ''').resolve())

            # Associated genes
            assoc_genes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (gene: $g, disease: $d) isa rd-gene-associated-with;
                fetch {{
                    "id": $g.id,
                    "rd-gene-symbol": $g.rd-gene-symbol
                }};
            ''').resolve())

            # Notes
            notes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (note: $n, subject: $d) isa aboutness;
                fetch {{
                    "id": $n.id,
                    "name": $n.name,
                    "content": $n.content
                }};
            ''').resolve())

            # Investigation
            investigation = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (member: $d, collection: $i) isa collection-membership;
                    $i isa rd-investigation;
                fetch {{
                    "id": $i.id,
                    "name": $i.name,
                    "rd-investigation-status": $i.rd-investigation-status
                }};
            ''').resolve())

    output = {
        "success": True,
        "disease": disease_result[0],
        "causal_genes": causal_genes,
        "associated_genes": assoc_genes,
        "notes": notes,
        "investigation": investigation[0] if investigation else None,
    }
    print(json.dumps(output, indent=2, default=str))


def cmd_show_phenome(args):
    """Show phenotypes grouped by frequency tier."""
    min_freq = args.min_freq

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            phenotype_query = f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (disease: $d, phenotype: $p) isa rd-disease-has-phenotype,
                        has rd-frequency-qualifier $freq;
                fetch {{
                    "id": $p.id,
                    "rd-hpo-id": $p.rd-hpo-id,
                    "rd-hpo-label": $p.rd-hpo-label,
                    "frequency": $freq
                }};
            '''
            phenotypes = list(tx.query(phenotype_query).resolve())

            # Also get phenotypes without frequency qualifier
            all_phenotypes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (disease: $d, phenotype: $p) isa rd-disease-has-phenotype;
                fetch {{
                    "id": $p.id,
                    "rd-hpo-id": $p.rd-hpo-id,
                    "rd-hpo-label": $p.rd-hpo-label
                }};
            ''').resolve())

    # Build frequency map
    freq_map = {p["id"]: p.get("frequency", "unknown") for p in phenotypes}

    # Filter by min_freq if specified
    freq_cutoff = {
        "obligate": 0,
        "very-frequent": 1,
        "frequent": 2,
        "occasional": 3,
        "rare": 4,
        "very-rare": 5,
    }
    cutoff_idx = freq_cutoff.get(min_freq, 999) if min_freq else 999

    grouped = {}
    for ph in all_phenotypes:
        ph_id = ph["id"]
        freq = freq_map.get(ph_id, "unknown")
        idx = freq_cutoff.get(freq, 999)
        if idx > cutoff_idx:
            continue
        if freq not in grouped:
            grouped[freq] = []
        grouped[freq].append({
            "hpo_id": ph.get("rd-hpo-id"),
            "label": ph.get("rd-hpo-label"),
            "id": ph_id,
        })

    # Sort groups by frequency order
    ordered = {}
    for freq in FREQUENCY_ORDER:
        if freq in grouped:
            ordered[freq] = grouped[freq]

    print(json.dumps({
        "success": True,
        "disease_id": args.id,
        "total_phenotypes": len(all_phenotypes),
        "phenome": ordered,
        "min_freq_filter": min_freq or "none",
    }, indent=2))


def cmd_show_therapeutome(args):
    """Show therapeutic landscape: drugs, trials, and notes."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            # Drugs via gene targets
            drugs = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (gene: $g, disease: $d) isa rd-gene-causes-disease;
                    (drug: $dr, target-gene: $g) isa rd-drug-targets;
                fetch {{
                    "drug_id": $dr.id,
                    "drug_name": $dr.name,
                    "rd-chembl-id": $dr.rd-chembl-id,
                    "rd-drugbank-id": $dr.rd-drugbank-id,
                    "rd-drug-class": $dr.rd-drug-class,
                    "rd-mechanism-of-action": $dr.rd-mechanism-of-action,
                    "rd-development-stage": $dr.rd-development-stage,
                    "gene_symbol": $g.rd-gene-symbol
                }};
            ''').resolve())

            # Drugs indicated directly
            indicated = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (drug: $dr, indication: $d) isa rd-drug-indicated-for;
                fetch {{
                    "drug_id": $dr.id,
                    "drug_name": $dr.name,
                    "rd-chembl-id": $dr.rd-chembl-id,
                    "rd-development-stage": $dr.rd-development-stage
                }};
            ''').resolve())

            # Clinical trials
            trials = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (trial: $t, disease: $d) isa rd-trial-studies;
                fetch {{
                    "id": $t.id,
                    "name": $t.name,
                    "rd-nct-id": $t.rd-nct-id,
                    "rd-trial-phase": $t.rd-trial-phase,
                    "rd-trial-status": $t.rd-trial-status
                }};
            ''').resolve())

            # Therapeutic notes
            notes = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (note: $n, subject: $d) isa aboutness;
                    {{ $n isa rd-therapeutic-landscape-note; }} or
                    {{ $n isa rd-mechanism-note; }};
                fetch {{
                    "id": $n.id,
                    "name": $n.name,
                    "content": $n.content
                }};
            ''').resolve())

    print(json.dumps({
        "success": True,
        "disease_id": args.id,
        "drug_targets": drugs,
        "indicated_drugs": indicated,
        "clinical_trials": trials,
        "therapeutic_notes": notes,
    }, indent=2, default=str))


def cmd_show_similar(args):
    """Show phenotypically similar diseases with similarity scores."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            similar = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    $r (disease-a: $d, disease-b: $sim) isa rd-disease-similar-to,
                        has rd-similarity-score $score;
                fetch {{
                    "id": $sim.id,
                    "name": $sim.name,
                    "rd-mondo-id": $sim.rd-mondo-id,
                    "similarity_score": $score
                }};
            ''').resolve())

            # Also check the reverse direction
            similar_rev = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    $r (disease-a: $sim, disease-b: $d) isa rd-disease-similar-to,
                        has rd-similarity-score $score;
                fetch {{
                    "id": $sim.id,
                    "name": $sim.name,
                    "rd-mondo-id": $sim.rd-mondo-id,
                    "similarity_score": $score
                }};
            ''').resolve())

    all_similar = similar + similar_rev
    # Sort by score descending
    all_similar.sort(key=lambda x: float(x.get("similarity_score", 0) or 0), reverse=True)

    print(json.dumps({
        "success": True,
        "disease_id": args.id,
        "similar_diseases": all_similar,
        "count": len(all_similar),
    }, indent=2, default=str))


def cmd_show_hierarchy(args):
    """Show MONDO disease hierarchy (parent classes)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            parents = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (child-disease: $d, parent-disease: $p) isa rd-disease-subclass-of;
                fetch {{
                    "id": $p.id,
                    "name": $p.name,
                    "rd-mondo-id": $p.rd-mondo-id
                }};
            ''').resolve())

            # Children
            children = list(tx.query(f'''
                match
                    $d isa rd-disease, has id "{escape_string(args.id)}";
                    (child-disease: $child, parent-disease: $d) isa rd-disease-subclass-of;
                fetch {{
                    "id": $child.id,
                    "name": $child.name,
                    "rd-mondo-id": $child.rd-mondo-id
                }};
            ''').resolve())

    print(json.dumps({
        "success": True,
        "disease_id": args.id,
        "parent_classes": parents,
        "child_classes": children,
    }, indent=2, default=str))


# =============================================================================
# ARTIFACT COMMANDS
# =============================================================================


def cmd_list_artifacts(args):
    """List artifacts, optionally filtered by associated disease."""
    if args.disease:
        query = f"""match
            $d isa rd-disease, has id "{escape_string(args.disease)}";
            (referent: $d, artifact: $a) isa representation;
        fetch {{
            "id": $a.id,
            "name": $a.name,
            "source-uri": $a.source-uri,
            "created-at": $a.created-at
        }};"""
    else:
        query = """match
            $a isa artifact;
            {{ $a isa rd-mondo-record; }} or
            {{ $a isa rd-monarch-assoc-record; }} or
            {{ $a isa rd-omim-record; }} or
            {{ $a isa rd-orphanet-record; }} or
            {{ $a isa rd-clintrials-record; }} or
            {{ $a isa rd-chembl-record; }} or
            {{ $a isa rd-gnomad-record; }};
        fetch {
            "id": $a.id,
            "name": $a.name,
            "source-uri": $a.source-uri,
            "created-at": $a.created-at
        };"""

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            artifacts = list(tx.query(query).resolve())

    print(json.dumps({
        "success": True,
        "artifacts": artifacts,
        "count": len(artifacts),
    }, indent=2, default=str))


def cmd_show_artifact(args):
    """Get artifact content for sensemaking."""
    query = f'''match $a isa artifact, has id "{escape_string(args.id)}";
    fetch {{
        "id": $a.id,
        "name": $a.name,
        "content": $a.content,
        "cache-path": $a.cache-path,
        "mime-type": $a.mime-type,
        "file-size": $a.file-size,
        "source-uri": $a.source-uri,
        "created-at": $a.created-at
    }};'''

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            result = list(tx.query(query).resolve())

    if not result:
        print(json.dumps({"success": False, "error": "Artifact not found"}))
        return

    art = result[0]
    cache_path = art.get("cache-path")
    if cache_path and CACHE_AVAILABLE:
        try:
            content = load_from_cache_text(cache_path)
            storage = "cache"
        except FileNotFoundError:
            content = f"[ERROR: Cache file not found: {cache_path}]"
            storage = "cache_missing"
    else:
        content = art.get("content")
        storage = "inline"

    print(json.dumps({
        "success": True,
        "artifact": {
            "id": art.get("id"),
            "name": art.get("name"),
            "source_url": art.get("source-uri"),
            "created_at": art.get("created-at"),
            "content": content,
            "storage": storage,
            "cache_path": cache_path,
            "mime_type": art.get("mime-type"),
            "file_size": art.get("file-size"),
        },
    }, indent=2))


# =============================================================================
# NOTE COMMANDS
# =============================================================================


def cmd_add_note(args):
    """Create a note about any entity."""
    note_id = generate_id("note")
    timestamp = get_timestamp()

    type_map = {
        "disease-overview": "rd-disease-overview-note",
        "mechanism": "rd-mechanism-note",
        "phenotypic-spectrum": "rd-phenotypic-spectrum-note",
        "diagnostic-criteria": "rd-diagnostic-criteria-note",
        "differential": "rd-differential-note",
        "therapeutic-landscape": "rd-therapeutic-landscape-note",
        "expert-landscape": "rd-expert-landscape-note",
        "research-gaps": "rd-research-gaps-note",
        "natural-history": "rd-natural-history-note",
        "general": "note",
    }
    note_type = type_map.get(args.type, "note")

    query = f'''insert $n isa {note_type},
        has id "{note_id}",
        has content "{escape_string(args.content)}",
        has created-at {timestamp}'''

    if args.name:
        query += f', has name "{escape_string(args.name)}"'
    if args.confidence is not None:
        query += f", has confidence {args.confidence}"
    if args.type == "mechanism" and args.mechanism_type:
        query += f', has rd-mechanism-type "{escape_string(args.mechanism_type)}"'
    if args.type == "mechanism" and args.functional_impact:
        query += f', has rd-functional-impact "{escape_string(args.functional_impact)}"'

    query += ";"

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(query).resolve()
            tx.commit()

        # Link to subject entity
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $n isa note, has id "{note_id}";
                $s isa entity, has id "{escape_string(args.about)}";
            insert (note: $n, subject: $s) isa aboutness;''').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "note_id": note_id,
        "about": args.about,
        "type": args.type,
    }))


# =============================================================================
# TAGGING COMMANDS
# =============================================================================


def cmd_tag(args):
    """Tag an entity."""
    tag_id = generate_id("tag")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing_tag = list(tx.query(
                f'match $t isa tag, has name "{escape_string(args.tag)}"; fetch {{ "id": $t.id }};'
            ).resolve())

        if not existing_tag:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'insert $t isa tag, has id "{tag_id}", has name "{escape_string(args.tag)}";').resolve()
                tx.commit()

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $e isa entity, has id "{escape_string(args.entity)}";
                $t isa tag, has name "{escape_string(args.tag)}";
            insert (tagged-entity: $e, tag: $t) isa tagging;''').resolve()
            tx.commit()

    print(json.dumps({"success": True, "entity": args.entity, "tag": args.tag}))


def cmd_search_tag(args):
    """Search entities by tag."""
    query = f'''match
        $t isa tag, has name "{escape_string(args.tag)}";
        (tagged-entity: $e, tag: $t) isa tagging;
    fetch {{
        "id": $e.id,
        "name": $e.name
    }};'''

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(query).resolve())

    print(json.dumps({
        "success": True,
        "tag": args.tag,
        "entities": results,
        "count": len(results),
    }, indent=2, default=str))


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Rare Disease Investigation CLI - MONDO-based disease knowledge graph builder"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- Disease Discovery ---

    p = subparsers.add_parser("search-disease", help="Search Monarch Initiative for diseases by name")
    p.add_argument("--query", required=True, help="Disease name or keyword to search")
    p.add_argument("--limit", type=int, default=10, help="Maximum results (default: 10)")

    p = subparsers.add_parser("init-disease", help="Initialize disease KG from MONDO ID")
    p.add_argument("--mondo-id", required=True, help="MONDO ID (e.g., MONDO:0800044 or 0800044)")

    # --- Ingestion ---

    p = subparsers.add_parser("ingest-phenotypes", help="Ingest HPO phenotype associations from Monarch")
    p.add_argument("--disease", required=True, help="Disease entity ID (from init-disease or list-diseases)")

    p = subparsers.add_parser("ingest-genes", help="Ingest causal and correlated gene associations from Monarch")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    p = subparsers.add_parser("ingest-hierarchy", help="Ingest MONDO subclass hierarchy from stored artifact")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    p = subparsers.add_parser("ingest-similar", help="Ingest phenotypically similar diseases via Monarch SemSim")
    p.add_argument("--disease", required=True, help="Disease entity ID")
    p.add_argument("--limit", type=int, default=20, help="Max similar diseases (default: 20)")

    p = subparsers.add_parser("ingest-clintrials", help="Ingest clinical trials from ClinicalTrials.gov")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    p = subparsers.add_parser("ingest-drugs", help="Ingest drug candidates from ChEMBL for causal genes")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    p = subparsers.add_parser("build-corpus", help="Print epmc-search commands for literature ingestion")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # --- Queries ---

    subparsers.add_parser("list-diseases", help="List all rd-disease entities")

    p = subparsers.add_parser("show-disease", help="Full disease profile")
    p.add_argument("--id", required=True, help="Disease entity ID")

    p = subparsers.add_parser("show-phenome", help="Phenotypes grouped by frequency tier")
    p.add_argument("--id", required=True, help="Disease entity ID")
    p.add_argument("--min-freq",
                   choices=["obligate", "very-frequent", "frequent", "occasional", "rare", "very-rare"],
                   help="Minimum frequency tier to show")

    p = subparsers.add_parser("show-therapeutome", help="Drugs, trials, and therapeutic notes")
    p.add_argument("--id", required=True, help="Disease entity ID")

    p = subparsers.add_parser("show-similar", help="Phenotypically similar diseases")
    p.add_argument("--id", required=True, help="Disease entity ID")

    p = subparsers.add_parser("show-hierarchy", help="Parent and child MONDO classes")
    p.add_argument("--id", required=True, help="Disease entity ID")

    # --- Standard ---

    p = subparsers.add_parser("list-artifacts", help="List artifacts for a disease")
    p.add_argument("--disease", help="Disease entity ID (optional, lists all rd-artifacts if omitted)")

    p = subparsers.add_parser("show-artifact", help="Get artifact content")
    p.add_argument("--id", required=True, help="Artifact entity ID")

    p = subparsers.add_parser("add-note", help="Create a note about any entity")
    p.add_argument("--about", required=True, help="Entity ID this note is about")
    p.add_argument("--type", required=True,
                   choices=["disease-overview", "mechanism", "phenotypic-spectrum", "diagnostic-criteria",
                            "differential", "therapeutic-landscape", "expert-landscape", "research-gaps",
                            "natural-history", "general"],
                   help="Note type")
    p.add_argument("--content", required=True, help="Note content (markdown supported)")
    p.add_argument("--name", help="Note name/title")
    p.add_argument("--confidence", type=float, help="Confidence score (0.0-1.0)")
    p.add_argument("--mechanism-type",
                   choices=["gain-of-function", "partial-loss", "total-loss", "dominant-negative", "toxification"],
                   help="Mechanism type (for mechanism notes)")
    p.add_argument("--functional-impact",
                   choices=["overactivity", "underactivity", "absence", "toxicity"],
                   help="Functional impact (for mechanism notes)")

    p = subparsers.add_parser("tag", help="Tag an entity")
    p.add_argument("--entity", required=True, help="Entity ID to tag")
    p.add_argument("--tag", required=True, help="Tag name")

    p = subparsers.add_parser("search-tag", help="Search entities by tag")
    p.add_argument("--tag", required=True, help="Tag name to search")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not TYPEDB_AVAILABLE and args.command not in ["search-disease"]:
        print(json.dumps({"success": False, "error": "typedb-driver not installed"}))
        sys.exit(1)

    commands = {
        "search-disease": cmd_search_disease,
        "init-disease": cmd_init_disease,
        "ingest-phenotypes": cmd_ingest_phenotypes,
        "ingest-genes": cmd_ingest_genes,
        "ingest-hierarchy": cmd_ingest_hierarchy,
        "ingest-similar": cmd_ingest_similar,
        "ingest-clintrials": cmd_ingest_clintrials,
        "ingest-drugs": cmd_ingest_drugs,
        "build-corpus": cmd_build_corpus,
        "list-diseases": cmd_list_diseases,
        "show-disease": cmd_show_disease,
        "show-phenome": cmd_show_phenome,
        "show-therapeutome": cmd_show_therapeutome,
        "show-similar": cmd_show_similar,
        "show-hierarchy": cmd_show_hierarchy,
        "list-artifacts": cmd_list_artifacts,
        "show-artifact": cmd_show_artifact,
        "add-note": cmd_add_note,
        "tag": cmd_tag,
        "search-tag": cmd_search_tag,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
            sys.exit(1)
    else:
        print(json.dumps({"success": False, "error": f"Unknown command: {args.command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
