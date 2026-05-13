"""
Researcher Lookup Page
Search for a researcher and view their full impact profile including
OpenAlex metrics, RMD position data, and Overton policy documents.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import load_summary, load_researchers, get_researcher_by_orcid, get_pdf_presigned_url
from utils.db_connection import get_engine

# Page config
st.set_page_config(
    page_title="Researcher Lookup",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Researcher Lookup")
st.markdown("Search for a researcher to view their full research impact profile")

# Load summary for fast dropdown
with st.spinner("Loading researcher index..."):
    summary = load_summary()

if not summary:
    st.warning("No researcher data available. Run the pipeline first.")
    st.stop()

# Build name -> orcid lookup
name_to_orcid = {r["display_name"]: r["orcid"] for r in summary if r.get("display_name")}
researcher_names = sorted(name_to_orcid.keys())

# Search/select researcher
st.subheader("Select a Researcher")
selected_name = st.selectbox(
    "Type or scroll to find a researcher",
    options=[""] + researcher_names,
    index=0,
    placeholder="Start typing a name..."
)

if not selected_name:
    st.info("Select a researcher from the dropdown above to view their impact profile.")
    st.stop()

# Load full data for the selected researcher
orcid = name_to_orcid[selected_name]
with st.spinner("Loading researcher details..."):
    # Try direct DB lookup first (single SELECT), fall back to loading all
    researcher = get_researcher_by_orcid(orcid)
    if researcher is None:
        all_researchers = load_researchers()
        researcher = get_researcher_by_orcid(all_researchers, orcid)

if not researcher:
    st.error(f"Could not find researcher data for {selected_name}")
    st.stop()

oa = researcher.get("openalex") or {}
rmd = researcher.get("rmd") or {}
topics = oa.get("topics", [])
primary_topic = topics[0] if topics else {}

# Load policy documents from normalized tables. Joins this researcher's
# OpenAlex/RMD DOI list against article_citations → policy_documents.
policy_docs = []
engine = get_engine()
if engine is not None:
    try:
        from sqlalchemy import text
        oa_block = researcher.get("openalex") or {}
        rmd_block = researcher.get("rmd") or {}
        researcher_dois = sorted({
            d.lower() for d in (
                (oa_block.get("works_dois") or []) + (rmd_block.get("dois") or [])
            ) if d
        })
        if researcher_dois:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT DISTINCT pd.policy_document_id, pd.data AS doc_data
                    FROM article_citations ac
                    JOIN policy_documents pd ON pd.policy_document_id = ac.policy_document_id
                    WHERE lower(ac.doi) = ANY(:dois)
                      AND pd.data->>'title' IS NOT NULL
                """), {"dois": researcher_dois}).fetchall()
            policy_docs = [r.doc_data for r in rows]
    except Exception as e:
        st.warning(f"Could not load policy documents: {e}")

# === Researcher Header ===
st.divider()
col1, col2 = st.columns([2, 1])

with col1:
    st.header(researcher.get("display_name", "Unknown"))

    # Position info from RMD if available
    profile = rmd.get("profile") or {}
    if profile.get("title") and profile.get("organization_name"):
        st.markdown(f"**{profile['title']}**, {profile['organization_name']}")
    elif profile.get("organization_name"):
        st.markdown(f"**{profile['organization_name']}**")

    # Research field from OpenAlex
    if primary_topic:
        st.markdown(
            f"**Domain:** {primary_topic.get('domain', 'N/A')} | "
            f"**Field:** {primary_topic.get('field', 'N/A')} | "
            f"**Subfield:** {primary_topic.get('subfield', 'N/A')}"
        )

with col2:
    # `wa:<uid>` synthetic identifiers mean we resolved this researcher via
    # OpenAlex name search, not via a real ORCID in RMD. Show the discovered
    # ORCID if Stage 2 found one, else just the WebAccess ID.
    is_synthetic = orcid.startswith("wa:")
    discovered = researcher.get("discovered_orcid")
    if is_synthetic and discovered:
        st.markdown(
            f"**ORCID:** [{discovered}](https://orcid.org/{discovered}) _(via name search)_  \n"
            f"**WebAccess:** {orcid[3:]}"
        )
    elif is_synthetic:
        st.markdown(f"**WebAccess:** {orcid[3:]} _(no ORCID on file)_")
    else:
        st.markdown(f"**ORCID:** [{orcid}](https://orcid.org/{orcid})")
    st.markdown(
        f"**OpenAlex:** [{researcher.get('openalex_id', 'N/A')}]"
        f"(https://openalex.org/{researcher.get('openalex_id', '')})"
    )
    flags = researcher.get("flags") or {}
    if flags.get("oa_disambiguation_suspect"):
        st.warning(
            "⚠️ This researcher's OpenAlex author record is flagged as "
            "potentially conflated with another author — works list shown is "
            "based on RMD only."
        )
    if profile.get("pure_profile_url"):
        st.markdown(f"**Pure Profile:** [View]({profile['pure_profile_url']})")
    if profile.get("email"):
        st.markdown(f"**Email:** {profile['email']}")

# === OpenAlex Metrics ===
st.divider()
st.subheader("Scholarly Metrics")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Works", f"{oa.get('works_count', 0):,}")
with col2:
    st.metric("Cited By", f"{oa.get('cited_by_count', 0):,}")
with col3:
    st.metric("H-Index", oa.get("h_index", 0))
with col4:
    st.metric("i10-Index", oa.get("i10_index", 0))
with col5:
    st.metric("Policy Documents", len(policy_docs))

# === RMD Additional Info ===
pres_count = rmd.get("presentations_count", 0)
etds_count = rmd.get("etds_count", 0)
if pres_count > 0 or etds_count > 0:
    col1, col2 = st.columns(2)
    with col1:
        if pres_count > 0:
            st.metric("Presentations", pres_count)
    with col2:
        if etds_count > 0:
            st.metric("ETDs Advised", etds_count)

# === Overton Policy Documents ===
if policy_docs:
    st.divider()
    st.subheader("Policy Impact")

    # Stats
    source_types = Counter()
    countries = Counter()
    topics_counter = Counter()
    sdg_counter = Counter()
    years = Counter()

    doc_rows = []
    for doc in policy_docs:
        source = doc.get("source") or {}
        source_types[source.get("type", "Unknown")] += 1
        countries[source.get("country", "Unknown")] += 1
        for t in doc.get("topics", []):
            topics_counter[t] += 1
        for s in doc.get("sdgcategories", []):
            sdg_counter[s] += 1
        published = doc.get("published_on", "")
        if published:
            years[published[:4]] += 1

        # Check for PDF availability
        doc_id = doc.get("policy_document_id", "")
        pdf_link = ""
        if doc_id:
            pdf_url = get_pdf_presigned_url(doc_id)
            if pdf_url:
                pdf_link = pdf_url

        doc_rows.append({
            "Title": doc.get("title", ""),
            "Source": source.get("title", ""),
            "Type": source.get("type", ""),
            "Country": source.get("country", ""),
            "Published": published,
            "URL": doc.get("overton_url", ""),
            "PDF": pdf_link,
        })

    # Summary row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Policy Documents", len(policy_docs))
    with col2:
        st.metric("Countries", len(countries))
    with col3:
        st.metric("Government Documents", source_types.get("government", 0))
    with col4:
        st.metric("Think Tank Documents", source_types.get("think tank", 0))

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        source_df = pd.DataFrame([
            {"Source Type": k, "Count": v} for k, v in source_types.items()
        ])
        if not source_df.empty:
            fig = px.pie(source_df, values="Count", names="Source Type",
                         title="Documents by Source Type",
                         color="Source Type",
                         color_discrete_map={
                             "government": "#1f77b4", "think tank": "#ff7f0e",
                             "igo": "#2ca02c", "other": "#d62728"
                         })
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        country_df = pd.DataFrame([
            {"Country": k, "Count": v} for k, v in countries.most_common(10)
        ])
        if not country_df.empty:
            fig = px.bar(country_df, x="Country", y="Count", title="Top 10 Countries")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    # Timeline
    if years:
        years_df = pd.DataFrame([
            {"Year": k, "Count": v} for k, v in sorted(years.items())
        ])
        fig = px.bar(years_df, x="Year", y="Count", title="Policy Documents by Year")
        st.plotly_chart(fig, use_container_width=True)

    # Topics
    if topics_counter:
        st.subheader("Top Topics")
        topics_df = pd.DataFrame([
            {"Topic": k, "Count": v} for k, v in topics_counter.most_common(15)
        ])
        fig = px.bar(topics_df, x="Count", y="Topic", orientation="h",
                     title="Most Common Topics in Citing Documents")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    # SDGs
    if sdg_counter:
        st.subheader("Sustainable Development Goals")
        sdg_df = pd.DataFrame([
            {"SDG": k, "Count": v} for k, v in sdg_counter.most_common()
        ])
        fig = px.bar(sdg_df, x="Count", y="SDG", orientation="h",
                     title="SDG Categories in Citing Documents")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
        st.plotly_chart(fig, use_container_width=True)

    # Document table
    st.subheader("All Policy Documents")
    docs_df = pd.DataFrame(doc_rows)
    st.dataframe(
        docs_df,
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
            "PDF": st.column_config.LinkColumn("PDF", display_text="View PDF"),
            "Title": st.column_config.TextColumn("Title", width="large"),
        },
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        label="Download Documents as CSV",
        data=docs_df.to_csv(index=False),
        file_name=f"{selected_name.replace(' ', '_')}_policy_documents.csv",
        mime="text/csv"
    )
else:
    st.info("No policy documents found for this researcher.")

# === Bio ===
if profile.get("bio"):
    st.divider()
    st.subheader("Biography")
    st.markdown(profile["bio"])
