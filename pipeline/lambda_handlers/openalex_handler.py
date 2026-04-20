"""Lambda handler for Stage 2: OpenAlex enrichment.

Loads researchers from RDS (populated by RMD stage) and enriches each
with OpenAlex academic metadata (works, citations, h-index, topics).

Event schema:
{
    "max_researchers": 50,   // optional, limit for testing
    "incremental": true      // optional, skip recently enriched
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline import openalex_stage

logger = logging.getLogger("pipeline.lambda.openalex")
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point for OpenAlex enrichment stage."""
    ensure_tables()

    stats = openalex_stage.run(
        max_researchers=event.get("max_researchers"),
        incremental=event.get("incremental", False),
    )

    return {
        "status": "completed",
        "stage": "openalex",
        "stats": stats,
    }
