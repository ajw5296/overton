"""Lambda handler for Stage 1: RMD researcher cohort.

Can run in two modes:
1. Full mode: loads ORCID map, fetches all RMD profiles.
2. Chunk mode (invoked by Step Functions Map): processes a subset of
   ORCID→WebAccess pairs, enabling fan-out parallelism.

Event schema (full mode):
{
    "max_researchers": 50,
    "incremental": true
}

Event schema (chunk mode):
{
    "researchers": [
        {"orcid": "0000-0001-1234-5678", "webaccess_id": "abc123"},
        ...
    ]
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline.db.operations import upsert_researcher, get_all_researchers
from pipeline.rmd_stage import _fetch_rmd_data, _load_orcid_map
from pipeline.utils import days_since, now_iso
from pipeline import config

logger = logging.getLogger("pipeline.lambda.rmd")
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point for RMD cohort stage."""
    ensure_tables()

    researchers = event.get("researchers")

    if researchers:
        return _process_chunk(researchers, event.get("incremental", False))
    else:
        from pipeline import rmd_stage
        stats = rmd_stage.run(
            max_researchers=event.get("max_researchers"),
            incremental=event.get("incremental", False),
        )
        return {"status": "completed", "stage": "rmd", "stats": stats}


def _process_chunk(researchers: list[dict], incremental: bool = False) -> dict:
    """Process a chunk of ORCID→WebAccess pairs."""
    # Load existing for incremental check
    existing = {}
    if incremental:
        try:
            for r in get_all_researchers():
                existing[r["orcid"]] = r["data"]
        except Exception:
            pass

    fetched = 0
    skipped = 0

    for item in researchers:
        orcid = item["orcid"]
        webaccess_id = item["webaccess_id"]

        if incremental and orcid in existing:
            rmd_data = existing[orcid].get("rmd") or {}
            last_fetched = rmd_data.get("last_fetched")
            if last_fetched and days_since(last_fetched) < config.INCREMENTAL_SKIP_DAYS:
                skipped += 1
                continue

        rmd_data = _fetch_rmd_data(webaccess_id)
        display_name = (rmd_data.get("profile") or {}).get("title") or webaccess_id

        researcher = {
            "orcid": orcid,
            "openalex_id": None,
            "display_name": display_name,
            "openalex": None,
            "rmd": rmd_data,
            "overton": None,
        }

        try:
            upsert_researcher(researcher)
            fetched += 1
        except Exception as e:
            logger.warning("Failed to upsert researcher %s: %s", orcid, e)

    return {
        "status": "completed",
        "stage": "rmd-chunk",
        "stats": {"fetched": fetched, "skipped": skipped, "total": len(researchers)},
    }
