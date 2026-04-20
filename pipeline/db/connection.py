"""PostgreSQL connection management via SQLAlchemy.

Reads connection parameters from AWS Secrets Manager or the DATABASE_URL
environment variable. Uses a module-level singleton engine for connection
pooling.
"""

import json
import os
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _build_url_from_secret(secret_arn: str) -> str:
    """Retrieve DB credentials from Secrets Manager and build a connection URL."""
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])

    host = secret["host"]
    port = secret.get("port", 5432)
    username = secret["username"]
    password = secret["password"]
    dbname = secret.get("dbname", "overton")

    return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{dbname}"


def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine.

    Connection source priority:
    1. DATABASE_URL environment variable (for local dev / testing)
    2. DATABASE_SECRET_ARN environment variable (for AWS deployment)
    """
    global _engine
    if _engine is not None:
        return _engine

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        logger.info("Connecting to PostgreSQL via DATABASE_URL")
        _engine = create_engine(database_url, pool_size=5, max_overflow=10)
    else:
        secret_arn = os.getenv("DATABASE_SECRET_ARN")
        if not secret_arn:
            raise RuntimeError(
                "No database connection configured. "
                "Set DATABASE_URL or DATABASE_SECRET_ARN."
            )
        logger.info("Connecting to PostgreSQL via Secrets Manager")
        url = _build_url_from_secret(secret_arn)
        _engine = create_engine(url, pool_size=5, max_overflow=10)

    # Verify connectivity
    with _engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connection verified")

    return _engine


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def close():
    """Dispose of the engine and reset singletons."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
        logger.info("PostgreSQL connection closed")
