"""CRUD operations for the Overton pipeline database.

All write operations use INSERT ... ON CONFLICT DO UPDATE (upsert) to be
idempotent and safe for incremental pipeline runs.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from pipeline.db.connection import get_engine
from pipeline.db.schema import (
    researchers,
    articles,
    policy_documents,
    article_citations,
    pipeline_metadata,
)

logger = logging.getLogger(__name__)


# ── Researchers ──────────────────────────────────────────────────────────────


def upsert_researcher(doc: dict) -> None:
    """Insert or update a researcher record keyed on ORCID."""
    stmt = insert(researchers).values(
        orcid=doc["orcid"],
        openalex_id=doc.get("openalex_id"),
        display_name=doc.get("display_name"),
        data=doc,
        last_fetched=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["orcid"],
        set_={
            "openalex_id": stmt.excluded.openalex_id,
            "display_name": stmt.excluded.display_name,
            "data": stmt.excluded.data,
            "last_fetched": stmt.excluded.last_fetched,
            "updated_at": func.now(),
        },
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)


def bulk_upsert_researchers(docs: list[dict]) -> int:
    """Upsert multiple researcher records in a single transaction.

    Returns the number of rows affected.
    """
    if not docs:
        return 0

    with get_engine().begin() as conn:
        for doc in docs:
            stmt = insert(researchers).values(
                orcid=doc["orcid"],
                openalex_id=doc.get("openalex_id"),
                display_name=doc.get("display_name"),
                data=doc,
                last_fetched=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["orcid"],
                set_={
                    "openalex_id": stmt.excluded.openalex_id,
                    "display_name": stmt.excluded.display_name,
                    "data": stmt.excluded.data,
                    "last_fetched": stmt.excluded.last_fetched,
                    "updated_at": func.now(),
                },
            )
            conn.execute(stmt)

    logger.info("Bulk upserted %d researchers", len(docs))
    return len(docs)


def get_researchers_needing_update(skip_days: int = 7) -> list[dict]:
    """Return researchers whose last_fetched is older than skip_days ago, or null."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=skip_days)
    stmt = select(researchers.c.orcid, researchers.c.data).where(
        (researchers.c.last_fetched < cutoff) | (researchers.c.last_fetched.is_(None))
    )
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [{"orcid": row.orcid, "data": row.data} for row in rows]


def get_all_researchers() -> list[dict]:
    """Return all researcher records."""
    stmt = select(researchers.c.orcid, researchers.c.display_name, researchers.c.data)
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [{"orcid": row.orcid, "display_name": row.display_name, "data": row.data} for row in rows]


def get_researcher_by_orcid(orcid: str) -> dict | None:
    """Return a single researcher by ORCID, or None."""
    stmt = select(researchers.c.data).where(researchers.c.orcid == orcid)
    with get_engine().connect() as conn:
        row = conn.execute(stmt).fetchone()
    return row.data if row else None


# ── Articles ─────────────────────────────────────────────────────────────────


def upsert_article(
    doc: dict,
    policy_citation_count: int | None = None,
    last_policy_cited_at: datetime | None = None,
    sources: list[str] | None = None,
) -> None:
    """Insert or update an article record keyed on DOI.

    Optional columns:
        policy_citation_count: count of policy docs citing this article (overwrites on update).
        last_policy_cited_at: most-recent policy citation date.
        sources: which discovery paths found this article — e.g. ['rmd','openalex','overton'].
                 On update, sources are merged (set union) rather than overwritten.
    """
    values = {
        "doi": doc["doi"],
        "data": doc,
        "last_fetched": datetime.now(timezone.utc),
    }
    if policy_citation_count is not None:
        values["policy_citation_count"] = policy_citation_count
    if last_policy_cited_at is not None:
        values["last_policy_cited_at"] = last_policy_cited_at
    if sources is not None:
        values["source_set"] = list(sources)

    stmt = insert(articles).values(**values)
    set_ = {
        "data": stmt.excluded.data,
        "last_fetched": stmt.excluded.last_fetched,
        "updated_at": func.now(),
    }
    if policy_citation_count is not None:
        set_["policy_citation_count"] = stmt.excluded.policy_citation_count
    if last_policy_cited_at is not None:
        set_["last_policy_cited_at"] = stmt.excluded.last_policy_cited_at
    if sources is not None:
        # Merge source sets via JSONB || (preserves order, dedup happens via consumer)
        set_["source_set"] = articles.c.source_set.op("||")(stmt.excluded.source_set)

    stmt = stmt.on_conflict_do_update(index_elements=["doi"], set_=set_)
    with get_engine().begin() as conn:
        conn.execute(stmt)


def get_articles_by_orcid(orcid: str) -> list[dict]:
    """Return all articles that include the given ORCID."""
    stmt = select(articles.c.doi, articles.c.data).where(
        articles.c.data["orcids"].contains(f'["{orcid}"]')
    )
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [{"doi": row.doi, "data": row.data} for row in rows]


# ── Policy Documents ─────────────────────────────────────────────────────────


def insert_policy_document_stub_if_missing(policy_document_id: str) -> None:
    """Insert a placeholder policy_documents row if one doesn't already exist.

    Used by Stage 3 to satisfy the article_citations foreign key when a citation
    references a policy doc Stage 4 hasn't enriched yet. Critically, this uses
    ON CONFLICT DO NOTHING — it must NEVER overwrite an already-enriched row,
    or Stage 4's hard-won metadata gets clobbered back to a bare stub.
    """
    stmt = insert(policy_documents).values(
        policy_document_id=policy_document_id,
        data={"policy_document_id": policy_document_id},
        last_fetched=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["policy_document_id"])
    with get_engine().begin() as conn:
        conn.execute(stmt)


def upsert_policy_document(doc: dict) -> None:
    """Insert or update a policy document record."""
    # Extract convenience columns from the JSONB data
    pdf_url = doc.get("pdf_url")
    dont_show = doc.get("dont_show_pdf")
    if isinstance(dont_show, str):
        dont_show = dont_show.lower() == "true"

    stmt = insert(policy_documents).values(
        policy_document_id=doc["policy_document_id"],
        data=doc,
        pdf_url=pdf_url,
        dont_show_pdf=bool(dont_show) if dont_show is not None else False,
        last_fetched=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["policy_document_id"],
        set_={
            "data": stmt.excluded.data,
            "pdf_url": stmt.excluded.pdf_url,
            "dont_show_pdf": stmt.excluded.dont_show_pdf,
            "last_fetched": stmt.excluded.last_fetched,
            "updated_at": func.now(),
        },
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)


def get_policy_documents_needing_pdf_download() -> list[dict]:
    """Return policy documents eligible for PDF download."""
    stmt = select(
        policy_documents.c.policy_document_id,
        policy_documents.c.pdf_url,
    ).where(
        policy_documents.c.pdf_url.isnot(None),
        policy_documents.c.dont_show_pdf.is_(False),
        policy_documents.c.s3_pdf_key.is_(None),
        policy_documents.c.download_status.in_(["pending", "failed"]),
    )
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [{"policy_document_id": row.policy_document_id, "pdf_url": row.pdf_url} for row in rows]


def update_pdf_download_status(
    policy_document_id: str, s3_pdf_key: str | None, status: str
) -> None:
    """Update the PDF download status for a policy document."""
    with get_engine().begin() as conn:
        conn.execute(
            policy_documents.update()
            .where(policy_documents.c.policy_document_id == policy_document_id)
            .values(
                s3_pdf_key=s3_pdf_key,
                download_status=status,
                updated_at=func.now(),
            )
        )


# ── Article Citations (junction table) ───────────────────────────────────────


def upsert_article_citation(
    doi: str, policy_document_id: str, citation_metadata: dict | None = None
) -> None:
    """Insert or update an article ↔ policy document citation link."""
    stmt = insert(article_citations).values(
        doi=doi,
        policy_document_id=policy_document_id,
        citation_metadata=citation_metadata,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["doi", "policy_document_id"],
        set_={"citation_metadata": stmt.excluded.citation_metadata},
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)


def get_researcher_policy_citations() -> list[dict]:
    """Return one row per (researcher × policy document) citation.

    Joins researchers.data (openalex.works_dois ∪ rmd.dois) → article_citations →
    policy_documents. Used by the export stage to build per-researcher policy
    impact summaries and the denormalized flat-doc table.
    """
    from sqlalchemy import text
    sql = text("""
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
            ac.policy_document_id,
            pd.data AS policy_doc_data,
            ac.citation_metadata
        FROM researcher_dois rd
        JOIN article_citations ac ON ac.doi = rd.doi
        JOIN policy_documents pd ON pd.policy_document_id = ac.policy_document_id
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [
        {
            "orcid": row.orcid,
            "display_name": row.display_name,
            "researcher_data": row.researcher_data,
            "policy_document_id": row.policy_document_id,
            "policy_doc_data": row.policy_doc_data,
            "citation_metadata": row.citation_metadata,
        }
        for row in rows
    ]


def get_unique_cited_policy_doc_ids() -> set[str]:
    """Return the set of all unique policy_document_ids from the citations table."""
    stmt = select(article_citations.c.policy_document_id.distinct())
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return {row[0] for row in rows}


def get_existing_policy_doc_ids() -> set[str]:
    """Return the set of all policy_document_ids already in the policy_documents table."""
    stmt = select(policy_documents.c.policy_document_id)
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return {row[0] for row in rows}


# ── Pipeline Metadata ────────────────────────────────────────────────────────


def record_pipeline_run(
    run_id: str,
    stage: str,
    status: str,
    stats: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Record or update a pipeline run stage entry."""
    now = datetime.now(timezone.utc)
    stmt = insert(pipeline_metadata).values(
        run_id=run_id,
        stage=stage,
        status=status,
        stats=stats or {},
        started_at=started_at or now,
        completed_at=completed_at if status in ("completed", "failed") else None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["run_id", "stage"],
        set_={
            "status": stmt.excluded.status,
            "stats": stmt.excluded.stats,
            "completed_at": stmt.excluded.completed_at,
        },
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)


def get_latest_pipeline_run() -> dict | None:
    """Return the most recent pipeline run metadata."""
    stmt = (
        select(pipeline_metadata)
        .order_by(pipeline_metadata.c.created_at.desc())
        .limit(1)
    )
    with get_engine().connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return None
    return {
        "run_id": row.run_id,
        "stage": row.stage,
        "status": row.status,
        "stats": row.stats,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
