"""
PSU Research Impact Dashboard - Home Page
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent to path so utils can be imported
sys.path.insert(0, str(Path(__file__).parent))
from utils.data_loader import load_summary, load_run_metadata

# Page config
st.set_page_config(
    page_title="PSU Research Impact Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 PSU Research Impact Dashboard")
st.markdown("### Analyzing how Penn State research is cited in policy documents")

st.divider()

# Dynamic stats from pipeline data
summary = load_summary()
metadata = load_run_metadata()

if summary:
    total = len(summary)
    with_policy = sum(1 for r in summary if r.get("policy_documents_total", 0) > 0)
    with_rmd = sum(1 for r in summary if r.get("has_rmd"))
    domains = len(set(r.get("primary_domain") or "Unknown" for r in summary))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Researchers", f"{total:,}")
    with col2:
        st.metric("With Policy Citations", f"{with_policy:,}")
    with col3:
        st.metric("With RMD Data", f"{with_rmd:,}")
    with col4:
        st.metric("Research Domains", domains)

    if metadata:
        run_ts = metadata.get("run_timestamp", "Unknown")
        run_status = metadata.get("status")
        caption = f"Last pipeline run: {run_ts}"
        if run_status and run_status != "completed":
            caption += f" (status: {run_status})"
        st.caption(caption)

st.divider()

st.markdown("""
## About This Dashboard

This dashboard analyzes the research impact of Penn State University researchers
using data from three sources:

- **[OpenAlex](https://openalex.org/)** - Scholarly metadata, citations, topics, and researcher profiles
- **[Overton](https://www.overton.io/)** - Citations in policy documents from governments, think tanks, and IGOs
- **[PSU Researcher Metadata Database](https://metadata.libraries.psu.edu/)** - Presentations and institutional data

---

## Pages

Use the sidebar to navigate between pages:

- **Source Types by Subfield** - Analyze which types of organizations cite research from different academic fields
- **Researcher Lookup** - Search for a researcher and view their full impact profile
- **University Overview** - Cross-domain aggregate metrics across Penn State

---

*Data sources: OpenAlex, Overton API, PSU RMD*
""")
