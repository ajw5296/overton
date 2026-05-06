"""Lambda handler for Stage 4: Overton Documents fetch.

Can run in two modes:
1. Full mode (invoked by Step Functions directly): fetches all missing documents.
2. Chunk mode (invoked by Step Functions Map): loads document IDs from S3
   at the given offset/limit, enabling fan-out parallelism.

Event schema (full mode):
{
    "incremental": true
}

Event schema (chunk mode — IDs passed directly):
{
    "document_ids": ["doc-id-1", "doc-id-2", ...]
}

Event schema (chunk mode — IDs in S3):
{
    "s3_key": "pipeline-cache/chunks/overton-documents-ids.json",
    "offset": 0,
    "limit": 50
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline.db.operations import upsert_policy_document
from pipeline.overton_documents_stage import _fetch_document

logger = logging.getLogger("pipeline.lambda.overton_documents")
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point for Overton Documents stage."""
    ensure_tables()

    document_ids = event.get("document_ids")
    s3_key = event.get("s3_key")

    if document_ids:
        return _process_document_ids(document_ids)
    elif s3_key:
        # Load IDs from S3 at the given offset
        from pipeline.db.s3_client import load_json_from_s3
        all_ids = load_json_from_s3(s3_key)
        offset = event.get("offset", 0)
        limit = event.get("limit", 50)
        chunk_ids = all_ids[offset:offset + limit]
        return _process_document_ids(chunk_ids)
    else:
        from pipeline import overton_documents_stage
        stats = overton_documents_stage.run(
            incremental=event.get("incremental", False),
        )
        return {"status": "completed", "stage": "overton-documents", "stats": stats}


def _process_document_ids(document_ids: list[str]) -> dict:
    """Process a chunk of document IDs — used in fan-out mode."""
    fetched = 0
    failed = 0

    for doc_id in document_ids:
        doc = _fetch_document(doc_id)
        if doc:
            try:
                upsert_policy_document(doc)
                fetched += 1
            except Exception as e:
                logger.warning("Failed to upsert document %s: %s", doc_id, e)
                failed += 1
        else:
            failed += 1

    return {
        "status": "completed",
        "stage": "overton-documents-chunk",
        "stats": {
            "total": len(document_ids),
            "fetched": fetched,
            "failed": failed,
        },
    }
