"""Lambda handler for Stage 3: Overton Articles fetch.

Can run in two modes:
1. Full mode (invoked by Step Functions directly): processes all researchers.
2. Chunk mode (invoked by Step Functions Map): processes a subset of researchers
   by ORCID list, enabling fan-out parallelism.

Event schema (full mode):
{
    "incremental": true,
    "skip_no_hits": false
}

Event schema (chunk mode):
{
    "orcids": ["0000-0001-1234-5678", "0000-0002-9876-5432", ...],
    "skip_no_hits": false
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline.db.operations import (
    get_all_researchers,
    get_researchers_needing_update,
    upsert_article,
    upsert_article_citation,
    upsert_policy_document,
)
from pipeline.utils import now_iso
from pipeline.overton_articles_stage import (
    _fetch_articles_for_orcid,
)
from pipeline import config

logger = logging.getLogger("pipeline.lambda.overton_articles")
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point for Overton Articles stage."""
    ensure_tables()

    orcids = event.get("orcids")

    if orcids:
        # Chunk mode: process only the given ORCIDs
        return _process_orcids(orcids)
    else:
        # Full mode: load from DB and process all
        from pipeline import overton_articles_stage
        stats = overton_articles_stage.run(
            incremental=event.get("incremental", False),
            skip_no_hits=event.get("skip_no_hits", False),
        )
        return {"status": "completed", "stage": "overton-articles", "stats": stats}


def _process_orcids(orcids: list[str]) -> dict:
    """Process a chunk of ORCIDs — used in fan-out mode."""
    total_articles = 0
    total_citations = 0
    researchers_with_hits = 0

    for orcid in orcids:
        articles, citations, result_count = _fetch_articles_for_orcid(orcid)

        if result_count == 0:
            continue

        researchers_with_hits += 1

        for article in articles:
            try:
                upsert_article(article)
                total_articles += 1
            except Exception as e:
                logger.warning("Failed to upsert article %s: %s", article.get("doi"), e)

        for cite in citations:
            try:
                upsert_policy_document({
                    "policy_document_id": cite["policy_document_id"],
                    "data": {"policy_document_id": cite["policy_document_id"]},
                })
                upsert_article_citation(
                    doi=cite["doi"],
                    policy_document_id=cite["policy_document_id"],
                    citation_metadata=cite["metadata"],
                )
                total_citations += 1
            except Exception as e:
                logger.warning("Failed to upsert citation %s -> %s: %s",
                               cite["doi"], cite["policy_document_id"], e)

    return {
        "status": "completed",
        "stage": "overton-articles-chunk",
        "stats": {
            "researchers_processed": len(orcids),
            "researchers_with_hits": researchers_with_hits,
            "articles_upserted": total_articles,
            "citations_upserted": total_citations,
        },
    }
