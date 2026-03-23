"""Centralized data loading for the dashboard with Streamlit caching."""

import json
from pathlib import Path
import streamlit as st

# Data paths - check dashboard/data/ first (Docker), then data/pipeline/ (local dev)
_DASHBOARD_DATA = Path(__file__).parent.parent / "data"
_LOCAL_DATA = Path(__file__).parent.parent.parent / "data" / "pipeline"


def _data_dir() -> Path:
    """Resolve the data directory (Docker vs local dev)."""
    if (_DASHBOARD_DATA / "researchers_summary.json").exists():
        return _DASHBOARD_DATA
    if (_LOCAL_DATA / "researchers_summary.json").exists():
        return _LOCAL_DATA
    # Fallback to dashboard/data even if empty (for error messages)
    return _DASHBOARD_DATA


@st.cache_data
def load_summary() -> list[dict]:
    """Load the lightweight researcher summary index."""
    path = _data_dir() / "researchers_summary.json"
    if not path.exists():
        st.error(f"Summary data not found at {path}. Run the pipeline first.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_researchers() -> list[dict]:
    """Load the full researcher dataset."""
    path = _data_dir() / "researchers.json"
    if not path.exists():
        st.error(f"Researcher data not found at {path}. Run the pipeline first.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_policy_docs_flat() -> list[dict]:
    """Load the flat policy documents for chart pages."""
    path = _data_dir() / "policy_documents_flat.json"
    if not path.exists():
        st.error(f"Policy documents not found at {path}. Run the pipeline first.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_run_metadata() -> dict:
    """Load pipeline run metadata."""
    path = _data_dir() / "run_metadata.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_researcher_by_orcid(researchers: list[dict], orcid: str) -> dict | None:
    """Find a researcher by ORCID."""
    for r in researchers:
        if r.get("orcid") == orcid:
            return r
    return None
