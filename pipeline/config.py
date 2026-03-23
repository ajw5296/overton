"""Pipeline configuration - API keys, URLs, rate limits, paths."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Directories ===
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "pipeline"
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
OVERTON_DELAY = 0.3  # seconds between requests

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
