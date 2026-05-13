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
                    "grants_count": len(rmd.get("grants", [])),
                    "total_grant_dollars": sum(
                        g.get("amount_in_dollars", 0) or 0
                        for g in rmd.get("grants", [])
                    ),
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


# ── Single Researcher Lookup ─────────────────────────────────────────────────


def get_researcher_by_orcid(orcid: str) -> dict | None:
    """Fetch a single researcher's full JSONB by ORCID."""
    engine = get_engine()
    if engine is None:
        return None
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
                # Pluck only the fields the dashboard renders in SQL — pulling
                # the full researcher.data and policy_doc.data JSONB blobs
                # across ~46k rows OOMs the Fargate task (4GB).
                rows = conn.execute(text("""
                    WITH researcher_dois AS (
                        SELECT
                            r.orcid,
                            r.display_name,
                            r.data #>> '{openalex,topics,0,subfield}' AS primary_subfield,
                            r.data #>> '{openalex,topics,0,field}'    AS primary_field,
                            r.data #>> '{openalex,topics,0,domain}'   AS primary_domain,
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
                        rd.primary_subfield,
                        rd.primary_field,
                        rd.primary_domain,
                        pd.policy_document_id,
                        pd.data->>'title'                  AS doc_title,
                        pd.data #>> '{source,title}'       AS source_title,
                        pd.data #>> '{source,country}'     AS source_country,
                        pd.data #>> '{source,type}'        AS source_type,
                        pd.data->>'published_on'           AS published_on,
                        pd.data->'topics'                  AS topics,
                        pd.data->'sdgcategories'           AS sdgcategories
                    FROM researcher_dois rd
                    JOIN article_citations ac ON ac.doi = rd.doi
                    JOIN policy_documents pd ON pd.policy_document_id = ac.policy_document_id
                    WHERE pd.data->>'title' IS NOT NULL
                """)).mappings().fetchall()

            flat_docs = [dict(row) for row in rows]
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

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3")
    return _s3_client


def get_s3_presigned_url(s3_key: str | None) -> str | None:
    """Sign an S3 key into a presigned GET URL. Returns None if no key or S3 not configured."""
    import os
    if not s3_key:
        return None
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        return None
    try:
        return _get_s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=3600,
        )
    except Exception as e:
        logger.warning("Failed to sign %s: %s", s3_key, e)
        return None
