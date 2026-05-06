"""Lambda handler that partitions work into chunks for Step Functions Map states.

Called before each fan-out stage to split the work into evenly-sized chunks
that can be processed in parallel by Map state workers.

Event schema:
{
    "stage": "overton-articles" | "overton-documents" | "download",
    "chunk_size": 100   // optional, defaults vary by stage
}

Returns:
{
    "chunks": [
        {"orcids": [...]},           // for overton-articles
        {"document_ids": [...]},     // for overton-documents
        {"documents": [...]},        // for download
    ]
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline.db.operations import (
    get_all_researchers,
    get_unique_cited_policy_doc_ids,
    get_existing_policy_doc_ids,
    get_policy_documents_needing_pdf_download,
)
from pipeline.db.connection import get_engine
from pipeline.db.schema import policy_documents as policy_documents_table
from sqlalchemy import select

logger = logging.getLogger("pipeline.lambda.chunker")
logger.setLevel(logging.INFO)

DEFAULT_CHUNK_SIZES = {
    "rmd": 50,
    "overton-articles": 50,
    "overton-documents": 200,
    "download": 100,
}


def _split(items: list, chunk_size: int) -> list[list]:
    """Split a list into chunks of the given size."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def handler(event, context):
    """Lambda entry point for chunking work."""
    ensure_tables()

    stage = event["stage"]
    chunk_size = event.get("chunk_size", DEFAULT_CHUNK_SIZES.get(stage, 100))

    if stage == "rmd":
        from pipeline.rmd_stage import _load_orcid_map
        orcid_map = _load_orcid_map()
        items = [{"orcid": orcid, "webaccess_id": uid} for orcid, uid in orcid_map.items()]
        chunks = [{"researchers": chunk} for chunk in _split(items, chunk_size)]

    elif stage == "overton-articles":
        researchers = get_all_researchers()
        orcids = [r["orcid"] for r in researchers]
        chunks = [{"orcids": chunk} for chunk in _split(orcids, chunk_size)]

    elif stage == "overton-documents":
        cited_ids = get_unique_cited_policy_doc_ids()
        existing_ids = get_existing_policy_doc_ids()

        # Find placeholders (minimal records from Stage 3)
        placeholder_ids = set()
        try:
            stmt = select(
                policy_documents_table.c.policy_document_id,
                policy_documents_table.c.data,
            ).where(
                policy_documents_table.c.policy_document_id.in_(list(cited_ids))
            )
            with get_engine().connect() as conn:
                rows = conn.execute(stmt).fetchall()
            for row in rows:
                data = row.data or {}
                if len(data) <= 2 and "title" not in data:
                    placeholder_ids.add(row.policy_document_id)
        except Exception as e:
            logger.warning("Failed to check placeholders: %s", e)

        missing_ids = sorted((cited_ids - existing_ids) | placeholder_ids)

        # Save full ID list to S3 to avoid Step Functions payload limits,
        # then pass chunk offsets to workers
        from pipeline.db.s3_client import save_json_to_s3
        s3_key = "pipeline-cache/chunks/overton-documents-ids.json"
        save_json_to_s3(s3_key, missing_ids)

        total = len(missing_ids)
        chunks = [{"s3_key": s3_key, "offset": i, "limit": chunk_size}
                  for i in range(0, total, chunk_size)]

    elif stage == "download":
        docs = get_policy_documents_needing_pdf_download()
        doc_list = [{"policy_document_id": d["policy_document_id"], "pdf_url": d["pdf_url"]} for d in docs]

        # Save to S3 if payload would be too large
        import json
        if len(json.dumps(doc_list)) > 150_000:
            from pipeline.db.s3_client import save_json_to_s3
            s3_key = "pipeline-cache/chunks/download-docs.json"
            save_json_to_s3(s3_key, doc_list)
            chunks = [{"download_s3_key": s3_key, "offset": i, "limit": chunk_size}
                      for i in range(0, len(doc_list), chunk_size)]
        else:
            chunks = [{"documents": chunk} for chunk in _split(doc_list, chunk_size)]

    else:
        return {"error": f"Unknown stage: {stage}"}

    total_items = sum(
        len(c.get("orcids", c.get("document_ids", c.get("documents", c.get("researchers", [])))))
        for c in chunks
    )
    logger.info("Stage %s: %d items split into %d chunks of %d",
                stage, total_items, len(chunks), chunk_size)

    return {
        "stage": stage,
        "total_items": total_items,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
