#!/usr/bin/env python3
"""Re-key all scilit-papers to deterministic identity ids. Dry-run unless --apply.

Plan: compute new id per paper; merge collisions (same new id) by re-pointing the
extras' relations onto a survivor; swap each survivor's id @key in place (relations
survive); rewrite scilit-reference-key prefixes that embed an old citing-paper id.

Run: uv run python prototypes/migrate_paper_identity.py [--apply]
"""
import os, sys, re
from collections import defaultdict
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from kqed import escape_string
from paper_identity import paper_identity

# Relations a paper plays a role in, with the role name, for collision-merge re-pointing.
# Each entry: (relation_type, victim_role, other_role)
# We do NOT restrict the other role-player's concrete type to avoid TypeDB INF6 errors
# with abstract supertypes (e.g. 'collection' is abstract; actual type is scilit-corpus).
# Instead we match the other player only by its id attribute.
PAPER_RELATIONS = [
    # (rel_type, victim_role, other_role)
    ("alh-aboutness",             "subject",            "note"),
    ("scilit-hinge",              "hinged-to",          "hinging-claim"),
    ("alh-representation",        "referent",           "alh-artifact"),
    ("alh-collection-membership", "member",             "collection"),
    ("alh-classification",        "classified-entity",  "type-facet"),
]
# alh-derivation: scilit-paper is NOT in the derived-from-source role (that's for fragments).
# Confirmed by INF11 error during investigation; so we skip it.


def meta_of(d, pid):
    """Fetch the identity attributes of a paper by id."""
    rows = K.r(d, f'match $p isa scilit-paper, has id "{pid}"; '
                  f'fetch {{"doi": $p.scilit-doi, "pmid": $p.scilit-pmid, '
                  f'"title": $p.name}};')
    row = rows[0] if rows else {}
    return {
        "doi":   row.get("doi"),
        "pmid":  row.get("pmid"),
        "title": row.get("title"),
    }


def repoint_relations(d, victim_id, survivor_id):
    """For each relation the victim plays, re-insert with the survivor, then delete victim's.

    We do NOT constrain the concrete type of the other role-player in match clauses;
    instead we identify it only by its id attribute. This avoids TypeDB INF6 errors
    when the other player's declared type is abstract (e.g. 'collection').
    """
    for rel, victim_role, other_role in PAPER_RELATIONS:
        # Find all relations of this type where victim plays victim_role.
        # Match the other player only by id (no type constraint to avoid INF6).
        query = (f'match $v isa scilit-paper, has id "{victim_id}"; '
                 f'$r isa {rel}, links ({victim_role}: $v, {other_role}: $o); '
                 f'$o has id $oid; fetch {{"oid": $oid}};')
        try:
            rows = K.r(d, query)
        except Exception as e:
            print(f"    WARN: could not query {rel} for {victim_id}: {e}")
            rows = []

        for row in rows:
            oid = row["oid"]
            # Check if the survivor already has this relation to the same other player
            # (to avoid duplicate relations after re-pointing)
            already = K._has(d, (f'$s isa scilit-paper, has id "{survivor_id}"; '
                                  f'$o has id "{escape_string(oid)}"; '
                                  f'$r isa {rel}, links ({victim_role}: $s, {other_role}: $o);'))
            if not already:
                # Insert the equivalent relation with the survivor.
                # We match the other player by id only (no type constraint).
                K.w(d, (f'match $s isa scilit-paper, has id "{survivor_id}"; '
                         f'$o has id "{escape_string(oid)}"; '
                         f'insert ({victim_role}: $s, {other_role}: $o) isa {rel};'))
                print(f"    re-pointed {rel} ({other_role}={oid}) from {victim_id} to {survivor_id}")
            else:
                print(f"    skipped dup {rel} ({other_role}={oid}) - survivor already has it")

            # Delete the victim's relation (match by victim id + other player id).
            K.w(d, (f'match $v isa scilit-paper, has id "{victim_id}"; '
                     f'$o has id "{escape_string(oid)}"; '
                     f'$r isa {rel}, links ({victim_role}: $v, {other_role}: $o); '
                     f'delete $r;'))
            print(f"    deleted {rel} from victim {victim_id}")


def main(apply=False):
    d = K.get_driver()
    try:
        # Fetch all scilit-paper ids
        papers = [r["id"] for r in K.r(d, 'match $p isa scilit-paper, has id $id; fetch {"id": $id};')]

        newid, basis = {}, {}
        for pid in papers:
            meta = meta_of(d, pid)
            nid, tier, val = paper_identity(meta)
            newid[pid] = nid
            basis[pid] = (tier, val)

        groups = defaultdict(list)
        for pid, nid in newid.items():
            groups[nid].append(pid)

        merges = {nid: olds for nid, olds in groups.items() if len(olds) > 1}
        print(f"papers={len(papers)} target_ids={len(groups)} collisions={len(merges)}")
        for nid, olds in list(merges.items())[:10]:
            print(f"  merge {olds} -> {nid}")

        if not apply:
            print("DRY-RUN. Re-run with --apply.")
            return

        # 1. Handle collisions: merge victims into survivor
        # survivor = the paper whose old id equals nid if present, else first in list
        victim_set = set()
        for nid, olds in merges.items():
            survivor = next((p for p in olds if p == nid), olds[0])
            victims = [p for p in olds if p != survivor]
            print(f"\nMerging {victims} -> survivor={survivor} (target={nid})")
            for victim in victims:
                print(f"  Re-pointing relations from victim {victim} to survivor {survivor}")
                repoint_relations(d, victim, survivor)
                # Delete the victim entity
                K.w(d, f'match $v isa scilit-paper, has id "{victim}"; delete $v;')
                print(f"  Deleted victim {victim}")
                victim_set.add(victim)

        # Build set of victims (to skip during id-swap phase)
        all_victims = set()
        for nid, olds in merges.items():
            survivor = next((p for p in olds if p == nid), olds[0])
            all_victims.update(p for p in olds if p != survivor)

        # 2. Swap id @key for every surviving paper (skip victims, skip already-correct)
        # Re-fetch live paper ids (victims are now deleted)
        live_papers = [r["id"] for r in K.r(d, 'match $p isa scilit-paper, has id $id; fetch {"id": $id};')]
        swapped, skipped = 0, 0
        for pid in live_papers:
            if pid not in newid:
                # Paper not in original list (shouldn't happen) - skip
                continue
            nid = newid[pid]
            tier, val = basis[pid]
            if pid == nid:
                # Already at target id, just ensure identity attrs are set
                skipped += 1
            else:
                # Swap the id @key: delete old, insert new
                K.w(d, (f'match $p isa scilit-paper, has id $o; $o == "{pid}"; '
                         f'delete has $o of $p; insert $p has id "{nid}";'))
                swapped += 1
            # Set identity attrs if not present (idempotent)
            if not K._has(d, f'$p isa scilit-paper, has id "{nid}", has scilit-identity-basis $b;'):
                K.w(d, (f'match $p isa scilit-paper, has id "{nid}"; '
                         f'insert $p has scilit-identity-basis "{escape_string(tier)}", '
                         f'has scilit-identity-value "{escape_string(val)}";'))
        print(f"\nId swap: {swapped} swapped, {skipped} already at target id")

        # 3. Rewrite scilit-reference-key prefixes (old citing-paper id -> new)
        rk_rows = K.r(d, 'match $p isa scilit-paper, has scilit-reference-key $k; '
                         'fetch {"id": $p.id, "k": $k};')
        rk_rewritten = 0
        for row in rk_rows:
            k = row["k"]
            old_prefix = k.split(":")[0]
            # Only rewrite if the prefix was a paper id that got remapped
            if old_prefix in newid and newid[old_prefix] != old_prefix:
                new_prefix = newid[old_prefix]
                suffix = k.split(":", 1)[1]
                nk = new_prefix + ":" + suffix
                pid = row["id"]
                # Delete old key
                K.w(d, (f'match $p isa scilit-paper, has id "{pid}", has scilit-reference-key $x; '
                         f'$x == "{escape_string(k)}"; delete has $x of $p;'))
                # Insert new key
                K.w(d, (f'match $p isa scilit-paper, has id "{pid}"; '
                         f'insert $p has scilit-reference-key "{escape_string(nk)}";'))
                rk_rewritten += 1
        print(f"Reference-key prefixes rewritten: {rk_rewritten}")

        print("\nAPPLIED")
    finally:
        d.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
