"""Stage 3: Resolve a researcher's complete works + policy citations via Overton.

For each researcher:
  1. Assemble the full DOI set — `rmd.dois` ∪ `openalex.works_dois`.
     (If the disambiguation guard fired, `openalex.works_dois` is already empty,
     so we fall back to RMD-known DOIs only.)
  2. POST the DOIs to /generate_id_set.php → `set:N:hash`.
  3. GET /articles.php?dois=<set_id> — paginated; gives us article metadata
     plus the nested `cited_by_documents` array (the policy citation network).
  4. Upsert one row per submitted DOI into `articles`. DOIs Overton doesn't
     have land as stubs (policy_citation_count = 0). DOIs Overton does have
     get the full record + a `policy_citation_count` overlay.
  5. Upsert junction rows into `article_citations`, plus stub rows in
     `policy_documents` for anything Stage 4 will enrich.

This replaces the prior `query=<ORCID>` free-text approach. On a sample
researcher (Foulds) the DOI-set path returns ~3× more policy docs than the
ORCID-text query because it picks up older co-authored work where Overton
hadn't tagged the ORCID.
"""

import logging
import time
import urllib.parse
from datetime import datetime

import requests
from tqdm import tqdm

from . import config
from .utils import api_request, now_iso, normalize_date
from .db.operations import (
    get_all_researchers,
    upsert_article,
    upsert_article_citation,
    insert_policy_document_stub_if_missing,
)
from .db.s3_client import upload_raw_response

logger = logging.getLogger("pipeline.overton_articles")

OVERTON_GENERATE_SET_URL = "https://app.overton.io/generate_id_set.php"


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return (doi.lower().strip()
            .replace("https://doi.org/", "")
            .replace("http://doi.org/", "")
            .rstrip("."))


def _create_doi_set(dois: list[str], max_retries: int = 4) -> str | None:
    """POST DOIs to Overton's set-creation endpoint, return set ID on success.

    Body format: form-urlencoded, with DOIs joined by newlines as the value of
    `dois`. Returns None on persistent failure.

    Mirrors the 429-handling pattern in pipeline.utils.api_request: on Too Many
    Requests, exponential backoff (5/10/20/40s) before retry. The first run
    hit a sustained 429 wall on this endpoint, so retries here are essential.
    """
    if not dois:
        return None
    body = urllib.parse.urlencode({"dois": "\n".join(dois)})
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OVERTON_GENERATE_SET_URL,
                params={"format": "json", "api_key": config.OVERTON_API_KEY},
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.status_code == 429:
                wait = min(2 ** attempt * 5, 60)
                logger.warning("generate_id_set 429; waiting %ds (attempt %d/%d)",
                               wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("set")
        except requests.exceptions.RequestException as e:
            logger.warning("generate_id_set request error (attempt %d/%d): %s",
                           attempt + 1, max_retries, e)
            time.sleep(2 ** attempt)
    logger.warning("generate_id_set failed for %d DOIs after %d retries",
                   len(dois), max_retries)
    return None


def _parse_article(raw: dict) -> dict:
    """Subset of fields we care about — full Overton record stays in raw archive."""
    return {
        "doi": _normalize_doi(raw.get("doi", "")),
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
        "r_open_institution_authors": raw.get("r_open_institution_authors"),
        "last_fetched": now_iso(),
    }


def _extract_citations(article_doi: str, raw: dict) -> list[dict]:
    """Pull cited_by_documents out of an Overton article into junction rows."""
    out = []
    for cite in raw.get("cited_by_documents", []):
        pid = cite.get("policy_document_id")
        if not pid:
            continue
        pages = []
        for pdf_info in (cite.get("cited_by_child_pdfs") or {}).values():
            pages.extend(pdf_info.get("on_pages", []))
        out.append({
            "doi": article_doi,
            "policy_document_id": pid,
            "metadata": {
                "source_title": cite.get("source_title"),
                "document_title": cite.get("document_title"),
                "published_on": normalize_date(cite.get("published_on")),
                "type": cite.get("type"),
                "country": cite.get("country"),
                "topics": cite.get("topics", []),
                "classifications": cite.get("classifications", []),
                "cited_on_pages": sorted(set(pages)),
            },
        })
    return out


def _fetch_articles_by_set(set_id: str, archive_label: str) -> list[dict]:
    """Page through articles.php?dois=<set_id> and return all raw article rows."""
    all_raw = []
    page = 1
    while True:
        data = api_request(
            config.OVERTON_ARTICLES_URL,
            params={
                "api_key": config.OVERTON_API_KEY,
                "format": "json",
                "dois": set_id,
                "page": str(page),
            },
            delay=config.OVERTON_DELAY,
            timeout=30,
        )
        if not data:
            break

        try:
            upload_raw_response("overton-articles", f"{archive_label}_page{page:03d}", data)
        except Exception as e:
            logger.warning("S3 archive failed: %s", e)

        results_wrapper = data.get("results", {})
        results = (results_wrapper.get("results", []) if isinstance(results_wrapper, dict)
                   else results_wrapper)
        if not results:
            break
        all_raw.extend(results)

        if not (data.get("query") or {}).get("next_page_url"):
            break
        page += 1

    return all_raw


def _last_cited_at(article: dict) -> datetime | None:
    raw = article.get("last_cited")
    if not raw:
        return None
    norm = normalize_date(raw)
    if not norm:
        return None
    try:
        return datetime.fromisoformat(norm)
    except ValueError:
        return None


def run(incremental: bool = False) -> dict:
    """Resolve every researcher's works and overlay Overton policy citations.

    Args:
        incremental: Currently a placeholder — full runs are the supported mode
            during the cut-over. Will reuse INCREMENTAL_SKIP_DAYS once stable.
    """
    try:
        researchers = get_all_researchers()
    except Exception as e:
        logger.error("Failed to load researchers: %s", e)
        return {"error": str(e)}

    print(f"Overton: processing {len(researchers)} researchers via DOI-set flow")

    counts = {
        "researchers_processed": 0,
        "researchers_skipped_no_dois": 0,
        "set_creation_failed": 0,
        "articles_upserted": 0,
        "stubs_upserted": 0,
        "citations_upserted": 0,
        "policy_doc_stubs_upserted": 0,
    }

    for r in tqdm(researchers, desc="Overton DOI-set"):
        orcid = r["orcid"]
        data = r["data"] or {}
        rmd_dois = {_normalize_doi(d) for d in (data.get("rmd") or {}).get("dois") or [] if d}
        oa_dois = {_normalize_doi(d) for d in (data.get("openalex") or {}).get("works_dois") or [] if d}
        rmd_dois.discard(""); oa_dois.discard("")
        all_dois = rmd_dois | oa_dois

        if not all_dois:
            counts["researchers_skipped_no_dois"] += 1
            continue

        set_id = _create_doi_set(sorted(all_dois))
        if not set_id:
            counts["set_creation_failed"] += 1
            continue

        raw_articles = _fetch_articles_by_set(set_id, archive_label=orcid)
        overton_dois: set[str] = set()

        for raw in raw_articles:
            parsed = _parse_article(raw)
            doi = parsed["doi"]
            if not doi:
                continue
            overton_dois.add(doi)

            sources = ["overton"]
            if doi in rmd_dois:
                sources.insert(0, "rmd")
            if doi in oa_dois:
                sources.insert(0, "openalex")

            try:
                upsert_article(
                    parsed,
                    policy_citation_count=parsed.get("citations") or 0,
                    last_policy_cited_at=_last_cited_at(parsed),
                    sources=sources,
                )
                counts["articles_upserted"] += 1
            except Exception as e:
                logger.warning("upsert article %s: %s", doi, e)

            for cite in _extract_citations(doi, raw):
                pid = cite["policy_document_id"]
                try:
                    # Stub the policy_document row so the FK on article_citations
                    # holds. ON CONFLICT DO NOTHING — never overwrites Stage 4's
                    # enriched metadata if the row already has it.
                    insert_policy_document_stub_if_missing(pid)
                    counts["policy_doc_stubs_upserted"] += 1
                    upsert_article_citation(
                        doi=cite["doi"],
                        policy_document_id=pid,
                        citation_metadata=cite["metadata"],
                    )
                    counts["citations_upserted"] += 1
                except Exception as e:
                    logger.warning("citation %s -> %s: %s", doi, pid, e)

        # DOIs we submitted but Overton didn't return → stub article rows so the
        # researcher's complete works list lands in the table, even non-policy-cited.
        for doi in all_dois - overton_dois:
            sources = []
            if doi in rmd_dois:
                sources.append("rmd")
            if doi in oa_dois:
                sources.append("openalex")
            try:
                upsert_article(
                    {"doi": doi, "last_fetched": now_iso()},
                    policy_citation_count=0,
                    sources=sources,
                )
                counts["stubs_upserted"] += 1
            except Exception as e:
                logger.warning("upsert stub %s: %s", doi, e)

        counts["researchers_processed"] += 1
        # Light inter-researcher pacing — keeps sustained call rate well under
        # whatever per-key burst limit the 429 wall represents.
        time.sleep(config.OVERTON_DELAY)

    print(f"Overton: processed={counts['researchers_processed']}  "
          f"skipped_no_dois={counts['researchers_skipped_no_dois']}  "
          f"set_failures={counts['set_creation_failed']}\n"
          f"  articles_upserted={counts['articles_upserted']}  "
          f"stubs={counts['stubs_upserted']}  "
          f"citations={counts['citations_upserted']}")
    return counts
