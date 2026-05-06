"""Stage 6: Export pipeline data into dashboard-ready files.

Reads from the PostgreSQL database and produces:
- researchers.json: full dataset (compact)
- researchers_summary.json: lightweight index for fast loading
- policy_documents_flat.json: denormalized for chart pages

This stage is optional when the dashboard reads directly from the database.
"""

import logging
import shutil
from datetime import datetime

from . import config
from .utils import load_json, save_json, now_iso
from .db.operations import (
    get_all_researchers,
    get_latest_pipeline_run,
    get_researcher_policy_citations,
)

logger = logging.getLogger("pipeline.export")


def _build_summary(researchers: list[dict], orcid_to_policy_count: dict[str, int]) -> list[dict]:
    """Build lightweight summary records for fast dashboard loading."""
    summaries = []
    for r in researchers:
        oa = r.get("openalex") or {}
        rmd = r.get("rmd") or {}
        flags = r.get("flags") or {}

        topics = oa.get("topics", [])
        primary_topic = topics[0] if topics else {}

        summaries.append({
            "orcid": r["orcid"],
            "openalex_id": r.get("openalex_id"),
            "display_name": r.get("display_name"),
            "works_count": oa.get("works_count", 0),
            "works_dois_count": len(oa.get("works_dois") or []),
            "cited_by_count": oa.get("cited_by_count", 0),
            "h_index": oa.get("h_index", 0),
            "primary_topic": primary_topic.get("topic"),
            "primary_subfield": primary_topic.get("subfield"),
            "primary_field": primary_topic.get("field"),
            "primary_domain": primary_topic.get("domain"),
            "has_rmd": bool(rmd.get("webaccess_id")),
            "rmd_org": (rmd.get("profile") or {}).get("organization_name"),
            "policy_documents_total": orcid_to_policy_count.get(r["orcid"], 0),
            "grants_count": len(rmd.get("grants", [])),
            "total_grant_dollars": sum(
                g.get("amount_in_dollars", 0) or 0
                for g in rmd.get("grants", [])
            ),
            "lookup_method": flags.get("lookup_method", "orcid"),
            "oa_disambiguation_suspect": bool(flags.get("oa_disambiguation_suspect")),
        })

    return summaries


def _build_policy_docs_flat(citation_rows: list[dict]) -> list[dict]:
    """Denormalize researcher × policy-document join rows for chart pages."""
    out = []
    for row in citation_rows:
        rdata = row.get("researcher_data") or {}
        oa = rdata.get("openalex") or {}
        topics = oa.get("topics") or []
        primary_topic = topics[0] if topics else {}

        doc = row.get("policy_doc_data") or {}
        source = doc.get("source") or {}

        out.append({
            "orcid": row["orcid"],
            "display_name": row.get("display_name"),
            "primary_subfield": primary_topic.get("subfield"),
            "primary_field": primary_topic.get("field"),
            "primary_domain": primary_topic.get("domain"),
            "policy_document_id": row["policy_document_id"],
            "doc_title": doc.get("title"),
            "source_title": source.get("title"),
            "source_country": source.get("country"),
            "source_type": source.get("type"),
            "published_on": doc.get("published_on"),
            "topics": doc.get("topics") or [],
            "sdgcategories": doc.get("sdgcategories") or [],
        })

    return out


def run(researchers: list[dict] | None = None) -> dict:
    """Export pipeline data into dashboard-ready files.

    Args:
        researchers: Researcher list. If None, loads from database,
                     falling back to the latest available stage output file.

    Returns:
        Stats dict.
    """
    # Load from database if not passed in
    if researchers is None:
        try:
            db_researchers = get_all_researchers()
            researchers = [r["data"] for r in db_researchers]
            print(f"Export: Loaded {len(researchers)} researchers from database")
        except Exception as e:
            logger.warning("DB unavailable, loading from files: %s", e)
            researchers = None

    # Fall back to file-based loading
    if not researchers:
        for filename in [config.OVERTON_OUTPUT, config.RMD_OUTPUT, config.OPENALEX_OUTPUT]:
            path = config.DATA_DIR / filename
            if path.exists():
                researchers = load_json(path, [])
                print(f"Export: Loaded {len(researchers)} researchers from {filename}")
                break
        if not researchers:
            print("Export: No pipeline data found. Run earlier stages first.")
            return {"error": "no data"}

    # 1. Full dataset (compact)
    full_path = config.DATA_DIR / config.FINAL_OUTPUT
    save_json(researchers, full_path, compact=True)

    # Pull the researcher × policy-doc join from the DB once. Both the summary
    # counts and the flat-doc rows derive from this.
    try:
        citation_rows = get_researcher_policy_citations()
        print(f"Export: {len(citation_rows)} researcher × policy-document rows from DB")
    except Exception as e:
        logger.warning("Could not query researcher policy citations: %s", e)
        citation_rows = []

    orcid_to_policy_count: dict[str, int] = {}
    for row in citation_rows:
        orcid_to_policy_count[row["orcid"]] = orcid_to_policy_count.get(row["orcid"], 0) + 1

    # 2. Summary index
    summaries = _build_summary(researchers, orcid_to_policy_count)
    summary_path = config.DATA_DIR / config.SUMMARY_OUTPUT
    save_json(summaries, summary_path)

    # 3. Flat policy documents
    flat_docs = _build_policy_docs_flat(citation_rows)
    flat_path = config.DATA_DIR / config.POLICY_DOCS_FLAT_OUTPUT
    save_json(flat_docs, flat_path, compact=True)

    # 4. Copy to dashboard/data/
    config.DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for src_name, src_path in [
        (config.FINAL_OUTPUT, full_path),
        (config.SUMMARY_OUTPUT, summary_path),
        (config.POLICY_DOCS_FLAT_OUTPUT, flat_path),
    ]:
        dst = config.DASHBOARD_DATA_DIR / src_name
        shutil.copy2(src_path, dst)
        logger.info(f"Copied {src_name} to dashboard/data/")

    # 5. Run metadata
    with_policy = sum(1 for r in researchers
                      if orcid_to_policy_count.get(r["orcid"], 0) > 0)
    with_rmd = sum(1 for r in researchers
                   if (r.get("rmd") or {}).get("webaccess_id"))
    total_grants = sum(
        len((r.get("rmd") or {}).get("grants", []))
        for r in researchers
    )

    metadata = {
        "run_timestamp": now_iso(),
        "total_researchers": len(researchers),
        "with_policy_documents": with_policy,
        "with_rmd_data": with_rmd,
        "total_grants": total_grants,
        "total_policy_documents": len(flat_docs),
        "file_sizes": {
            config.FINAL_OUTPUT: full_path.stat().st_size,
            config.SUMMARY_OUTPUT: summary_path.stat().st_size,
            config.POLICY_DOCS_FLAT_OUTPUT: flat_path.stat().st_size,
        },
    }
    save_json(metadata, config.DATA_DIR / config.RUN_METADATA)

    stats = {
        "researchers": len(researchers),
        "with_policy_docs": with_policy,
        "with_rmd": with_rmd,
        "total_grants": total_grants,
        "policy_doc_rows": len(flat_docs),
    }

    print(f"\nExport complete:")
    print(f"  Researchers: {len(researchers):,}")
    print(f"  With policy docs: {with_policy:,}")
    print(f"  With RMD data: {with_rmd:,}")
    print(f"  Total policy doc rows: {len(flat_docs):,}")
    print(f"  Total grants: {total_grants:,}")

    return stats
