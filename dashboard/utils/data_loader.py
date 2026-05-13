"""Centralized data loading for the dashboard with Streamlit caching.

Tries PostgreSQL first, falls back to flat JSON files if the database
is not available.
"""

import json
import logging
from pathlib import Path

import streamlit as st

from utils.db_connection import get_engine

logger = logging.getLogger(__name__)

# Data paths - check dashboard/data/ first (Docker), then data/pipeline/ (local dev)
_DASHBOARD_DATA = Path(__file__).parent.parent / "data"
_LOCAL_DATA = Path(__file__).parent.parent.parent / "data" / "pipeline"


def _data_dir() -> Path:
    """Resolve the data directory (Docker vs local dev)."""
    if (_DASHBOARD_DATA / "researchers_summary.json").exists():
        return _DASHBOARD_DATA
    if (_LOCAL_DATA / "researchers_summary.json").exists():
        return _LOCAL_DATA
    return _DASHBOARD_DATA


def _load_json_file(filename: str) -> list | dict:
    """Load a JSON file from the data directory."""
    path = _data_dir() / filename
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Summary ──────────────────────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_summary() -> list[dict]:
    """Load the lightweight researcher summary index.

    From DB: builds summary from researchers table.
    Fallback: reads researchers_summary.json.
    """
    engine = get_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT orcid, openalex_id, display_name, data FROM researchers"
                )).fetchall()

                # Count policy citations per researcher by joining the
                # researcher's OpenAlex/RMD DOI list against article_citations.
                # Same join pattern as pipeline.db.operations.get_researcher_policy_citations.
                cite_rows = conn.execute(text("""
                    SELECT rd.orcid, COUNT(DISTINCT ac.policy_document_id) AS doc_count
                    FROM (
                        SELECT r.orcid, lower(d.value) AS doi
                        FROM researchers r
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            COALESCE(r.data #> '{openalex,works_dois}', '[]'::jsonb)
                            || COALESCE(r.data #> '{rmd,dois}', '[]'::jsonb)
                        ) AS d(value)
                    ) rd
                    JOIN article_citations ac ON ac.doi = rd.doi
                    GROUP BY rd.orcid
                """)).fetchall()
                citation_counts = {cr.orcid: cr.doc_count for cr in cite_rows}

            summaries = []
            for row in rows:
                data = row.data or {}
                oa = data.get("openalex") or {}
                rmd = data.get("rmd") or {}
                flags = data.get("flags") or {}
                topics = oa.get("topics", [])
                primary_topic = topics[0] if topics else {}

                summaries.append({
                    "orcid": row.orcid,
                    "openalex_id": row.openalex_id,
                    "display_name": row.display_name,
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
                    "policy_documents_total": citation_counts.get(row.orcid, 0),
                    "lookup_method": flags.get("lookup_method", "orcid"),
                    "oa_disambiguation_suspect": bool(flags.get("oa_disambiguation_suspect")),
                })
            logger.info("Loaded %d researcher summaries from database", len(summaries))
            return summaries
        except Exception as e:
            logger.warning("DB summary query failed, falling back to file: %s", e)

    # Flat file fallback
    data = _load_json_file("researchers_summary.json")
    if not data:
        st.error("Summary data not found. Run the pipeline first.")
    return data


# ── Full Researchers ─────────────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_researchers() -> list[dict]:
    """Load the full researcher dataset.

    From DB: reads all researcher JSONB data.
    Fallback: reads researchers.json.
    """
    engine = get_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT data FROM researchers")).fetchall()
            researchers = [row.data for row in rows]
            logger.info("Loaded %d researchers from database", len(researchers))
            return researchers
        except Exception as e:
            logger.warning("DB researchers query failed, falling back to file: %s", e)

    data = _load_json_file("researchers.json")
    if not data:
        st.error("Researcher data not found. Run the pipeline first.")
    return data


# ── Single Researcher Lookup ─────────────────────────────────────────────────


def get_researcher_by_orcid(researchers_or_orcid, orcid: str | None = None) -> dict | None:
    """Find a researcher by ORCID.

    Can be called two ways:
    - get_researcher_by_orcid(researchers_list, orcid) — legacy list scan
    - get_researcher_by_orcid(orcid) — direct DB lookup (preferred)
    """
    # Handle direct ORCID lookup
    if isinstance(researchers_or_orcid, str) and orcid is None:
        orcid = researchers_or_orcid
        engine = get_engine()
        if engine is not None:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT data FROM researchers WHERE orcid = :orcid"),
                        {"orcid": orcid},
                    ).fetchone()
                return row.data if row else None
            except Exception as e:
                logger.warning("DB lookup failed for %s: %s", orcid, e)
                return None
        return None

    # Legacy: scan a list
    for r in researchers_or_orcid:
        if r.get("orcid") == orcid:
            return r
    return None


# ── Policy Documents Flat ────────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_policy_docs_flat() -> list[dict]:
    """Load the flat policy documents for chart pages.

    From DB: joins researchers with their overton policy documents.
    Fallback: reads policy_documents_flat.json.
    """
    engine = get_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                # Researcher → DOI list → article_citations → policy_documents.
                # Same join as pipeline.db.operations.get_researcher_policy_citations.
                rows = conn.execute(text("""
                    WITH researcher_dois AS (
                        SELECT
                            r.orcid,
                            r.display_name,
                            r.data,
                            lower(d.value) AS doi
                        FROM researchers r
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            COALESCE(r.data #> '{openalex,works_dois}', '[]'::jsonb)
                            || COALESCE(r.data #> '{rmd,dois}', '[]'::jsonb)
                        ) AS d(value)
                    )
                    SELECT
                        rd.orcid,
                        rd.display_name,
                        rd.data AS researcher_data,
                        pd.policy_document_id,
                        pd.data AS doc_data
                    FROM researcher_dois rd
                    JOIN article_citations ac ON ac.doi = rd.doi
                    JOIN policy_documents pd ON pd.policy_document_id = ac.policy_document_id
                    WHERE pd.data->>'title' IS NOT NULL
                """)).fetchall()

            flat_docs = []
            for row in rows:
                r_data = row.researcher_data or {}
                doc = row.doc_data or {}
                oa = r_data.get("openalex") or {}
                topics = oa.get("topics", [])
                primary_topic = topics[0] if topics else {}
                source = doc.get("source") or {}

                flat_docs.append({
                    "orcid": row.orcid,
                    "display_name": row.display_name,
                    "primary_subfield": primary_topic.get("subfield"),
                    "primary_field": primary_topic.get("field"),
                    "primary_domain": primary_topic.get("domain"),
                    "policy_document_id": row.policy_document_id,
                    "doc_title": doc.get("title"),
                    "source_title": source.get("title"),
                    "source_country": source.get("country"),
                    "source_type": source.get("type"),
                    "published_on": doc.get("published_on"),
                    "topics": doc.get("topics", []),
                    "sdgcategories": doc.get("sdgcategories", []),
                })
            logger.info("Built %d flat policy doc rows from database", len(flat_docs))
            return flat_docs
        except Exception as e:
            logger.warning("DB policy docs query failed, falling back to file: %s", e)

    data = _load_json_file("policy_documents_flat.json")
    if not data:
        st.error("Policy documents not found. Run the pipeline first.")
    return data


# ── Run Metadata ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_run_metadata() -> dict:
    """Load pipeline run metadata.

    From DB: reads the latest pipeline_metadata entry.
    Fallback: reads run_metadata.json.
    """
    engine = get_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT run_id, stage, status, stats, started_at, completed_at "
                    "FROM pipeline_metadata "
                    "ORDER BY created_at DESC LIMIT 1"
                )).fetchone()
            if row:
                return {
                    "run_id": row.run_id,
                    "stage": row.stage,
                    "status": row.status,
                    "stats": row.stats,
                    "run_timestamp": row.completed_at.isoformat() if row.completed_at else
                                     row.started_at.isoformat() if row.started_at else "Unknown",
                }
        except Exception as e:
            logger.warning("DB metadata query failed, falling back to file: %s", e)

    return _load_json_file("run_metadata.json") or {}


# ── PDF Presigned URLs ───────────────────────────────────────────────────────


def get_pdf_presigned_url(policy_document_id: str) -> str | None:
    """Generate a presigned S3 URL for a policy document PDF.

    Returns None if the document hasn't been downloaded or S3 is not configured.
    """
    engine = get_engine()
    if engine is None:
        return None

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT s3_pdf_key FROM policy_documents "
                    "WHERE policy_document_id = :id AND s3_pdf_key IS NOT NULL"
                ),
                {"id": policy_document_id},
            ).fetchone()

        if not row or not row.s3_pdf_key:
            return None

        import os
        import boto3
        bucket = os.getenv("S3_BUCKET_NAME")
        if not bucket:
            return None

        s3 = boto3.client("s3")
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": row.s3_pdf_key},
            ExpiresIn=3600,
        )
    except Exception as e:
        logger.warning("Failed to generate presigned URL for %s: %s", policy_document_id, e)
        return None
