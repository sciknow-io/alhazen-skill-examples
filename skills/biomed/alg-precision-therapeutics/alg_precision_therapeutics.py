#!/usr/bin/env python3
"""
Algorithm for Precision Therapeutics CLI - Mechanism-centered rare disease investigation.

Starting from a known MONDO diagnosis, synthesizes mechanism of harm and therapeutic
strategies from Monarch, ClinicalTrials.gov, ChEMBL, and literature.

Central innovation: apt-mechanism is a first-class entity linking
gene -> pathway -> phenotype -> drug.

This script handles INGESTION and QUERIES. Claude handles SENSEMAKING via SKILL.md.

Usage:
    python alg_precision_therapeutics.py <command> [options]

Commands:
    # Disease Discovery
    search-disease          Search Monarch Initiative for diseases by name
    init-investigation      Initialize investigation from MONDO ID
    list-investigations     List all investigations in TypeDB

    # Automated Ingestion
    ingest-disease          Full pipeline: phenotypes + genes + hierarchy + drugs + trials
    ingest-phenotypes       Ingest HPO phenotype associations from Monarch
    ingest-genes            Ingest causal and correlated gene associations from Monarch
    ingest-hierarchy        Ingest MONDO subclass hierarchy
    ingest-drugs            Ingest drug candidates from ChEMBL (per causal gene)
    ingest-clintrials       Ingest clinical trials from ClinicalTrials.gov

    # Manual Entity Management
    add-mechanism           Add a mechanism of harm entity
    add-gene                Add a gene entity
    add-drug                Add a drug entity
    add-strategy            Add a therapeutic strategy entity
    add-phenotype           Add a phenotype entity
    link-mechanism-gene     Link mechanism to gene
    link-mechanism-phenotype Link mechanism to phenotype
    link-drug-mechanism     Link drug to mechanism (via strategy)
    link-drug-target        Link drug to gene target

    # Artifact Inspection
    list-artifacts          List artifacts (optionally filtered by disease)
    show-artifact           Get artifact content for sensemaking

    # Analysis Views
    show-disease            Full disease overview
    show-mechanisms         All mechanisms with gene/pathway/phenotype links
    show-therapeutic-map    Strategies per mechanism with drug evidence
    show-phenome            Phenotypic spectrum by frequency tier
    show-genes              Causal genes with association type/evidence
    show-trials             Clinical trials landscape

    # Notes and Organization
    add-note                Create a note about any entity
    tag                     Tag an entity
    search-tag              Search entities by tag

    # Scaffold
    build-corpus            Print ready-to-run epmc-search CLI commands

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

# HP frequency qualifier mapping (HP codes -> string labels)
HPO_FREQUENCY_MAP = {
    "HP:0040280": "obligate",       # 100%
    "HP:0040281": "very-frequent",  # 80-99%
    "HP:0040282": "frequent",       # 30-79%
    "HP:0040283": "occasional",     # 5-29%
    "HP:0040284": "rare",           # 1-4%
    "HP:0040285": "very-rare",      # <1%
}

FREQUENCY_ORDER = ["obligate", "very-frequent", "frequent", "occasional", "rare", "very-rare", "unknown"]

# APM mechanism types
MECHANISM_TYPES = [
    "GoF",                    # Gain of function
    "LoF-partial",            # Partial loss of function
    "LoF-total",              # Complete loss of function
    "dominant-negative",      # Dominant negative
    "haploinsufficiency",     # One copy insufficient
    "toxic-aggregation",      # Toxic protein aggregation
    "pathway-dysregulation",  # Indirect pathway effect
]


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


def escape_string(s) -> str:
    """Escape special characters for TypeQL."""
    if s is None:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def get_timestamp() -> str:
    """Get current timestamp for TypeDB."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def monarch_get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to the Monarch Initiative API."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed. Run: uv sync --all-extras"}
    url = f"{MONARCH_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json", "User-Agent": "Alhazen-APT/1.0"}
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
                match $d isa apt-disease, has id "{escape_string(disease_id)}";
                fetch {{
                    "id": $d.id,
                    "name": $d.name,
                    "mondo_id": $d.apt-mondo-id,
                    "description": $d.description
                }};
            ''').resolve())
    if not results:
        return None
    return results[0]


def get_disease_by_mondo(mondo_id: str) -> dict | None:
    """Get disease entity from TypeDB by MONDO ID."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(f'''
                match $d isa apt-disease, has apt-mondo-id "{escape_string(mondo_id)}";
                fetch {{
                    "id": $d.id,
                    "name": $d.name,
                    "mondo_id": $d.apt-mondo-id
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
# DISEASE DISCOVERY
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


def cmd_init_investigation(args):
    """Initialize precision therapeutics investigation from MONDO ID."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    # Check if already in TypeDB (idempotent)
    existing = get_disease_by_mondo(mondo_id)
    if existing:
        print(json.dumps({
            "success": True,
            "disease_id": existing["id"],
            "name": existing["name"],
            "message": "Investigation already initialized",
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
    disease_id = generate_id("apt-disease")
    investigation_id = generate_id("apt-investigation")
    artifact_id = generate_id("apt-artifact")

    with get_driver() as driver:
        # Insert disease entity
        disease_query = f'''insert $d isa apt-disease,
            has id "{disease_id}",
            has name "{escape_string(name)}",
            has apt-mondo-id "{escape_string(mondo_id)}",
            has created-at {timestamp}'''
        if description:
            disease_query += f', has description "{escape_string(description)}"'
        if omim_id:
            disease_query += f', has apt-omim-id "{escape_string(omim_id)}"'
        if orpha_id:
            disease_query += f', has apt-orpha-id "{escape_string(orpha_id)}"'
        if gard_id:
            disease_query += f', has apt-gard-id "{escape_string(gard_id)}"'
        if doid_id:
            disease_query += f', has apt-doid-id "{escape_string(doid_id)}"'
        if ncit_id:
            disease_query += f', has apt-ncit-id "{escape_string(ncit_id)}"'
        if inheritance:
            disease_query += f', has apt-inheritance-pattern "{escape_string(inheritance)}"'
        disease_query += ";"

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(disease_query).resolve()
            tx.commit()

        # Insert investigation collection
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''insert $i isa apt-investigation,
                has id "{investigation_id}",
                has name "APT Investigation: {escape_string(name)}",
                has apt-mondo-id "{escape_string(mondo_id)}",
                has apt-investigation-status "active",
                has created-at {timestamp};''').resolve()
            tx.commit()

        # Add disease to investigation via collection-membership
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $d isa apt-disease, has id "{disease_id}";
                $i isa apt-investigation, has id "{investigation_id}";
            insert (collection: $i, member: $d) isa collection-membership;''').resolve()
            tx.commit()

    # Store MONDO record artifact
    raw_json = json.dumps(data, indent=2)
    mondo_extra = f', has apt-mondo-id "{escape_string(mondo_id)}"'
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="apt-mondo-record",
        name=f"MONDO record: {name}",
        content=raw_json,
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}",
        extra_attrs=mondo_extra,
    )

    # Link artifact to disease
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $a isa apt-mondo-record, has id "{artifact_id}";
                $d isa apt-disease, has id "{disease_id}";
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
            f"  ingest-disease --mondo-id {mondo_id}\n"
            f"  # OR step-by-step:\n"
            f"  ingest-phenotypes --disease {disease_id}\n"
            f"  ingest-genes --disease {disease_id}\n"
            f"  ingest-hierarchy --disease {disease_id}\n"
            f"  ingest-drugs --disease {disease_id}\n"
            f"  ingest-clintrials --disease {disease_id}"
        ),
    }, indent=2))


def cmd_list_investigations(args):
    """List all APT investigations in TypeDB."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query('''
                match $i isa apt-investigation;
                fetch {
                    "id": $i.id,
                    "name": $i.name,
                    "mondo_id": $i.apt-mondo-id,
                    "status": $i.apt-investigation-status,
                    "created_at": $i.created-at
                };
            ''').resolve())

    print(json.dumps({"success": True, "count": len(results), "investigations": results}, indent=2))


# =============================================================================
# AUTOMATED INGESTION
# =============================================================================


def cmd_ingest_disease(args):
    """Full ingestion pipeline for a MONDO disease."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    # Ensure disease is initialized
    existing = get_disease_by_mondo(mondo_id)
    if not existing:
        print(json.dumps({"success": False, "error": f"Disease not initialized. Run: init-investigation {mondo_id}"}))
        return

    disease_id = existing["id"]
    results = {"disease_id": disease_id, "mondo_id": mondo_id, "steps": {}}

    # Run all ingestion steps
    for step, func, step_args in [
        ("phenotypes", cmd_ingest_phenotypes, type("A", (), {"disease": disease_id})()),
        ("genes", cmd_ingest_genes, type("A", (), {"disease": disease_id})()),
        ("hierarchy", cmd_ingest_hierarchy, type("A", (), {"disease": disease_id})()),
        ("clintrials", cmd_ingest_clintrials, type("A", (), {"disease": disease_id})()),
        ("drugs", cmd_ingest_drugs, type("A", (), {"disease": disease_id})()),
    ]:
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            func(step_args)
        try:
            step_result = json.loads(buf.getvalue())
        except json.JSONDecodeError:
            step_result = {"raw": buf.getvalue()[:200]}
        results["steps"][step] = step_result

    results["success"] = True
    results["message"] = f"Full ingestion complete for {mondo_id}. Run: show-mechanisms --mondo-id {mondo_id}"
    print(json.dumps(results, indent=2))


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

    params = {"limit": 500}
    data = monarch_get(f"/entity/{mondo_id}/biolink:DiseaseToPhenotypicFeatureAssociation", params)
    if "error" in data:
        print(json.dumps({"success": False, "error": data["error"]}))
        return

    associations = data.get("items", [])
    timestamp = get_timestamp()
    inserted = skipped = 0

    with get_driver() as driver:
        for assoc in associations:
            hpo_id = assoc.get("object", "")
            hpo_label = assoc.get("object_label") or hpo_id

            if not hpo_id or not hpo_id.startswith("HP:"):
                skipped += 1
                continue

            # Map frequency qualifier
            freq_qualifier = "unknown"
            fq = assoc.get("frequency_qualifier") or ""
            if fq in HPO_FREQUENCY_MAP:
                freq_qualifier = HPO_FREQUENCY_MAP[fq]
            elif fq.startswith("HP:"):
                freq_qualifier = fq
            else:
                pct = assoc.get("has_percentage")
                if pct is not None:
                    try:
                        p = float(pct)
                        if p >= 100:
                            freq_qualifier = "obligate"
                        elif p >= 80:
                            freq_qualifier = "very-frequent"
                        elif p >= 30:
                            freq_qualifier = "frequent"
                        elif p >= 5:
                            freq_qualifier = "occasional"
                        elif p >= 1:
                            freq_qualifier = "rare"
                        else:
                            freq_qualifier = "very-rare"
                    except (ValueError, TypeError):
                        freq_qualifier = "unknown"

            evidence_code = ""
            for ev in (assoc.get("has_evidence") or []):
                evidence_code = ev.get("id", ev) if isinstance(ev, dict) else str(ev)
                break

            # Upsert phenotype entity
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_p = list(tx.query(f'''
                    match $p isa apt-phenotype, has apt-hpo-id "{escape_string(hpo_id)}";
                    fetch {{ "id": $p.id }};
                ''').resolve())

            if existing_p:
                phenotype_id = existing_p[0]["id"]
            else:
                phenotype_id = generate_id("apt-phenotype")
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(f'''insert $p isa apt-phenotype,
                        has id "{phenotype_id}",
                        has name "{escape_string(hpo_label)}",
                        has apt-hpo-id "{escape_string(hpo_id)}",
                        has apt-hpo-label "{escape_string(hpo_label)}",
                        has created-at {timestamp};''').resolve()
                    tx.commit()

            # Check if disease-has-phenotype relation already exists
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                rel_exists = list(tx.query(f'''
                    match
                        $d isa apt-disease, has id "{escape_string(args.disease)}";
                        $p isa apt-phenotype, has id "{phenotype_id}";
                        (disease: $d, phenotype: $p) isa apt-disease-has-phenotype;
                    fetch {{ "disease_id": $d.id }};
                ''').resolve())

            if not rel_exists:
                rel_query = f'''match
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                    $p isa apt-phenotype, has id "{phenotype_id}";
                insert (disease: $d, phenotype: $p) isa apt-disease-has-phenotype,
                    has apt-frequency-qualifier "{escape_string(freq_qualifier)}"'''
                if evidence_code:
                    rel_query += f', has apt-evidence-code "{escape_string(evidence_code)}"'
                rel_query += ";"
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(rel_query).resolve()
                    tx.commit()
                inserted += 1
            else:
                skipped += 1

    # Store association artifact
    artifact_id = generate_id("apt-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="apt-monarch-assoc-record",
        name=f"Phenotype associations: {disease_name}",
        content=json.dumps(data, indent=2),
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}/biolink:DiseaseToPhenotypicFeatureAssociation",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "mondo_id": mondo_id,
        "total_associations": len(associations),
        "inserted": inserted,
        "skipped_or_updated": skipped,
        "artifact_id": artifact_id,
        "message": f"Ingested {inserted} phenotypes. Run: show-phenome --disease {args.disease}",
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

    for biolink_cat, rel_type in [
        ("biolink:CausalGeneToDiseaseAssociation", "causal"),
        ("biolink:CorrelatedGeneToDiseaseAssociation", "correlated"),
    ]:
        params = {"limit": 200}
        data = monarch_get(f"/entity/{mondo_id}/{biolink_cat}", params)
        if "error" in data:
            print(json.dumps({"success": False, "error": f"{rel_type}: {data['error']}"}))
            return
        all_data[rel_type] = data

        for assoc in data.get("items", []):
            gene_id_raw = assoc.get("subject", "")
            gene_symbol = assoc.get("subject_label") or gene_id_raw
            gene_name = gene_symbol

            if not gene_id_raw or not (gene_id_raw.startswith("HGNC:") or gene_id_raw.startswith("NCBIGene:")):
                skipped += 1
                continue

            hgnc_id = gene_id_raw if gene_id_raw.startswith("HGNC:") else ""
            entrez_id = gene_id_raw.replace("NCBIGene:", "") if gene_id_raw.startswith("NCBIGene:") else ""

            # Upsert gene entity
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                    if hgnc_id:
                        existing_g = list(tx.query(f'''
                            match $g isa apt-gene, has apt-hgnc-id "{escape_string(hgnc_id)}";
                            fetch {{ "id": $g.id }};
                        ''').resolve())
                    else:
                        existing_g = list(tx.query(f'''
                            match $g isa apt-gene, has apt-gene-symbol "{escape_string(gene_symbol)}";
                            fetch {{ "id": $g.id }};
                        ''').resolve())

            if existing_g:
                gene_entity_id = existing_g[0]["id"]
            else:
                gene_entity_id = generate_id("apt-gene")
                gene_insert = f'''insert $g isa apt-gene,
                    has id "{gene_entity_id}",
                    has name "{escape_string(gene_name)}",
                    has apt-gene-symbol "{escape_string(gene_symbol)}",
                    has created-at {timestamp}'''
                if hgnc_id:
                    gene_insert += f', has apt-hgnc-id "{escape_string(hgnc_id)}"'
                if entrez_id:
                    gene_insert += f', has apt-entrez-id "{escape_string(entrez_id)}"'
                gene_insert += ";"
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                        tx.query(gene_insert).resolve()
                        tx.commit()

            confidence = assoc.get("score")
            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = None

            if rel_type == "causal":
                rel_query = f'''match
                    $g isa apt-gene, has id "{gene_entity_id}";
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                insert (gene: $g, disease: $d) isa apt-gene-causes-disease'''
                if confidence is not None:
                    rel_query += f", has confidence {confidence}"
                rel_query += ";"
                causal_inserted += 1
            else:
                rel_query = f'''match
                    $g isa apt-gene, has id "{gene_entity_id}";
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                insert (gene: $g, disease: $d) isa apt-gene-associated-with,
                    has apt-association-type "correlated"'''
                if confidence is not None:
                    rel_query += f", has confidence {confidence}"
                rel_query += ";"
                assoc_inserted += 1

            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(rel_query).resolve()
                    tx.commit()

    # Store artifact
    artifact_id = generate_id("apt-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="apt-monarch-assoc-record",
        name=f"Gene associations: {disease_name}",
        content=json.dumps(all_data, indent=2),
        mime_type="application/json",
        source_uri=f"{MONARCH_BASE_URL}/entity/{mondo_id}/associations-combined",
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
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                    (referent: $d, artifact: $a) isa representation;
                    $a isa apt-mondo-record;
                fetch {{
                    "id": $a.id,
                    "content": $a.content,
                    "cache-path": $a.cache-path
                }};
            ''').resolve())

    if not artifacts:
        print(json.dumps({
            "success": False,
            "error": "No MONDO record artifact found. Run init-investigation first.",
        }))
        return

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

    super_classes = []
    node_hierarchy = data.get("node_hierarchy", {})
    if isinstance(node_hierarchy, dict):
        super_classes = node_hierarchy.get("super_classes", [])
    if not super_classes:
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

        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_parent = list(tx.query(f'''
                    match $d isa apt-disease, has apt-mondo-id "{escape_string(parent_mondo_id)}";
                    fetch {{ "id": $d.id }};
                ''').resolve())

        if existing_parent:
            parent_id = existing_parent[0]["id"]
        else:
            parent_id = generate_id("apt-disease")
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(f'''insert $d isa apt-disease,
                        has id "{parent_id}",
                        has name "{escape_string(parent_name)}",
                        has apt-mondo-id "{escape_string(parent_mondo_id)}",
                        has created-at {timestamp};''').resolve()
                    tx.commit()

        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''match
                    $child isa apt-disease, has id "{escape_string(args.disease)}";
                    $parent isa apt-disease, has id "{parent_id}";
                insert (child-disease: $child, parent-disease: $parent) isa apt-disease-subclass-of;''').resolve()
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
            "No hierarchy data found in MONDO artifact."
        ),
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
    headers = {"Accept": "application/json", "User-Agent": "Alhazen-APT/1.0"}

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

        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                existing_t = list(tx.query(f'''
                    match $t isa apt-clinical-trial, has apt-nct-id "{escape_string(nct_id)}";
                    fetch {{ "id": $t.id }};
                ''').resolve())

        if existing_t:
            trial_id = existing_t[0]["id"]
        else:
            trial_id = generate_id("apt-trial")
            trial_insert = f'''insert $t isa apt-clinical-trial,
                has id "{trial_id}",
                has name "{escape_string(title[:200])}",
                has apt-nct-id "{escape_string(nct_id)}",
                has apt-trial-status "{escape_string(trial_status)}",
                has apt-trial-phase "{escape_string(trial_phase)}",
                has created-at {timestamp};'''
            with get_driver() as driver:
                with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                    tx.query(trial_insert).resolve()
                    tx.commit()

        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''match
                    $t isa apt-clinical-trial, has id "{trial_id}";
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                insert (trial: $t, disease: $d) isa apt-trial-studies;''').resolve()
                tx.commit()
        inserted += 1

    # Store artifact
    artifact_id = generate_id("apt-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="apt-clintrials-record",
        name=f"Clinical trials: {disease_name}",
        content=json.dumps(data, indent=2),
        mime_type="application/json",
        source_uri=f"{CLINTRIALS_BASE_URL}/studies?query.cond={disease_name}",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "total_studies": len(studies),
        "inserted": inserted,
        "skipped": skipped,
        "artifact_id": artifact_id,
        "message": f"Ingested {inserted} clinical trials.",
    }, indent=2))


def cmd_ingest_drugs(args):
    """Ingest drug candidates from ChEMBL for causal genes."""
    if not REQUESTS_AVAILABLE:
        print(json.dumps({"success": False, "error": "requests not installed"}))
        return

    # Get causal genes for this disease
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            genes = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(args.disease)}";
                    (gene: $g, disease: $d) isa apt-gene-causes-disease;
                fetch {{
                    "id": $g.id,
                    "name": $g.name,
                    "symbol": $g.apt-gene-symbol,
                    "hgnc_id": $g.apt-hgnc-id,
                    "entrez_id": $g.apt-entrez-id
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
    all_data = {}

    for gene in genes:
        symbol = gene.get("symbol") or gene.get("name", "")
        if not symbol:
            continue

        # ChEMBL: search for targets by gene symbol
        try:
            resp = requests.get(
                f"{CHEMBL_BASE_URL}/target.json",
                params={"target_synonym__icontains": symbol, "limit": 5},
                headers={"Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            target_data = resp.json()
        except Exception as e:
            all_data[symbol] = {"error": str(e)}
            continue

        targets = target_data.get("targets", [])
        all_data[symbol] = {"targets": targets}

        for target in targets[:3]:
            chembl_target_id = target.get("target_chembl_id", "")
            if not chembl_target_id:
                continue

            # Get drugs for this target
            try:
                resp2 = requests.get(
                    f"{CHEMBL_BASE_URL}/activity.json",
                    params={
                        "target_chembl_id": chembl_target_id,
                        "limit": 20,
                        "pchembl_value__isnull": False,
                    },
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                resp2.raise_for_status()
                activity_data = resp2.json()
            except Exception:
                continue

            for activity in activity_data.get("activities", []):
                mol_id = activity.get("molecule_chembl_id", "")
                mol_name = activity.get("molecule_pref_name") or mol_id
                moa = activity.get("mechanism_of_action") or f"target: {symbol}"

                if not mol_id:
                    continue

                # Upsert drug
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                        existing_drug = list(tx.query(f'''
                            match $dr isa apt-drug, has apt-chembl-id "{escape_string(mol_id)}";
                            fetch {{ "id": $dr.id }};
                        ''').resolve())

                if existing_drug:
                    drug_id = existing_drug[0]["id"]
                else:
                    drug_id = generate_id("apt-drug")
                    with get_driver() as driver:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            tx.query(f'''insert $dr isa apt-drug,
                                has id "{drug_id}",
                                has name "{escape_string(str(mol_name)[:200])}",
                                has apt-chembl-id "{escape_string(mol_id)}",
                                has apt-mechanism-of-action "{escape_string(str(moa)[:300])}",
                                has apt-development-stage "investigational",
                                has created-at {timestamp};''').resolve()
                            tx.commit()
                    total_drugs += 1

                # Link drug to causal gene
                gene_id = gene.get("id")
                with get_driver() as driver:
                    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                        link_exists = list(tx.query(f'''
                            match
                                $dr isa apt-drug, has id "{drug_id}";
                                $g isa apt-gene, has id "{escape_string(gene_id)}";
                                (drug: $dr, target-gene: $g) isa apt-drug-targets;
                            fetch {{ "drug_id": $dr.id }};
                        ''').resolve())

                if not link_exists:
                    with get_driver() as driver:
                        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                            tx.query(f'''match
                                $dr isa apt-drug, has id "{drug_id}";
                                $g isa apt-gene, has id "{escape_string(gene_id)}";
                            insert (drug: $dr, target-gene: $g) isa apt-drug-targets,
                                has apt-mechanism-of-action "{escape_string(str(moa)[:300])}",
                                has provenance "ChEMBL";''').resolve()
                            tx.commit()

    # Store artifact
    artifact_id = generate_id("apt-artifact")
    save_artifact(
        artifact_id=artifact_id,
        artifact_type="apt-chembl-record",
        name=f"ChEMBL drug data: {args.disease}",
        content=json.dumps(all_data, indent=2),
        mime_type="application/json",
        source_uri=f"{CHEMBL_BASE_URL}/",
    )

    print(json.dumps({
        "success": True,
        "disease_id": args.disease,
        "genes_queried": len(genes),
        "drugs_inserted": total_drugs,
        "artifact_id": artifact_id,
        "message": f"Ingested {total_drugs} drugs from ChEMBL.",
    }, indent=2))


# =============================================================================
# MANUAL ENTITY MANAGEMENT
# =============================================================================


def cmd_add_mechanism(args):
    """Add a mechanism of harm entity."""
    timestamp = get_timestamp()
    mechanism_id = generate_id("apt-mechanism")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''insert $m isa apt-mechanism,
                has id "{mechanism_id}",
                has name "{escape_string(args.description[:200])}",
                has apt-mechanism-type "{escape_string(args.type)}",
                has apt-mechanism-level "{escape_string(args.level)}",
                has created-at {timestamp}'''
            if args.description:
                query += f', has description "{escape_string(args.description)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

        # Link to disease
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $m isa apt-mechanism, has id "{mechanism_id}";
                $d isa apt-disease, has id "{escape_string(args.disease)}";
            insert (mechanism: $m, disease: $d) isa apt-disease-has-mechanism;''').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "mechanism_id": mechanism_id,
        "disease_id": args.disease,
        "type": args.type,
        "level": args.level,
        "message": f"Added mechanism {mechanism_id}. Link to gene: link-mechanism-gene --mechanism {mechanism_id} --gene GENE_ID",
    }, indent=2))


def cmd_add_gene(args):
    """Add a gene entity."""
    timestamp = get_timestamp()
    gene_id = generate_id("apt-gene")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''insert $g isa apt-gene,
                has id "{gene_id}",
                has name "{escape_string(args.symbol)}",
                has apt-gene-symbol "{escape_string(args.symbol)}",
                has created-at {timestamp}'''
            if args.hgnc_id:
                query += f', has apt-hgnc-id "{escape_string(args.hgnc_id)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

    print(json.dumps({"success": True, "gene_id": gene_id, "symbol": args.symbol}, indent=2))


def cmd_add_drug(args):
    """Add a drug entity."""
    timestamp = get_timestamp()
    drug_id = generate_id("apt-drug")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''insert $dr isa apt-drug,
                has id "{drug_id}",
                has name "{escape_string(args.name)}",
                has created-at {timestamp}'''
            if args.chembl_id:
                query += f', has apt-chembl-id "{escape_string(args.chembl_id)}"'
            if args.modality:
                query += f', has apt-therapeutic-modality "{escape_string(args.modality)}"'
            if args.moa:
                query += f', has apt-mechanism-of-action "{escape_string(args.moa)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

    print(json.dumps({"success": True, "drug_id": drug_id, "name": args.name}, indent=2))


def cmd_add_strategy(args):
    """Add a therapeutic strategy entity."""
    timestamp = get_timestamp()
    strategy_id = generate_id("apt-strategy")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''insert $s isa apt-therapeutic-strategy,
                has id "{strategy_id}",
                has name "{escape_string(args.rationale[:200])}",
                has apt-therapeutic-approach "{escape_string(args.modality)}",
                has apt-therapeutic-modality "{escape_string(args.modality)}",
                has created-at {timestamp}'''
            if args.rationale:
                query += f', has description "{escape_string(args.rationale)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

        # Link to mechanism
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $s isa apt-therapeutic-strategy, has id "{strategy_id}";
                $m isa apt-mechanism, has id "{escape_string(args.mechanism)}";
            insert (strategy: $s, mechanism: $m) isa apt-strategy-targets-mechanism;''').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "strategy_id": strategy_id,
        "mechanism_id": args.mechanism,
        "message": f"Added strategy. Link to drug: link-drug-mechanism --drug DRUG_ID --mechanism {args.mechanism}",
    }, indent=2))


def cmd_add_phenotype(args):
    """Add a phenotype entity and link to disease."""
    timestamp = get_timestamp()

    # Upsert phenotype
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            existing = list(tx.query(f'''
                match $p isa apt-phenotype, has apt-hpo-id "{escape_string(args.hpo_id)}";
                fetch {{ "id": $p.id }};
            ''').resolve())

    if existing:
        phenotype_id = existing[0]["id"]
    else:
        phenotype_id = generate_id("apt-phenotype")
        with get_driver() as driver:
            with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
                tx.query(f'''insert $p isa apt-phenotype,
                    has id "{phenotype_id}",
                    has name "{escape_string(args.hpo_id)}",
                    has apt-hpo-id "{escape_string(args.hpo_id)}",
                    has created-at {timestamp};''').resolve()
                tx.commit()

    # Link to disease
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''match
                $d isa apt-disease, has id "{escape_string(args.disease)}";
                $p isa apt-phenotype, has id "{phenotype_id}";
            insert (disease: $d, phenotype: $p) isa apt-disease-has-phenotype'''
            if args.frequency:
                query += f', has apt-frequency-qualifier "{escape_string(args.frequency)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

    print(json.dumps({"success": True, "phenotype_id": phenotype_id, "hpo_id": args.hpo_id}, indent=2))


def cmd_link_mechanism_gene(args):
    """Link a mechanism to a gene."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $m isa apt-mechanism, has id "{escape_string(args.mechanism)}";
                $g isa apt-gene, has id "{escape_string(args.gene)}";
            insert (mechanism: $m, gene: $g) isa apt-mechanism-involves-gene;''').resolve()
            tx.commit()

    print(json.dumps({"success": True, "mechanism_id": args.mechanism, "gene_id": args.gene}, indent=2))


def cmd_link_mechanism_phenotype(args):
    """Link a mechanism to a phenotype (mechanism causes phenotype)."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $m isa apt-mechanism, has id "{escape_string(args.mechanism)}";
                $p isa apt-phenotype, has id "{escape_string(args.phenotype)}";
            insert (mechanism: $m, phenotype: $p) isa apt-mechanism-causes-phenotype;''').resolve()
            tx.commit()

    print(json.dumps({"success": True, "mechanism_id": args.mechanism, "phenotype_id": args.phenotype}, indent=2))


def cmd_link_drug_mechanism(args):
    """Link a drug to a mechanism via therapeutic strategy."""
    timestamp = get_timestamp()
    strategy_id = generate_id("apt-strategy")

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''insert $s isa apt-therapeutic-strategy,
                has id "{strategy_id}",
                has name "Strategy: drug {args.drug} -> mechanism {args.mechanism}",
                has apt-therapeutic-approach "pharmacological",
                has apt-therapeutic-modality "small-molecule",
                has created-at {timestamp};''').resolve()
            tx.commit()

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $s isa apt-therapeutic-strategy, has id "{strategy_id}";
                $m isa apt-mechanism, has id "{escape_string(args.mechanism)}";
            insert (strategy: $s, mechanism: $m) isa apt-strategy-targets-mechanism;''').resolve()
            tx.commit()

        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $s isa apt-therapeutic-strategy, has id "{strategy_id}";
                $dr isa apt-drug, has id "{escape_string(args.drug)}";
            insert (strategy: $s, drug: $dr) isa apt-strategy-implements;''').resolve()
            tx.commit()

    print(json.dumps({
        "success": True,
        "strategy_id": strategy_id,
        "drug_id": args.drug,
        "mechanism_id": args.mechanism,
    }, indent=2))


def cmd_link_drug_target(args):
    """Link a drug to a gene target."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            query = f'''match
                $dr isa apt-drug, has id "{escape_string(args.drug)}";
                $g isa apt-gene, has id "{escape_string(args.gene)}";
            insert (drug: $dr, target-gene: $g) isa apt-drug-targets'''
            if args.moa:
                query += f', has apt-mechanism-of-action "{escape_string(args.moa)}"'
            query += ";"
            tx.query(query).resolve()
            tx.commit()

    print(json.dumps({"success": True, "drug_id": args.drug, "gene_id": args.gene}, indent=2))


# =============================================================================
# ARTIFACT INSPECTION
# =============================================================================


def cmd_list_artifacts(args):
    """List artifacts, optionally filtered by disease."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            if args.disease:
                results = list(tx.query(f'''
                    match
                        $d isa apt-disease, has id "{escape_string(args.disease)}";
                        (referent: $d, artifact: $a) isa representation;
                    fetch {{
                        "id": $a.id,
                        "name": $a.name,
                        "source_uri": $a.source-uri,
                        "created_at": $a.created-at
                    }};
                ''').resolve())
            else:
                results = list(tx.query('''
                    match $a isa artifact;
                    fetch {
                        "id": $a.id,
                        "name": $a.name,
                        "source_uri": $a.source-uri,
                        "created_at": $a.created-at
                    };
                ''').resolve())

    print(json.dumps({"success": True, "count": len(results), "artifacts": results}, indent=2))


def cmd_show_artifact(args):
    """Get artifact content for sensemaking."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(f'''
                match $a isa artifact, has id "{escape_string(args.id)}";
                fetch {{
                    "id": $a.id,
                    "name": $a.name,
                    "content": $a.content,
                    "cache-path": $a.cache-path,
                    "source_uri": $a.source-uri
                }};
            ''').resolve())

    if not results:
        print(json.dumps({"success": False, "error": f"Artifact not found: {args.id}"}))
        return

    art = results[0]
    cache_path = art.get("cache-path")
    if cache_path and CACHE_AVAILABLE:
        try:
            content = load_from_cache_text(cache_path)
            art["content"] = content
        except FileNotFoundError:
            pass

    print(json.dumps({"success": True, "artifact": art}, indent=2))


# =============================================================================
# ANALYSIS VIEWS
# =============================================================================


def cmd_show_disease(args):
    """Full disease overview."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_id = disease["id"]

    with get_driver() as driver:
        # Full disease details
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            details = list(tx.query(f'''
                match $d isa apt-disease, has id "{escape_string(disease_id)}";
                fetch {{
                    "id": $d.id,
                    "name": $d.name,
                    "description": $d.description,
                    "mondo_id": $d.apt-mondo-id,
                    "omim_id": $d.apt-omim-id,
                    "orpha_id": $d.apt-orpha-id,
                    "gard_id": $d.apt-gard-id,
                    "inheritance_pattern": $d.apt-inheritance-pattern,
                    "prevalence": $d.apt-prevalence,
                    "age_of_onset": $d.apt-age-of-onset,
                    "created_at": $d.created-at
                }};
            ''').resolve())

        # Mechanism count
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            mechanisms = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, mechanism: $m) isa apt-disease-has-mechanism;
                fetch {{
                    "id": $m.id,
                    "name": $m.name,
                    "type": $m.apt-mechanism-type,
                    "level": $m.apt-mechanism-level
                }};
            ''').resolve())

        # Causal genes
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            causal_genes = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (gene: $g, disease: $d) isa apt-gene-causes-disease;
                fetch {{
                    "id": $g.id,
                    "symbol": $g.apt-gene-symbol,
                    "hgnc_id": $g.apt-hgnc-id
                }};
            ''').resolve())

        # Phenotype count
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            phenotypes = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, phenotype: $p) isa apt-disease-has-phenotype;
                fetch {{ "id": $p.id }};
            ''').resolve())

    result = details[0] if details else {}
    result["mechanisms"] = mechanisms
    result["causal_genes"] = causal_genes
    result["phenotype_count"] = len(phenotypes)

    print(json.dumps({"success": True, "disease": result}, indent=2))


def cmd_show_mechanisms(args):
    """Show all mechanisms with gene/pathway/phenotype links."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_id = disease["id"]

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            mechanisms = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, mechanism: $m) isa apt-disease-has-mechanism;
                fetch {{
                    "id": $m.id,
                    "name": $m.name,
                    "description": $m.description,
                    "type": $m.apt-mechanism-type,
                    "level": $m.apt-mechanism-level,
                    "functional_impact": $m.apt-functional-impact,
                    "evidence_strength": $m.apt-mechanism-evidence-strength,
                    "therapeutic_addressability": $m.apt-therapeutic-addressability
                }};
            ''').resolve())

        result_mechanisms = []
        for mech in mechanisms:
            mech_id = mech["id"]

            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                genes = list(tx.query(f'''
                    match
                        $m isa apt-mechanism, has id "{escape_string(mech_id)}";
                        (mechanism: $m, gene: $g) isa apt-mechanism-involves-gene;
                    fetch {{ "symbol": $g.apt-gene-symbol, "id": $g.id }};
                ''').resolve())

            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                phenotypes = list(tx.query(f'''
                    match
                        $m isa apt-mechanism, has id "{escape_string(mech_id)}";
                        (mechanism: $m, phenotype: $p) isa apt-mechanism-causes-phenotype;
                    fetch {{ "hpo_id": $p.apt-hpo-id, "label": $p.apt-hpo-label }};
                ''').resolve())

            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                strategies = list(tx.query(f'''
                    match
                        $m isa apt-mechanism, has id "{escape_string(mech_id)}";
                        (mechanism: $m, strategy: $s) isa apt-strategy-targets-mechanism;
                    fetch {{
                        "id": $s.id,
                        "name": $s.name,
                        "approach": $s.apt-therapeutic-approach
                    }};
                ''').resolve())

            mech["genes"] = genes
            mech["phenotypes_caused"] = phenotypes
            mech["therapeutic_strategies"] = strategies
            result_mechanisms.append(mech)

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "mondo_id": mondo_id,
        "mechanism_count": len(result_mechanisms),
        "mechanisms": result_mechanisms,
    }, indent=2))


def cmd_show_therapeutic_map(args):
    """Show therapeutic strategies per mechanism with drug evidence."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_id = disease["id"]

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            mechanisms = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, mechanism: $m) isa apt-disease-has-mechanism;
                fetch {{
                    "id": $m.id,
                    "name": $m.name,
                    "type": $m.apt-mechanism-type,
                    "addressability": $m.apt-therapeutic-addressability
                }};
            ''').resolve())

        result = []
        for mech in mechanisms:
            mech_id = mech["id"]

            with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                strategies = list(tx.query(f'''
                    match
                        $m isa apt-mechanism, has id "{escape_string(mech_id)}";
                        (mechanism: $m, strategy: $s) isa apt-strategy-targets-mechanism;
                    fetch {{
                        "id": $s.id,
                        "name": $s.name,
                        "approach": $s.apt-therapeutic-approach,
                        "modality": $s.apt-therapeutic-modality
                    }};
                ''').resolve())

            for strat in strategies:
                strat_id = strat["id"]
                with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
                    drugs = list(tx.query(f'''
                        match
                            $s isa apt-therapeutic-strategy, has id "{escape_string(strat_id)}";
                            (strategy: $s, drug: $dr) isa apt-strategy-implements;
                        fetch {{
                            "id": $dr.id,
                            "name": $dr.name,
                            "chembl_id": $dr.apt-chembl-id,
                            "stage": $dr.apt-development-stage,
                            "moa": $dr.apt-mechanism-of-action
                        }};
                    ''').resolve())
                strat["drugs"] = drugs

            mech["strategies"] = strategies
            result.append(mech)

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "therapeutic_map": result,
    }, indent=2))


def cmd_show_phenome(args):
    """Show phenotypic spectrum by frequency tier."""
    # Support both --disease and --mondo-id
    if hasattr(args, "mondo_id") and args.mondo_id:
        mondo_id = args.mondo_id
        if not mondo_id.startswith("MONDO:"):
            mondo_id = f"MONDO:{mondo_id}"
        disease = get_disease_by_mondo(mondo_id)
        if not disease:
            print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
            return
        disease_id = disease["id"]
    else:
        disease_id = args.disease

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            # Fetch with frequency (relations attrs must be bound in match, not fetched as $rel.attr)
            results_with_freq = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, phenotype: $p) isa apt-disease-has-phenotype,
                        has apt-frequency-qualifier $freq;
                fetch {{
                    "hpo_id": $p.apt-hpo-id,
                    "label": $p.apt-hpo-label,
                    "frequency": $freq
                }};
            ''').resolve())
            # Also get phenotypes without frequency qualifier
            results_no_freq = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (disease: $d, phenotype: $p) isa apt-disease-has-phenotype;
                    not {{ (disease: $d, phenotype: $p) isa apt-disease-has-phenotype,
                        has apt-frequency-qualifier $freq2; }};
                fetch {{
                    "hpo_id": $p.apt-hpo-id,
                    "label": $p.apt-hpo-label
                }};
            ''').resolve())
        results = results_with_freq + [dict(r, frequency="unknown") for r in results_no_freq]

    # Group by frequency
    by_freq = {}
    for item in results:
        freq = item.get("frequency") or "unknown"
        by_freq.setdefault(freq, []).append(item)

    ordered = []
    for f in FREQUENCY_ORDER:
        if f in by_freq:
            ordered.append({"frequency_tier": f, "count": len(by_freq[f]), "phenotypes": by_freq[f]})

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "total_phenotypes": len(results),
        "phenome": ordered,
    }, indent=2))


def cmd_show_genes(args):
    """Show causal genes with association type and evidence."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_id = disease["id"]

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            causal = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (gene: $g, disease: $d) isa apt-gene-causes-disease;
                fetch {{
                    "id": $g.id,
                    "symbol": $g.apt-gene-symbol,
                    "hgnc_id": $g.apt-hgnc-id
                }};
            ''').resolve())

        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            associated = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (gene: $g, disease: $d) isa apt-gene-associated-with;
                fetch {{
                    "id": $g.id,
                    "symbol": $g.apt-gene-symbol,
                    "hgnc_id": $g.apt-hgnc-id
                }};
            ''').resolve())

    # Add association_type in Python (can't use literals in TypeQL fetch)
    for g in causal:
        g["association_type"] = "causal"
    for g in associated:
        g["association_type"] = "correlated"

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "causal_genes": causal,
        "associated_genes": associated,
    }, indent=2))


def cmd_show_trials(args):
    """Show clinical trials landscape."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_id = disease["id"]

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            trials = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (trial: $t, disease: $d) isa apt-trial-studies;
                fetch {{
                    "id": $t.id,
                    "name": $t.name,
                    "nct_id": $t.apt-nct-id,
                    "phase": $t.apt-trial-phase,
                    "status": $t.apt-trial-status
                }};
            ''').resolve())

    # Group by phase
    by_phase = {}
    for t in trials:
        phase = t.get("phase") or "N/A"
        by_phase.setdefault(phase, []).append(t)

    print(json.dumps({
        "success": True,
        "disease_id": disease_id,
        "total_trials": len(trials),
        "by_phase": by_phase,
    }, indent=2))


# =============================================================================
# NOTES AND ORGANIZATION
# =============================================================================


def cmd_add_note(args):
    """Create a note about any entity."""
    timestamp = get_timestamp()
    note_id = generate_id("apt-note")
    note_type = args.type or "apt-disease-overview-note"

    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''insert $n isa {note_type},
                has id "{note_id}",
                has name "Note: {escape_string(args.content[:80])}",
                has content "{escape_string(args.content)}",
                has created-at {timestamp};''').resolve()
            tx.commit()

        # Link note to entity
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $n isa note, has id "{note_id}";
                $e isa entity, has id "{escape_string(args.entity)}";
            insert (noted-entity: $e, note: $n) isa annotation;''').resolve()
            tx.commit()

    print(json.dumps({"success": True, "note_id": note_id, "entity_id": args.entity}, indent=2))


def cmd_tag(args):
    """Tag an entity."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
            tx.query(f'''match
                $e isa entity, has id "{escape_string(args.entity)}";
            insert $e has tag "{escape_string(args.tag)}";''').resolve()
            tx.commit()

    print(json.dumps({"success": True, "entity_id": args.entity, "tag": args.tag}, indent=2))


def cmd_search_tag(args):
    """Search entities by tag."""
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            results = list(tx.query(f'''
                match $e isa entity, has id $eid, has tag "{escape_string(args.tag)}";
                fetch {{ "id": $e.id, "name": $e.name }};
            ''').resolve())

    print(json.dumps({"success": True, "count": len(results), "entities": results}, indent=2))


def cmd_build_corpus(args):
    """Print ready-to-run epmc-search CLI commands."""
    mondo_id = args.mondo_id
    if not mondo_id.startswith("MONDO:"):
        mondo_id = f"MONDO:{mondo_id}"

    disease = get_disease_by_mondo(mondo_id)
    if not disease:
        print(json.dumps({"success": False, "error": f"Disease not found: {mondo_id}"}))
        return

    disease_name = disease.get("name", mondo_id)
    disease_id = disease["id"]

    # Get causal gene symbols
    with get_driver() as driver:
        with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
            genes = list(tx.query(f'''
                match
                    $d isa apt-disease, has id "{escape_string(disease_id)}";
                    (gene: $g, disease: $d) isa apt-gene-causes-disease;
                fetch {{ "symbol": $g.apt-gene-symbol }};
            ''').resolve())

    gene_symbols = [g.get("symbol") for g in genes if g.get("symbol")]
    commands = []
    script = ".claude/skills/epmc-search/epmc_search.py"

    # Disease-level searches
    commands.append(f'uv run python {script} search --query "{disease_name}" --collection "{disease_name} literature" --max-results 50')
    commands.append(f'uv run python {script} search --query "{disease_name} mechanism" --collection "{disease_name} mechanism" --max-results 30')
    commands.append(f'uv run python {script} search --query "{disease_name} therapy treatment" --collection "{disease_name} therapy" --max-results 30')

    # Gene-level searches
    for sym in gene_symbols[:5]:
        commands.append(f'uv run python {script} search --query "{sym} {disease_name}" --collection "{sym} disease" --max-results 20')

    print(json.dumps({
        "success": True,
        "disease": disease_name,
        "commands": commands,
        "instructions": "Copy-paste these commands to build a literature corpus for mechanism analysis.",
    }, indent=2))


# =============================================================================
# ARGUMENT PARSER
# =============================================================================


def build_parser():
    parser = argparse.ArgumentParser(
        description="Algorithm for Precision Therapeutics - Mechanism-centered rare disease investigation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # search-disease
    p = sub.add_parser("search-disease", help="Search Monarch Initiative for diseases")
    p.add_argument("--query", required=True, help="Disease name search query")
    p.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # init-investigation
    p = sub.add_parser("init-investigation", help="Initialize investigation from MONDO ID")
    p.add_argument("mondo_id", help="MONDO disease ID (e.g. MONDO:0800044)")

    # list-investigations
    sub.add_parser("list-investigations", help="List all investigations")

    # ingest-disease
    p = sub.add_parser("ingest-disease", help="Full ingestion pipeline")
    p.add_argument("--mondo-id", required=True, help="MONDO ID")

    # ingest-phenotypes
    p = sub.add_parser("ingest-phenotypes", help="Ingest HPO phenotype associations")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # ingest-genes
    p = sub.add_parser("ingest-genes", help="Ingest causal and correlated gene associations")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # ingest-hierarchy
    p = sub.add_parser("ingest-hierarchy", help="Ingest MONDO disease hierarchy")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # ingest-clintrials
    p = sub.add_parser("ingest-clintrials", help="Ingest clinical trials")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # ingest-drugs
    p = sub.add_parser("ingest-drugs", help="Ingest drug candidates from ChEMBL")
    p.add_argument("--disease", required=True, help="Disease entity ID")

    # add-mechanism
    p = sub.add_parser("add-mechanism", help="Add a mechanism of harm entity")
    p.add_argument("--disease", required=True, help="Disease entity ID")
    p.add_argument("--type", required=True, choices=MECHANISM_TYPES, help="Mechanism type")
    p.add_argument("--level", required=True,
                   choices=["molecular", "cellular", "tissue", "systemic"],
                   help="Mechanism level")
    p.add_argument("--description", required=True, help="Mechanism description")

    # add-gene
    p = sub.add_parser("add-gene", help="Add a gene entity")
    p.add_argument("--symbol", required=True, help="Gene symbol (e.g. NGLY1)")
    p.add_argument("--hgnc-id", dest="hgnc_id", default="", help="HGNC ID")

    # add-drug
    p = sub.add_parser("add-drug", help="Add a drug entity")
    p.add_argument("--name", required=True, help="Drug name")
    p.add_argument("--chembl-id", dest="chembl_id", default="", help="ChEMBL ID")
    p.add_argument("--modality", default="", help="Therapeutic modality")
    p.add_argument("--moa", default="", help="Mechanism of action")

    # add-strategy
    p = sub.add_parser("add-strategy", help="Add a therapeutic strategy")
    p.add_argument("--mechanism", required=True, help="Mechanism entity ID")
    p.add_argument("--modality", required=True, help="Therapeutic modality")
    p.add_argument("--rationale", required=True, help="Strategy rationale")

    # add-phenotype
    p = sub.add_parser("add-phenotype", help="Add a phenotype and link to disease")
    p.add_argument("--hpo-id", dest="hpo_id", required=True, help="HPO ID (e.g. HP:0001234)")
    p.add_argument("--disease", required=True, help="Disease entity ID")
    p.add_argument("--frequency", default="", help="Frequency qualifier")

    # link-mechanism-gene
    p = sub.add_parser("link-mechanism-gene", help="Link mechanism to gene")
    p.add_argument("--mechanism", required=True, help="Mechanism entity ID")
    p.add_argument("--gene", required=True, help="Gene entity ID")

    # link-mechanism-phenotype
    p = sub.add_parser("link-mechanism-phenotype", help="Link mechanism to phenotype")
    p.add_argument("--mechanism", required=True, help="Mechanism entity ID")
    p.add_argument("--phenotype", required=True, help="Phenotype entity ID")

    # link-drug-mechanism
    p = sub.add_parser("link-drug-mechanism", help="Link drug to mechanism via strategy")
    p.add_argument("--drug", required=True, help="Drug entity ID")
    p.add_argument("--mechanism", required=True, help="Mechanism entity ID")

    # link-drug-target
    p = sub.add_parser("link-drug-target", help="Link drug to gene target")
    p.add_argument("--drug", required=True, help="Drug entity ID")
    p.add_argument("--gene", required=True, help="Gene entity ID")
    p.add_argument("--moa", default="", help="Mechanism of action")

    # list-artifacts
    p = sub.add_parser("list-artifacts", help="List artifacts")
    p.add_argument("--disease", default="", help="Filter by disease entity ID")

    # show-artifact
    p = sub.add_parser("show-artifact", help="Get artifact content")
    p.add_argument("--id", required=True, help="Artifact entity ID")

    # show-disease
    p = sub.add_parser("show-disease", help="Full disease overview")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    # show-mechanisms
    p = sub.add_parser("show-mechanisms", help="All mechanisms with links")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    # show-therapeutic-map
    p = sub.add_parser("show-therapeutic-map", help="Therapeutic strategies per mechanism")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    # show-phenome
    p = sub.add_parser("show-phenome", help="Phenotypic spectrum by frequency tier")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--disease", default="", help="Disease entity ID")
    grp.add_argument("--mondo-id", dest="mondo_id", default="", help="MONDO ID")

    # show-genes
    p = sub.add_parser("show-genes", help="Causal genes with evidence")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    # show-trials
    p = sub.add_parser("show-trials", help="Clinical trials landscape")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    # add-note
    p = sub.add_parser("add-note", help="Create a note about an entity")
    p.add_argument("--entity", required=True, help="Entity ID to annotate")
    p.add_argument("--type", default="apt-disease-overview-note", help="Note type")
    p.add_argument("--content", required=True, help="Note content")

    # tag
    p = sub.add_parser("tag", help="Tag an entity")
    p.add_argument("--entity", required=True, help="Entity ID")
    p.add_argument("--tag", required=True, help="Tag value")

    # search-tag
    p = sub.add_parser("search-tag", help="Search entities by tag")
    p.add_argument("--tag", required=True, help="Tag to search for")

    # build-corpus
    p = sub.add_parser("build-corpus", help="Print epmc-search CLI commands")
    p.add_argument("--mondo-id", dest="mondo_id", required=True, help="MONDO ID")

    return parser


COMMAND_MAP = {
    "search-disease": cmd_search_disease,
    "init-investigation": cmd_init_investigation,
    "list-investigations": cmd_list_investigations,
    "ingest-disease": cmd_ingest_disease,
    "ingest-phenotypes": cmd_ingest_phenotypes,
    "ingest-genes": cmd_ingest_genes,
    "ingest-hierarchy": cmd_ingest_hierarchy,
    "ingest-clintrials": cmd_ingest_clintrials,
    "ingest-drugs": cmd_ingest_drugs,
    "add-mechanism": cmd_add_mechanism,
    "add-gene": cmd_add_gene,
    "add-drug": cmd_add_drug,
    "add-strategy": cmd_add_strategy,
    "add-phenotype": cmd_add_phenotype,
    "link-mechanism-gene": cmd_link_mechanism_gene,
    "link-mechanism-phenotype": cmd_link_mechanism_phenotype,
    "link-drug-mechanism": cmd_link_drug_mechanism,
    "link-drug-target": cmd_link_drug_target,
    "list-artifacts": cmd_list_artifacts,
    "show-artifact": cmd_show_artifact,
    "show-disease": cmd_show_disease,
    "show-mechanisms": cmd_show_mechanisms,
    "show-therapeutic-map": cmd_show_therapeutic_map,
    "show-phenome": cmd_show_phenome,
    "show-genes": cmd_show_genes,
    "show-trials": cmd_show_trials,
    "add-note": cmd_add_note,
    "tag": cmd_tag,
    "search-tag": cmd_search_tag,
    "build-corpus": cmd_build_corpus,
}


def main():
    if not TYPEDB_AVAILABLE:
        print(json.dumps({
            "error": "TypeDB driver not available. Run: uv sync --all-extras",
        }))
        sys.exit(1)

    parser = build_parser()
    args = parser.parse_args()

    cmd = COMMAND_MAP.get(args.command)
    if not cmd:
        print(json.dumps({"error": f"Unknown command: {args.command}"}))
        sys.exit(1)

    cmd(args)


if __name__ == "__main__":
    main()
