"""Dashboard database connection with graceful fallback.

Returns None if the database is not available, allowing the dashboard
to fall back to flat file loading.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

_engine = None
_initialized = False


def get_engine():
    """Return a SQLAlchemy engine, or None if DB is not configured/available.

    Connection source priority:
    1. DATABASE_URL environment variable (for local dev / testing)
    2. DATABASE_SECRET_ARN environment variable (for AWS deployment)

    Returns None (without raising) if no DB is configured or connection fails.
    """
    global _engine, _initialized

    if _initialized:
        return _engine

    _initialized = True

    try:
        from sqlalchemy import create_engine, text

        database_url = os.getenv("DATABASE_URL")
        if database_url:
            _engine = create_engine(database_url, pool_size=3, max_overflow=5)
        else:
            secret_arn = os.getenv("DATABASE_SECRET_ARN")
            if not secret_arn:
                logger.info("No database configured — using flat file mode")
                return None

            import boto3
            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])
            url = (
                f"postgresql+psycopg2://{secret['username']}:{secret['password']}"
                f"@{secret['host']}:{secret.get('port', 5432)}/{secret.get('dbname', 'overton')}"
            )
            _engine = create_engine(url, pool_size=3, max_overflow=5)

        # Verify connectivity
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("Dashboard connected to PostgreSQL")
        return _engine

    except Exception as e:
        logger.warning("Database not available, falling back to flat files: %s", e)
        _engine = None
        return None
