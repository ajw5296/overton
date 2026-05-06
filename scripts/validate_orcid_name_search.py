"""Validation: run OpenAlex name search against all 235 unmapped researchers.

For each unmapped RMD researcher, queries OpenAlex:
    /authors?search=<name>&filter=ror:PSU,has_orcid:true

Classifies each result into a tier:
    - clean_match     1 hit, names look like the same person
    - single_weak     1 hit, but names don't clearly match (needs review)
    - ambiguous       2+ hits (needs disambiguation — e.g. DOI overlap)
    - no_orcid_hits   0 hits with has_orcid filter (tries fallback without)
    - not_on_openalex no PSU author by that name at all

Writes full detail to data/pipeline/orcid_search_validation.json and prints
a summary. Run: python -m scripts.validate_orcid_name_search
"""

import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import config
from pipeline.utils import api_request, load_json, save_json


def _normalize_name(name: str) -> tuple[str, str, set[str]]:
    """Return (first_token, last_token, all_tokens_lower) stripped of punctuation."""
    cleaned = name.replace(".", " ").replace(",", " ").replace("-", " ")
    tokens = [t.lower() for t in cleaned.split() if len(t) > 1]
    if not tokens:
        return "", "", set()
    return tokens[0], tokens[-1], set(tokens)


def _names_look_similar(rmd_name: str, oa_name: str) -> bool:
    """Heuristic: same last name + first-name overlap (first char or shared token).

    Generous enough to allow 'Robert' vs 'Bob' ambiguity through — we're not
    deciding the match here, just flagging whether it's worth a human look.
    """
    rf, rl, rs = _normalize_name(rmd_name)
    of, ol, os_ = _normalize_name(oa_name)
    if not rl or not ol or rl != ol:
        return False
    # First token exact match or shared first-letter counts as a plausible match
    if rf == of:
        return True
    if rf and of and rf[0] == of[0]:
        return True
    # Fall back to any token overlap besides last name
    return bool((rs - {rl}) & (os_ - {ol}))


def _search_author(name: str, require_orcid: bool) -> list[dict]:
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}
    filter_parts = [f"affiliations.institution.ror:{config.PSU_ROR}"]
    if require_orcid:
        filter_parts.append("has_orcid:true")
    data = api_request(
        f"{config.OPENALEX_BASE_URL}/authors",
        params={
            "filter": ",".join(filter_parts),
            "search": name,
            "per_page": 5,
            "select": "id,orcid,display_name,display_name_alternatives,works_count,last_known_institutions",
        },
        headers=headers,
        delay=config.OPENALEX_DELAY,
    )
    if not data:
        return []
    return data.get("results", [])


def classify(rmd_name: str) -> dict:
    """Run the search and classify the result."""
    hits = _search_author(rmd_name, require_orcid=True)

    if len(hits) == 1:
        oa_name = hits[0].get("display_name") or ""
        similar = _names_look_similar(rmd_name, oa_name)
        return {
            "tier": "clean_match" if similar else "single_weak",
            "candidates": hits,
        }

    if len(hits) > 1:
        # Score each candidate by name similarity
        scored = []
        for h in hits:
            oa_name = h.get("display_name") or ""
            scored.append({"hit": h, "similar": _names_look_similar(rmd_name, oa_name)})
        similar_count = sum(1 for s in scored if s["similar"])
        return {
            "tier": "ambiguous",
            "candidates": hits,
            "similar_count": similar_count,
        }

    # Zero hits with has_orcid filter — check if they exist at all
    fallback = _search_author(rmd_name, require_orcid=False)
    if fallback:
        return {
            "tier": "no_orcid_hits",
            "candidates": fallback[:3],
        }
    return {
        "tier": "not_on_openalex",
        "candidates": [],
    }


def main() -> None:
    report_path = config.DATA_DIR / "orcid_coverage_report.json"
    report = json.loads(report_path.read_text())
    unmapped = report["unmapped_no_profile_orcid"]
    print(f"Loaded {len(unmapped)} unmapped researchers\n")

    results = []
    tier_counts = {
        "clean_match": 0,
        "single_weak": 0,
        "ambiguous": 0,
        "no_orcid_hits": 0,
        "not_on_openalex": 0,
    }

    for u in tqdm(unmapped, desc="OpenAlex name search"):
        name = u["name"]
        if not name:
            tier_counts["not_on_openalex"] += 1
            results.append({**u, "tier": "not_on_openalex", "candidates": []})
            continue
        classification = classify(name)
        tier_counts[classification["tier"]] += 1
        results.append({**u, **classification})

    total = len(unmapped)
    print("\n=== Validation Summary ===")
    print(f"Total unmapped researchers searched: {total}")
    for tier, count in tier_counts.items():
        pct = (count / total * 100) if total else 0
        print(f"  {tier:<20} {count:>4}   ({pct:.1f}%)")

    reachable = tier_counts["clean_match"] + tier_counts["ambiguous"] + tier_counts["single_weak"]
    print(f"\n  Reachable (has at least one ORCID candidate): {reachable}")
    print(f"  Not reachable via this method:                 {total - reachable}")

    out_path = config.DATA_DIR / "orcid_search_validation.json"
    save_json(
        {
            "summary": {"total": total, "tiers": tier_counts},
            "results": results,
        },
        out_path,
    )
    print(f"\nWrote detail to {out_path}")


if __name__ == "__main__":
    main()
