"""SQLAlchemy table definitions for the Overton pipeline database.

Tables:
    researchers       — One row per ORCID, full profile in JSONB
    articles          — One row per DOI, from Overton Articles API
    policy_documents  — One row per policy_document_id, from Overton Documents API
    article_citations — Junction table linking articles to policy documents
    pipeline_metadata — Pipeline run tracking
"""

import logging

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Text,
    Boolean,
    Integer,
    Index,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from pipeline.db.connection import get_engine

logger = logging.getLogger(__name__)

metadata = MetaData()

researchers = Table(
    "researchers",
    metadata,
    Column("orcid", Text, primary_key=True),
    Column("openalex_id", Text),
    Column("display_name", Text),
    Column("data", JSONB, nullable=False),
    Column("last_fetched", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
)

articles = Table(
    "articles",
    metadata,
    Column("doi", Text, primary_key=True),
    Column("data", JSONB, nullable=False),
    # Policy-citation overlay (denormalized for fast filtering)
    Column("policy_citation_count", Integer, server_default="0"),
    Column("last_policy_cited_at", TIMESTAMP(timezone=True)),
    # Which sources discovered this work — {'rmd', 'openalex', 'overton'}
    Column("source_set", JSONB, server_default="[]"),
    Column("last_fetched", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
)

policy_documents = Table(
    "policy_documents",
    metadata,
    Column("policy_document_id", Text, primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("pdf_url", Text),
    Column("s3_pdf_key", Text),
    Column("download_status", Text, server_default="pending"),
    Column("dont_show_pdf", Boolean, server_default="false"),
    Column("last_fetched", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()),
)

article_citations = Table(
    "article_citations",
    metadata,
    Column("doi", Text, ForeignKey("articles.doi"), primary_key=True),
    Column("policy_document_id", Text, ForeignKey("policy_documents.policy_document_id"), primary_key=True),
    Column("citation_metadata", JSONB),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

pipeline_metadata = Table(
    "pipeline_metadata",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("stats", JSONB),
    Column("started_at", TIMESTAMP(timezone=True)),
    Column("completed_at", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

# Secondary indexes (created separately for clarity)
_indexes = [
    Index("idx_researchers_openalex_id", researchers.c.openalex_id),
    Index("idx_researchers_display_name", researchers.c.display_name),
    Index("idx_researchers_data_gin", researchers.c.data, postgresql_using="gin"),
    Index("idx_articles_orcids_gin", articles.c.data["orcids"], postgresql_using="gin"),
    Index("idx_articles_last_fetched", articles.c.last_fetched),
    Index("idx_articles_policy_cited", articles.c.policy_citation_count,
          postgresql_where=articles.c.policy_citation_count > 0),
    Index("idx_policy_docs_source_country", policy_documents.c.data["source"]["country"].astext),
    Index("idx_policy_docs_source_type", policy_documents.c.data["source"]["type"].astext),
    Index("idx_policy_docs_download", policy_documents.c.download_status, postgresql_where=policy_documents.c.s3_pdf_key.is_(None)),
    Index("idx_citations_doi", article_citations.c.doi),
    Index("idx_citations_policy_doc", article_citations.c.policy_document_id),
    Index("idx_pipeline_meta_run_stage", pipeline_metadata.c.run_id, pipeline_metadata.c.stage, unique=True),
    Index("idx_pipeline_meta_created", pipeline_metadata.c.created_at),
]


def ensure_tables():
    """Create all tables and indexes if they don't already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    """
    engine = get_engine()
    metadata.create_all(engine, checkfirst=True)
    logger.info("Database tables and indexes ensured")
