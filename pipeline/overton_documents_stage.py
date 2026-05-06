"""Stage 4: Fetch full policy document metadata from the Overton Documents API.

Reads unique policy_document_ids from the article_citations table (populated
by Stage 3), fetches full metadata from documents.php for any not yet in the
policy_documents table, and normalizes data on ingest.
"""

import logging

from sqlalchemy import select
from tqdm import tqdm

from . import config
from .utils import api_request, now_iso, normalize_date, cast_bool
from .db.connection import get_engine
from .db.schema import policy_documents as policy_documents_table
from .db.operations import (
    get_unique_cited_policy_doc_ids,
    get_existing_policy_doc_ids,
    upsert_policy_document,
    update_pdf_download_status,
)
from .db.s3_client import upload_raw_response, list_existing_pdf_ids

logger = logging.getLogger("pipeline.overton_documents")


def _parse_document(raw: dict) -> dict:
    """Parse a raw Overton document result into our schema."""
    source = raw.get("source", {})

    # Extract DOIs from cites.scholarly
    cites = raw.get("cites", {})
    scholarly_cites = cites.get("scholarly", [])
    cites_dois = [c.get("doi") for c in scholarly_cites if c.get("doi")]

    return {
        "policy_document_id": raw.get("policy_document_id", ""),
        "pdf_document_id": raw.get("pdf_document_id"),
        "title": raw.get("title"),
        "translated_title": raw.get("translated_title"),
        "source": {
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "country": source.get("country"),
            "state": source.get("state"),
            "type": source.get("type"),
            "subtype": source.get("subtype"),
            "sector": source.get("sector"),
            "organisation_type": source.get("organisation_type"),
            "function": source.get("function", []),
            "region": source.get("region", []),
        },
        "published_on": normalize_date(raw.get("published_on")),
        "added_on": normalize_date(raw.get("added_on")),
        "document_url": raw.get("document_url"),
        "pdf_url": raw.get("pdf_url"),
        "thumbnail": raw.get("thumbnail"),
        "topics": raw.get("topics", []),
        "classifications": raw.get("classifications", []),
        "sdgcategories": raw.get("sdgcategories", []),
        "cofog_divisions": raw.get("cofog_divisions", []),
        "llm_document_theme": raw.get("llm_document_theme"),
        "llm_document_description": raw.get("llm_document_description"),
        "citation_count": raw.get("citation_count", 0),
        "authors": raw.get("authors", []),
        "languages": raw.get("languages", []),
        "dont_show_pdf": cast_bool(raw.get("dont_show_pdf", False)),
        "cites_scholarly_dois": cites_dois,
        "overton_url": raw.get("overton_url"),
        "overton_url_with_context": raw.get("overton_url_with_context"),
        "last_fetched": now_iso(),
    }


def _fetch_document(policy_document_id: str) -> dict | None:
    """Fetch a single policy document by ID from Overton."""
    params = {
        "api_key": config.OVERTON_API_KEY,
        "format": "json",
        "query": policy_document_id,
    }

    data = api_request(
        config.OVERTON_DOCUMENTS_URL,
        params=params,
        delay=config.OVERTON_DELAY,
        timeout=30,
    )
    if not data:
        return None

    total = data.get("query", {}).get("total_results", 0)
    if total == 0:
        return None

    # Archive raw response
    try:
        upload_raw_response("overton-documents", policy_document_id, data)
    except Exception as e:
        logger.warning("Failed to archive to S3: %s", e)

    results = data.get("results", [])
    if not results:
        return None

    # Find the matching document (there may be multiple results)
    for doc in results:
        if doc.get("policy_document_id") == policy_document_id:
            return _parse_document(doc)

    # If no exact match, use the first result
    return _parse_document(results[0])


def run(incremental: bool = False) -> dict:
    """Fetch full metadata for policy documents referenced in article_citations.

    Args:
        incremental: Only fetch documents not already in the policy_documents table.
                     (This is the default behavior — we always skip existing docs.)

    Returns:
        Stats dict with counts.
    """
    # Get all policy_document_ids referenced by citations
    try:
        cited_ids = get_unique_cited_policy_doc_ids()
    except Exception as e:
        logger.error("Failed to query article_citations: %s", e)
        return {"error": str(e)}

    # Get policy docs we already have full data for
    try:
        existing_ids = get_existing_policy_doc_ids()
    except Exception as e:
        logger.error("Failed to query policy_documents: %s", e)
        existing_ids = set()

    # Filter to documents needing fetch — those that are either missing entirely
    # or are only placeholders (inserted by Stage 3 with minimal data)
    # A placeholder has a data field with only policy_document_id
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
            # A placeholder only has policy_document_id and maybe 'data' wrapper
            if len(data) <= 2 and "title" not in data:
                placeholder_ids.add(row.policy_document_id)
    except Exception as e:
        logger.warning("Failed to check for placeholders: %s", e)

    # IDs to fetch: not in existing OR are placeholders
    missing_ids = (cited_ids - existing_ids) | placeholder_ids
    print(f"Overton Documents: {len(cited_ids)} referenced, "
          f"{len(existing_ids)} existing ({len(placeholder_ids)} placeholders), "
          f"{len(missing_ids)} to fetch")

    if not missing_ids:
        print("Overton Documents: Nothing to fetch")
        return {"referenced": len(cited_ids), "fetched": 0, "already_existed": len(existing_ids)}

    # Snapshot existing PDFs in S3 once (single ListObjectsV2 walk) so we can
    # mark docs as 'downloaded' on insert and let Stage 5 skip them naturally.
    try:
        existing_pdfs = list_existing_pdf_ids()
        print(f"Overton Documents: {len(existing_pdfs)} PDFs already in S3 — will mark downloaded")
    except Exception as e:
        logger.warning("Could not list existing PDFs: %s", e)
        existing_pdfs = set()

    fetched = 0
    failed = 0
    pdfs_skipped = 0

    for doc_id in tqdm(sorted(missing_ids), desc="Overton Documents"):
        doc = _fetch_document(doc_id)
        if doc:
            try:
                upsert_policy_document(doc)
                fetched += 1
                # If the PDF for this doc is already in S3, mark it downloaded
                # so Stage 5 doesn't re-fetch it.
                if doc_id in existing_pdfs:
                    pdf_prefix = "policy-documents"  # matches S3_PDF_PREFIX default
                    update_pdf_download_status(
                        doc_id,
                        s3_pdf_key=f"{pdf_prefix}/{doc_id}.pdf",
                        status="downloaded",
                    )
                    pdfs_skipped += 1
            except Exception as e:
                logger.warning("Failed to upsert policy document %s: %s", doc_id, e)
                failed += 1
        else:
            failed += 1

    stats = {
        "referenced": len(cited_ids),
        "already_existed": len(existing_ids) - len(placeholder_ids),
        "fetched": fetched,
        "failed": failed,
        "pdfs_preserved": pdfs_skipped,
    }

    print(f"Overton Documents: Fetched {fetched}, failed {failed}, "
          f"{pdfs_skipped} PDFs preserved from prior run")
    return stats
