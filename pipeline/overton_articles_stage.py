"""Stage 3: Fetch scholarly articles from the Overton Articles API.

Queries articles.php by ORCID for each researcher. For each article found,
stores the article record and extracts cited_by_documents into the
article_citations junction table.
"""

import logging
from tqdm import tqdm

from . import config
from .utils import api_request, now_iso, days_since, normalize_date
from .db.operations import (
    get_all_researchers,
    get_researchers_needing_update,
    upsert_article,
    upsert_article_citation,
    upsert_policy_document,
)
from .db.s3_client import upload_raw_response

logger = logging.getLogger("pipeline.overton_articles")


def _parse_article(raw: dict) -> dict:
    """Parse a raw article result into our schema."""
    return {
        "doi": raw.get("doi", ""),
        "title": raw.get("title"),
        "document_url": raw.get("document_url"),
        "container": raw.get("container"),
        "journal": raw.get("journal"),
        "publisher": raw.get("publisher"),
        "type": raw.get("type"),
        "published_on": normalize_date(raw.get("published_on")),
        "authors": raw.get("authors", []),
        "orcids": raw.get("orcids", []),
        "language": raw.get("language"),
        "abstract": raw.get("abstract"),
        "oa_status": raw.get("oa_status"),
        "funders": raw.get("funders", []),
        "grant_ids": raw.get("grant_ids", []),
        "citations": raw.get("citations", 0),
        "with_journal_subject": raw.get("with_journal_subject", []),
        "last_cited": raw.get("last_cited"),
        "last_fetched": now_iso(),
    }


def _extract_citations(article_doi: str, raw: dict) -> list[dict]:
    """Extract cited_by_documents from a raw article into citation records."""
    citations = []
    for cite in raw.get("cited_by_documents", []):
        policy_doc_id = cite.get("policy_document_id")
        if not policy_doc_id:
            continue

        # Extract page numbers from child PDFs if available
        pages = []
        for pdf_info in (cite.get("cited_by_child_pdfs") or {}).values():
            pages.extend(pdf_info.get("on_pages", []))

        citation_meta = {
            "source_title": cite.get("source_title"),
            "document_title": cite.get("document_title"),
            "published_on": normalize_date(cite.get("published_on")),
            "type": cite.get("type"),
            "country": cite.get("country"),
            "topics": cite.get("topics", []),
            "classifications": cite.get("classifications", []),
            "cited_on_pages": sorted(set(pages)),
        }

        citations.append({
            "doi": article_doi,
            "policy_document_id": policy_doc_id,
            "metadata": citation_meta,
        })

    return citations


def _fetch_articles_for_orcid(orcid: str) -> tuple[list[dict], list[dict], int]:
    """Fetch all articles for an ORCID from Overton, handling pagination.

    Returns:
        (articles, citations, total_results)
    """
    all_articles = []
    all_citations = []
    total_results = 0
    page = 1

    while True:
        params = {
            "api_key": config.OVERTON_API_KEY,
            "format": "json",
            "query": orcid,
            "sort": "relevance",
            "page": str(page),
        }

        data = api_request(
            config.OVERTON_ARTICLES_URL,
            params=params,
            delay=config.OVERTON_DELAY,
            timeout=30,
        )
        if not data:
            break

        query_info = data.get("query", {})
        total_results = query_info.get("total_results", 0)

        if total_results == 0:
            break

        # Archive raw response to S3
        try:
            upload_raw_response(
                "overton-articles", f"{orcid}_page{page:03d}", data
            )
        except Exception as e:
            logger.warning("Failed to archive to S3: %s", e)

        # The articles endpoint nests results under results.results
        results_wrapper = data.get("results", {})
        if isinstance(results_wrapper, dict):
            results = results_wrapper.get("results", [])
        else:
            results = results_wrapper

        if not results:
            break

        for raw_article in results:
            doi = raw_article.get("doi")
            if not doi:
                continue

            article = _parse_article(raw_article)
            all_articles.append(article)

            citations = _extract_citations(doi, raw_article)
            all_citations.extend(citations)

        # Check for next page
        next_url = query_info.get("next_page_url")
        if not next_url:
            break
        page += 1

    return all_articles, all_citations, total_results


def run(incremental: bool = False, skip_no_hits: bool = False) -> dict:
    """Fetch articles from Overton Articles API for all researchers.

    Args:
        incremental: Skip researchers whose articles were recently fetched.
        skip_no_hits: Skip ORCIDs that previously had zero hits.

    Returns:
        Stats dict with counts.
    """
    # Load researchers from database
    try:
        if incremental:
            stale = get_researchers_needing_update(config.INCREMENTAL_SKIP_DAYS)
            all_db = get_all_researchers()
            stale_orcids = {r["orcid"] for r in stale}
            researchers = [r for r in all_db if r["orcid"] in stale_orcids]
            skipped_count = len(all_db) - len(researchers)
            print(f"Overton Articles: {len(researchers)} researchers need update, "
                  f"{skipped_count} skipped (incremental)")
        else:
            researchers = get_all_researchers()
            skipped_count = 0
    except Exception as e:
        logger.error("Failed to load researchers from database: %s", e)
        return {"error": str(e)}

    total_articles = 0
    total_citations = 0
    researchers_with_hits = 0
    no_hits = 0

    print(f"Overton Articles: Processing {len(researchers)} researchers...")

    for researcher in tqdm(researchers, desc="Overton Articles"):
        orcid = researcher["orcid"]

        articles, citations, result_count = _fetch_articles_for_orcid(orcid)

        if result_count == 0:
            no_hits += 1
            continue

        researchers_with_hits += 1

        # Upsert articles
        for article in articles:
            try:
                upsert_article(article)
                total_articles += 1
            except Exception as e:
                logger.warning("Failed to upsert article %s: %s", article.get("doi"), e)

        # Upsert citation links
        # Note: article_citations has a FK to policy_documents, but the policy
        # document may not exist yet (Stage 4 fetches those). We need to ensure
        # a minimal placeholder exists for the FK to succeed.
        for cite in citations:
            try:
                # Create a placeholder policy_document if it doesn't exist
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
                logger.warning(
                    "Failed to upsert citation %s -> %s: %s",
                    cite["doi"], cite["policy_document_id"], e,
                )

    stats = {
        "researchers_processed": len(researchers),
        "researchers_with_hits": researchers_with_hits,
        "no_hits": no_hits,
        "skipped_incremental": skipped_count,
        "articles_upserted": total_articles,
        "citations_upserted": total_citations,
    }

    print(f"Overton Articles: {researchers_with_hits} researchers with hits, "
          f"{total_articles} articles, {total_citations} citations")
    return stats
