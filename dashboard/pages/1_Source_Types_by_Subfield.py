"""
Source Types by Subfield Analysis Page
Uses the flat policy documents data for efficient chart rendering.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import load_policy_docs_flat

# Page config
st.set_page_config(
    page_title="Source Types by Subfield",
    page_icon="📊",
    layout="wide"
)

st.title("Source Types by Subfield")
st.markdown("Analyzing which types of organizations cite research from different academic fields")

# Load data
with st.spinner("Loading data..."):
    flat_docs = load_policy_docs_flat()

if not flat_docs:
    st.warning("No policy document data available. Run the pipeline first.")
    st.stop()

df = pd.DataFrame(flat_docs)
st.success(f"Loaded {len(df):,} policy document citations")

# Sidebar filters
st.sidebar.header("Filters")

# Domain filter
all_domains = sorted(df["primary_domain"].dropna().unique())
selected_domains = st.sidebar.multiselect(
    "Select Domains",
    options=all_domains,
    default=all_domains
)

# Filter by domain first
domain_df = df[df["primary_domain"].isin(selected_domains)]

# Subfield filter (filtered by domain selection)
all_subfields = sorted(domain_df["primary_subfield"].dropna().unique())
selected_subfields = st.sidebar.multiselect(
    "Select Subfields",
    options=all_subfields,
    default=all_subfields
)

# Apply subfield filter
filtered_df = domain_df[domain_df["primary_subfield"].isin(selected_subfields)]

# Summary metrics
st.header("Summary")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Policy Documents", f"{len(filtered_df):,}")
with col2:
    st.metric("Subfields", len(selected_subfields))
with col3:
    gov_count = len(filtered_df[filtered_df["source_type"] == "government"])
    st.metric("Government Citations", f"{gov_count:,}")
with col4:
    tt_count = len(filtered_df[filtered_df["source_type"] == "think tank"])
    st.metric("Think Tank Citations", f"{tt_count:,}")

# Main visualization - stacked bar chart
st.header("Source Types by Subfield")

subfield_counts = (
    filtered_df.groupby(["primary_subfield", "source_type"])
    .size()
    .reset_index(name="Count")
    .rename(columns={"primary_subfield": "Subfield", "source_type": "Source Type"})
)

if not subfield_counts.empty:
    fig = px.bar(
        subfield_counts,
        x="Subfield",
        y="Count",
        color="Source Type",
        title="Policy Document Citations by Subfield and Source Type",
        color_discrete_map={
            "government": "#1f77b4",
            "think tank": "#ff7f0e",
            "igo": "#2ca02c",
            "other": "#d62728"
        }
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        height=600,
        xaxis_title="Research Subfield",
        yaxis_title="Number of Policy Documents"
    )
    st.plotly_chart(fig, use_container_width=True)

# Source type breakdown
st.header("Overall Source Type Distribution")

source_totals = (
    filtered_df.groupby("source_type")
    .size()
    .reset_index(name="Count")
    .rename(columns={"source_type": "Source Type"})
)

if not source_totals.empty:
    fig_pie = px.pie(
        source_totals,
        values="Count",
        names="Source Type",
        title="Distribution of Policy Document Source Types",
        color="Source Type",
        color_discrete_map={
            "government": "#1f77b4",
            "think tank": "#ff7f0e",
            "igo": "#2ca02c",
            "other": "#d62728"
        }
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# Detailed pivot table
st.header("Detailed Data")

pivot_df = pd.crosstab(
    filtered_df["primary_subfield"],
    filtered_df["source_type"],
)
pivot_df["Total"] = pivot_df.sum(axis=1)
pivot_df = pivot_df.sort_values("Total", ascending=False)
pivot_df.index.name = "Subfield"

st.dataframe(pivot_df, use_container_width=True)

st.download_button(
    label="Download Data as CSV",
    data=pivot_df.to_csv(),
    file_name="policy_impact_by_subfield.csv",
    mime="text/csv"
)
