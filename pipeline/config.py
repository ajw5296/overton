"""Pipeline configuration - API keys, URLs, rate limits, paths."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Directories ===
PROJECT_ROOT = Path(__file__).parent.parent
IS_LAMBDA = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DATA_DIR = Path("/tmp/pipeline") if IS_LAMBDA else PROJECT_ROOT / "data" / "pipeline"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"

# === OpenAlex ===
OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "mail@example.com")
PSU_ROR = "https://ror.org/04p491231"
OPENALEX_DELAY = 0.1  # seconds between requests

# === RMD (PSU Researcher Metadata Database) ===
RMD_BASE_URL = "https://metadata.libraries.psu.edu/v1"
RMD_API_KEY = os.getenv("PSU_RESEARCH_API_KEY", "")
RMD_DELAY = 0.5  # seconds between requests

# === Overton ===
OVERTON_ARTICLES_URL = "https://app.overton.io/articles.php"
OVERTON_DOCUMENTS_URL = "https://app.overton.io/documents.php"
OVERTON_API_KEY = os.getenv("OVERTON_API_KEY", "")
OVERTON_DELAY = 0.2  # seconds between requests (50 calls/sec across 10 concurrent workers)

# === Output filenames ===
OPENALEX_OUTPUT = "01_researchers_openalex.json"
RMD_OUTPUT = "02_researchers_rmd.json"
OVERTON_OUTPUT = "03_researchers_overton.json"
FINAL_OUTPUT = "researchers.json"
SUMMARY_OUTPUT = "researchers_summary.json"
POLICY_DOCS_FLAT_OUTPUT = "policy_documents_flat.json"
ORCID_WEBACCESS_MAP = "orcid_webaccess_map.json"
RUN_METADATA = "run_metadata.json"

# === Incremental update settings ===
INCREMENTAL_SKIP_DAYS = 7  # skip records fetched within this many days

# === Database (RDS PostgreSQL) ===
DATABASE_SECRET_NAME = os.getenv("DATABASE_SECRET_ARN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")  # for local dev: postgresql+psycopg2://user:pass@host/db

# === S3 Data Lake ===
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
S3_RAW_PREFIX = os.getenv("S3_RAW_PREFIX", "raw-api-responses")
S3_PDF_PREFIX = os.getenv("S3_PDF_PREFIX", "policy-documents")

# === Document download settings ===
MAX_PDF_SIZE_MB = 50
PDF_DOWNLOAD_DELAY = 1.0  # seconds between downloads
PDF_DOWNLOAD_TIMEOUT = 120  # seconds per download
