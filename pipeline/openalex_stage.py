"""Stage 2: Enrich researchers with OpenAlex academic metadata + full DOI list.

For each researcher in the database:
  1. Resolve the OpenAlex author record:
       - by ORCID if we have one
       - else by name+PSU-ROR search, accepting only on (PSU last_known_institution
         + name match per pipeline.name_match)
  2. Pull aggregate metrics (h-index, topics, affiliations, etc.).
  3. Pull the full works list and collect DOIs.
  4. Run a disambiguation guard: if the OA-vs-RMD DOI overlap is implausibly low
     and OA's works count is implausibly large, flag the researcher and drop the
     OA DOI list (keep just RMD's). Suspects go to a review file.

The full DOI list lives at researcher.data.openalex.works_dois — Stage 3 (Overton)
batches them into a DOI set for citation lookups.
"""

import logging
import urllib.parse
from datetime import datetime
from tqdm import tqdm

from . import config, name_match
from .utils import api_request, save_json, now_iso, days_since
from .db.operations import get_all_researchers, upsert_researcher
from .db.s3_client import upload_raw_response

logger = logging.getLogger("pipeline.openalex")

# Disambiguation thresholds — if BOTH conditions are true, flag suspect.
SUSPECT_OVERLAP_FRAC = 0.10   # less than 10% of RMD DOIs appear in OA's works
SUSPECT_EXPANSION = 5.0       # OA has 5x+ more works than RMD


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return (doi.lower().strip()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .rstrip("."))


def _lookup_by_orcid(orcid: str, headers: dict) -> dict | None:
    """Direct lookup of OpenAlex author by ORCID."""
    return api_request(
        f"{config.OPENALEX_BASE_URL}/authors/orcid:{orcid}",
        headers=headers,
        delay=config.OPENALEX_DELAY,
    )


def _lookup_by_name(rmd_name: str, headers: dict) -> tuple[dict | None, str]:
    """Search OpenAlex for a PSU author matching `rmd_name`.

    Returns (author_record, decision). Decision is one of:
        'accept'  — auto-accept (PSU last_known_institution + matched name)
        'review'  — borderline match, written to review file (NOT used)
        'reject'  — no plausible match
    """
    if not rmd_name:
        return None, "reject"

    data = api_request(
        f"{config.OPENALEX_BASE_URL}/authors",
        params={
            "filter": f"affiliations.institution.ror:{config.PSU_ROR}",
            "search": rmd_name,
            "per-page": 5,
            "select": "id,orcid,display_name,display_name_alternatives,works_count,last_known_institutions,affiliations,summary_stats,topics",
        },
        headers=headers,
        delay=config.OPENALEX_DELAY,
    )
    if not data or not data.get("results"):
        return None, "reject"

    # Walk candidates; auto-accept first one with PSU last_known + accepted name match
    review_candidates = []
    for cand in data["results"]:
        oa_name = cand.get("display_name") or ""
        result = name_match.match(rmd_name, oa_name)

        last_known = cand.get("last_known_institutions") or []
        is_psu = any((i.get("ror") or "") == config.PSU_ROR for i in last_known)

        if result.decision == "accept" and is_psu:
            return cand, "accept"
        if result.decision in ("accept", "review"):
            review_candidates.append({
                "rmd_name": rmd_name,
                "oa_name": oa_name,
                "oa_id": cand.get("id"),
                "oa_orcid": cand.get("orcid"),
                "tier": result.tier,
                "score": result.score,
                "is_psu_last_known": is_psu,
                "works_count": cand.get("works_count"),
            })

    return ({"_review_candidates": review_candidates} if review_candidates else None), "review"


def _pull_works_dois(author_id: str, headers: dict, max_pages: int = 25) -> list[str]:
    """Page through `/works?filter=author.id:X` and collect normalized DOIs."""
    if not author_id:
        return []
    short_id = author_id.replace("https://openalex.org/", "")

    dois: list[str] = []
    cursor = "*"
    pages = 0
    while cursor and pages < max_pages:
        pages += 1
        d = api_request(
            f"{config.OPENALEX_BASE_URL}/works",
            params={
                "filter": f"author.id:{short_id}",
                "per-page": 200,
                "cursor": cursor,
                "select": "doi",
            },
            headers=headers,
            delay=config.OPENALEX_DELAY,
        )
        if not d:
            break
        for w in d.get("results", []):
            norm = _normalize_doi(w.get("doi"))
            if norm:
                dois.append(norm)
        cursor = (d.get("meta") or {}).get("next_cursor")
    return dois


def _disambiguation_suspect(rmd_dois: set[str], oa_dois: set[str]) -> bool:
    """Cheap overlap-based check for OpenAlex author conflation.

    Returns True if it looks like the OA author record is over-inclusive
    (different person's works conflated under the ORCID).
    """
    if not rmd_dois or not oa_dois:
        return False
    overlap = len(rmd_dois & oa_dois) / len(rmd_dois)
    expansion = len(oa_dois) / max(len(rmd_dois), 1)
    return overlap < SUSPECT_OVERLAP_FRAC and expansion > SUSPECT_EXPANSION


def _parse_author(author: dict) -> dict:
    """Parse an OpenAlex author record into our schema (aggregate metrics)."""
    orcid_raw = author.get("orcid") or ""
    orcid = orcid_raw.replace("https://orcid.org/", "") or None
    openalex_id = (author.get("id") or "").replace("https://openalex.org/", "")
    summary = author.get("summary_stats") or {}

    current_year = datetime.now().year
    affiliations = []
    for aff in author.get("affiliations", []):
        inst = aff.get("institution", {})
        years = sorted(aff.get("years", []))
        affiliations.append({
            "institution": inst.get("display_name", "Unknown"),
            "ror": inst.get("ror"),
            "years": years,
            "is_current": current_year in years if years else False,
        })

    topics = []
    for t in (author.get("topics") or [])[:5]:
        topics.append({
            "topic": t.get("display_name"),
            "subfield": (t.get("subfield") or {}).get("display_name"),
            "field": (t.get("field") or {}).get("display_name"),
            "domain": (t.get("domain") or {}).get("display_name"),
        })

    return {
        "openalex_id": openalex_id,
        "orcid": orcid,
        "display_name": author.get("display_name"),
        "works_count": author.get("works_count", 0),
        "cited_by_count": author.get("cited_by_count", 0),
        "h_index": summary.get("h_index", 0),
        "i10_index": summary.get("i10_index", 0),
        "two_yr_mean_citedness": summary.get("2yr_mean_citedness", 0.0),
        "affiliations": affiliations,
        "topics": topics,
        "last_fetched": now_iso(),
    }


def run(max_researchers: int | None = None,
        incremental: bool = False) -> dict:
    """Enrich researchers with OpenAlex data + works DOIs.

    Args:
        max_researchers: Limit number of researchers (for testing).
        incremental: Skip researchers already enriched within INCREMENTAL_SKIP_DAYS.

    Returns:
        Stats dict with counts.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    review_dir = config.DATA_DIR / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}

    try:
        db_researchers = get_all_researchers()
    except Exception as e:
        logger.error("Failed to load researchers from database: %s", e)
        return {"error": str(e)}

    if max_researchers:
        db_researchers = db_researchers[:max_researchers]

    print(f"OpenAlex: enriching {len(db_researchers)} researchers")

    counts = {"fetched": 0, "skipped": 0, "not_found": 0,
              "name_search_accepted": 0, "name_search_reviewed": 0,
              "disambiguation_suspects": 0}
    name_review_rows: list[dict] = []
    suspect_rows: list[dict] = []

    for row in tqdm(db_researchers, desc="OpenAlex enrichment"):
        orcid = row["orcid"]
        data = row["data"]

        # Incremental: skip if recently enriched
        if incremental and data.get("openalex"):
            oa_fetched = data["openalex"].get("last_fetched")
            if oa_fetched and days_since(oa_fetched) < config.INCREMENTAL_SKIP_DAYS:
                counts["skipped"] += 1
                continue

        # Resolve author record. Synthetic 'wa:<uid>' identifiers (no ORCID known)
        # take the name-search path; everything else is a direct ORCID lookup.
        is_synthetic = orcid.startswith("wa:")
        lookup_method = "orcid"
        author_data = None

        if not is_synthetic:
            author_data = _lookup_by_orcid(orcid, headers)
        else:
            rmd_name = (data.get("rmd") or {}).get("name") or data.get("display_name", "")
            author_data, decision = _lookup_by_name(rmd_name, headers)
            lookup_method = "name_search"
            if decision == "review":
                # Borderline candidates — log for human review, do NOT enrich.
                if author_data and author_data.get("_review_candidates"):
                    name_review_rows.extend(author_data["_review_candidates"])
                counts["name_search_reviewed"] += 1
                continue
            if decision == "reject" or not author_data:
                counts["not_found"] += 1
                continue
            counts["name_search_accepted"] += 1

        if not author_data:
            counts["not_found"] += 1
            continue

        try:
            upload_raw_response("openalex", orcid, author_data)
        except Exception as e:
            logger.warning("Failed to archive to S3: %s", e)

        parsed = _parse_author(author_data)
        author_id = author_data.get("id") or ""

        # Pull full works list + run disambiguation guard
        oa_dois = _pull_works_dois(author_id, headers)
        rmd_dois = set((data.get("rmd") or {}).get("dois") or [])
        suspect = _disambiguation_suspect(rmd_dois, set(oa_dois))

        flags = data.get("flags") or {}
        flags["lookup_method"] = lookup_method
        flags["oa_disambiguation_suspect"] = suspect

        if suspect:
            counts["disambiguation_suspects"] += 1
            suspect_rows.append({
                "orcid": orcid,
                "display_name": parsed.get("display_name"),
                "rmd_doi_count": len(rmd_dois),
                "oa_doi_count": len(oa_dois),
                "overlap": len(rmd_dois & set(oa_dois)),
                "openalex_id": parsed.get("openalex_id"),
            })
            parsed["works_dois"] = []  # drop OA DOIs; only RMD's will be used downstream
        else:
            parsed["works_dois"] = sorted(set(oa_dois))

        # Merge into existing record (preserve RMD data + flags)
        data["openalex_id"] = parsed["openalex_id"]
        data["display_name"] = parsed["display_name"] or data.get("display_name")
        data["openalex"] = parsed
        data["flags"] = flags
        # If we found an ORCID via name-search, surface it on the record too
        if is_synthetic and parsed.get("orcid"):
            data["discovered_orcid"] = parsed["orcid"]

        try:
            upsert_researcher(data)
            counts["fetched"] += 1
        except Exception as e:
            logger.warning("Failed to upsert researcher %s: %s", orcid, e)

    if name_review_rows:
        save_json({"candidates": name_review_rows}, review_dir / "name_match_review.json")
        print(f"  → {len(name_review_rows)} name-match review candidates → review/name_match_review.json")
    if suspect_rows:
        save_json({"suspects": suspect_rows}, review_dir / "oa_disambiguation_suspects.json")
        print(f"  → {len(suspect_rows)} disambiguation suspects → review/oa_disambiguation_suspects.json")

    print(f"OpenAlex: enriched={counts['fetched']}  not_found={counts['not_found']}  "
          f"skipped={counts['skipped']}  name_accepted={counts['name_search_accepted']}  "
          f"name_review={counts['name_search_reviewed']}  suspects={counts['disambiguation_suspects']}")
    return {"total_researchers": len(db_researchers), **counts}
