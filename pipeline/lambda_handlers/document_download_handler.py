"""Lambda handler for Stage 5: Document PDF download to S3.

Can run in two modes:
1. Full mode (invoked by Step Functions directly): downloads all pending PDFs.
2. Chunk mode (invoked by Step Functions Map): downloads a subset of PDFs
   by policy_document_id list, enabling fan-out parallelism.

Event schema (full mode):
{
    "max_downloads": 100   // optional, limit for testing
}

Event schema (chunk mode):
{
    "documents": [
        {"policy_document_id": "doc-1", "pdf_url": "https://..."},
        {"policy_document_id": "doc-2", "pdf_url": "https://..."}
    ]
}
"""

import logging

from pipeline.db.schema import ensure_tables
from pipeline.db.operations import update_pdf_download_status
from pipeline.db.s3_client import upload_pdf, pdf_exists
from pipeline.document_download_stage import _download_pdf

logger = logging.getLogger("pipeline.lambda.document_download")
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point for document PDF download stage."""
    ensure_tables()

    documents = event.get("documents")
    download_s3_key = event.get("download_s3_key")

    if documents:
        return _process_documents(documents)
    elif download_s3_key:
        from pipeline.db.s3_client import load_json_from_s3
        all_docs = load_json_from_s3(download_s3_key)
        offset = event.get("offset", 0)
        limit = event.get("limit", 100)
        chunk = all_docs[offset:offset + limit]
        return _process_documents(chunk)
    else:
        # Full mode: query DB for pending downloads
        from pipeline import document_download_stage
        stats = document_download_stage.run(
            max_downloads=event.get("max_downloads"),
        )
        return {"status": "completed", "stage": "download", "stats": stats}


def _process_documents(documents: list[dict]) -> dict:
    """Process a chunk of documents — used in fan-out mode."""
    downloaded = 0
    skipped_large = 0
    skipped_exists = 0
    failed = 0

    for doc in documents:
        doc_id = doc["policy_document_id"]
        pdf_url = doc["pdf_url"]

        # Check if already in S3
        try:
            if pdf_exists(doc_id):
                update_pdf_download_status(doc_id, f"policy-documents/{doc_id}.pdf", "downloaded")
                skipped_exists += 1
                continue
        except Exception:
            pass

        pdf_bytes, status = _download_pdf(pdf_url)

        if status == "downloaded" and pdf_bytes:
            try:
                s3_key = upload_pdf(doc_id, pdf_bytes)
                update_pdf_download_status(doc_id, s3_key, "downloaded")
                downloaded += 1
            except Exception as e:
                logger.warning("Failed to upload PDF %s to S3: %s", doc_id, e)
                update_pdf_download_status(doc_id, None, "failed")
                failed += 1
        elif status == "skipped_too_large":
            update_pdf_download_status(doc_id, None, "skipped_too_large")
            skipped_large += 1
        else:
            update_pdf_download_status(doc_id, None, "failed")
            failed += 1

    return {
        "status": "completed",
        "stage": "download-chunk",
        "stats": {
            "total": len(documents),
            "downloaded": downloaded,
            "skipped_too_large": skipped_large,
            "skipped_already_exists": skipped_exists,
            "failed": failed,
        },
    }
