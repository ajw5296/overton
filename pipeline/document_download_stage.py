"""Stage 5: Download full-text policy document PDFs to S3.

Queries the policy_documents table for documents with a pdf_url that haven't
been downloaded yet, streams the PDF, and uploads to S3.
"""

import logging
import time

import requests
from tqdm import tqdm

from . import config
from .db.operations import (
    get_policy_documents_needing_pdf_download,
    update_pdf_download_status,
)
from .db.s3_client import upload_pdf, pdf_exists

logger = logging.getLogger("pipeline.document_download")


def _download_pdf(url: str, timeout: int = None) -> tuple[bytes | None, str]:
    """Download a PDF from a URL, returning (content_bytes, status).

    Returns:
        (pdf_bytes, status) where status is 'downloaded', 'skipped_too_large',
        or 'failed'.
    """
    timeout = timeout or config.PDF_DOWNLOAD_TIMEOUT
    max_size = config.MAX_PDF_SIZE_MB * 1024 * 1024

    try:
        # Stream the response to check size before loading fully
        with requests.get(url, timeout=timeout, stream=True) as resp:
            resp.raise_for_status()

            # Check Content-Length header if available
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_size:
                logger.info("Skipping %s — too large (%s bytes)", url, content_length)
                return None, "skipped_too_large"

            # Read in chunks, enforcing size limit
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                total += len(chunk)
                if total > max_size:
                    logger.info("Skipping %s — exceeded %dMB during download", url, config.MAX_PDF_SIZE_MB)
                    return None, "skipped_too_large"
                chunks.append(chunk)

            return b"".join(chunks), "downloaded"

    except requests.exceptions.RequestException as e:
        logger.warning("Failed to download %s: %s", url, e)
        return None, "failed"
    except (UnicodeDecodeError, UnicodeError) as e:
        # Servers occasionally return non-UTF-8 bytes in redirect Location
        # headers; requests.sessions.get_redirect_target raises on those.
        # Treat as a failed download so the stage can continue.
        logger.warning("Failed to download %s: encoding error in response: %s", url, e)
        return None, "failed"


def run(max_downloads: int | None = None) -> dict:
    """Download PDFs for policy documents that need them.

    Args:
        max_downloads: Limit number of downloads (for testing).

    Returns:
        Stats dict with counts.
    """
    try:
        docs = get_policy_documents_needing_pdf_download()
    except Exception as e:
        logger.error("Failed to query documents needing download: %s", e)
        return {"error": str(e)}

    if max_downloads:
        docs = docs[:max_downloads]

    print(f"Document Download: {len(docs)} PDFs to download")

    if not docs:
        return {"total_eligible": 0, "downloaded": 0}

    downloaded = 0
    skipped_large = 0
    failed = 0
    skipped_exists = 0

    for doc in tqdm(docs, desc="Downloading PDFs"):
        doc_id = doc["policy_document_id"]
        pdf_url = doc["pdf_url"]

        # Check if already in S3 (belt and suspenders)
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

        # Rate limit between downloads
        time.sleep(config.PDF_DOWNLOAD_DELAY)

    stats = {
        "total_eligible": len(docs),
        "downloaded": downloaded,
        "skipped_too_large": skipped_large,
        "skipped_already_exists": skipped_exists,
        "failed": failed,
    }

    print(f"Document Download: {downloaded} downloaded, {skipped_large} too large, "
          f"{skipped_exists} already existed, {failed} failed")
    return stats
