"""Stage 1: Fetch PSU researchers from OpenAlex API.

Produces the baseline researcher records with OpenAlex metadata.
"""

import logging
import time
from datetime import datetime
from tqdm import tqdm

from . import config
from .utils import api_request, load_json, save_json, now_iso, days_since

logger = logging.getLogger("pipeline.openalex")


def _parse_author(author: dict) -> dict | None:
    """Parse an OpenAlex author record into our schema."""
    orcid_raw = author.get("orcid")
    if not orcid_raw:
        return None

    orcid = orcid_raw.replace("https://orcid.org/", "")
    openalex_id = (author.get("id") or "").replace("https://openalex.org/", "")

    summary = author.get("summary_stats") or {}

    # Parse affiliations - find PSU and others
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
        "orcid": orcid,
        "openalex_id": openalex_id,
        "display_name": author.get("display_name"),
        "openalex": {
            "works_count": author.get("works_count", 0),
            "cited_by_count": author.get("cited_by_count", 0),
            "h_index": summary.get("h_index", 0),
            "i10_index": summary.get("i10_index", 0),
            "two_yr_mean_citedness": summary.get("2yr_mean_citedness", 0.0),
            "affiliations": affiliations,
            "topics": topics,
            "last_fetched": now_iso(),
        },
        "rmd": None,
        "overton": None,
    }


def run(max_researchers: int | None = None, current_only: bool = False,
        incremental: bool = False) -> list[dict]:
    """Fetch all PSU-affiliated researchers with ORCIDs from OpenAlex.

    Args:
        max_researchers: Limit number of researchers (for testing).
        current_only: Only fetch researchers currently at PSU.
        incremental: Skip researchers already fetched within INCREMENTAL_SKIP_DAYS.

    Returns:
        List of researcher dicts in the unified schema.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.DATA_DIR / config.OPENALEX_OUTPUT

    # Load existing data for incremental mode
    existing = {}
    if incremental:
        prev = load_json(output_path, [])
        existing = {r["orcid"]: r for r in prev}
        logger.info(f"Incremental mode: {len(existing)} existing records loaded")

    # Build filter
    if current_only:
        filter_param = f"last_known_institutions.ror:{config.PSU_ROR},has_orcid:true"
    else:
        filter_param = f"affiliations.institution.ror:{config.PSU_ROR},has_orcid:true"

    select_fields = "id,orcid,display_name,works_count,cited_by_count,summary_stats,affiliations,topics"

    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}

    # Get total count
    count_resp = api_request(
        f"{config.OPENALEX_BASE_URL}/authors",
        params={"filter": filter_param, "per_page": 1},
        headers=headers,
    )
    total_count = (count_resp or {}).get("meta", {}).get("count", 0)
    to_fetch = min(max_researchers, total_count) if max_researchers else total_count
    print(f"OpenAlex: Found {total_count:,} researchers, fetching {to_fetch:,}")

    researchers = []
    cursor = "*"
    pbar = tqdm(total=to_fetch, desc="OpenAlex researchers")

    while len(researchers) < to_fetch:
        data = api_request(
            f"{config.OPENALEX_BASE_URL}/authors",
            params={
                "filter": filter_param,
                "per_page": 200,
                "cursor": cursor,
                "select": select_fields,
            },
            headers=headers,
            delay=config.OPENALEX_DELAY,
        )
        if not data:
            logger.error("Failed to fetch page from OpenAlex, stopping.")
            break

        results = data.get("results", [])
        if not results:
            break

        for author in results:
            parsed = _parse_author(author)
            if not parsed:
                continue

            # Incremental: reuse existing record if recently fetched
            if incremental and parsed["orcid"] in existing:
                prev_record = existing[parsed["orcid"]]
                oa_fetched = (prev_record.get("openalex") or {}).get("last_fetched")
                if oa_fetched and days_since(oa_fetched) < config.INCREMENTAL_SKIP_DAYS:
                    researchers.append(prev_record)
                    pbar.update(1)
                    if max_researchers and len(researchers) >= max_researchers:
                        break
                    continue

            researchers.append(parsed)
            pbar.update(1)
            if max_researchers and len(researchers) >= max_researchers:
                break

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

    pbar.close()
    print(f"OpenAlex: Fetched {len(researchers):,} researchers")

    save_json(researchers, output_path)
    return researchers
