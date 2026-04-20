"""Stage 2: Enrich researchers with OpenAlex academic metadata.

Loads researchers from the database (populated by RMD stage), fetches
each one's OpenAlex profile by ORCID, and updates the researcher record
with works count, citations, h-index, topics, and affiliations.
"""

import logging
from datetime import datetime
from tqdm import tqdm

from . import config
from .utils import api_request, save_json, now_iso, days_since
from .db.operations import get_all_researchers, upsert_researcher
from .db.s3_client import upload_raw_response

logger = logging.getLogger("pipeline.openalex")


def _parse_author(author: dict) -> dict | None:
    """Parse an OpenAlex author record into our schema."""
    orcid_raw = author.get("orcid")
    if not orcid_raw:
        return None

    orcid = orcid_raw.replace("https://orcid.org/", "")
    openalex_id = (author.get("id") or "").replace("https://openalex.org/", "")

    summary = author.get("summary_stats") or {}

    # Parse affiliations
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

    # Parse top 5 topics
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
    """Enrich researchers with OpenAlex data by ORCID lookup.

    Args:
        max_researchers: Limit number of researchers (for testing).
        incremental: Skip researchers already enriched within INCREMENTAL_SKIP_DAYS.

    Returns:
        Stats dict with counts.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}

    # Load researchers from database (inserted by RMD stage)
    try:
        db_researchers = get_all_researchers()
    except Exception as e:
        logger.error("Failed to load researchers from database: %s", e)
        return {"error": str(e)}

    if max_researchers:
        db_researchers = db_researchers[:max_researchers]

    print(f"OpenAlex: Enriching {len(db_researchers)} researchers")

    fetched = 0
    skipped = 0
    not_found = 0

    for row in tqdm(db_researchers, desc="OpenAlex enrichment"):
        orcid = row["orcid"]
        data = row["data"]

        # Incremental: skip if recently fetched
        if incremental and data.get("openalex"):
            oa_fetched = data["openalex"].get("last_fetched")
            if oa_fetched and days_since(oa_fetched) < config.INCREMENTAL_SKIP_DAYS:
                skipped += 1
                continue

        # Fetch single author by ORCID
        author_data = api_request(
            f"{config.OPENALEX_BASE_URL}/authors/orcid:{orcid}",
            headers=headers,
            delay=config.OPENALEX_DELAY,
        )

        if not author_data:
            not_found += 1
            continue

        # Archive raw response
        try:
            upload_raw_response("openalex", orcid, author_data)
        except Exception as e:
            logger.warning("Failed to archive to S3: %s", e)

        parsed = _parse_author(author_data)
        if not parsed:
            not_found += 1
            continue

        # Merge into existing record (preserve RMD data)
        data["openalex_id"] = parsed["openalex_id"]
        data["display_name"] = parsed["display_name"] or data.get("display_name")
        data["openalex"] = parsed

        try:
            upsert_researcher(data)
            fetched += 1
        except Exception as e:
            logger.warning("Failed to upsert researcher %s: %s", orcid, e)

    stats = {
        "total_researchers": len(db_researchers),
        "fetched": fetched,
        "skipped": skipped,
        "not_found": not_found,
    }
    print(f"OpenAlex: Enriched {fetched}, skipped {skipped}, not found {not_found}")
    return stats
