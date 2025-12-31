"""
Overton Policy Impact Dashboard
Streamlit application for visualizing research policy impact data.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import json
from pathlib import Path
from collections import defaultdict

# Page config
st.set_page_config(
    page_title="Overton Policy Impact Dashboard",
    page_icon="📊",
    layout="wide"
)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data" / "overton_exports"
POLICY_DOCS_FILE = DATA_DIR / "social_science_overton_policy_documents.json"


@st.cache_data
def load_policy_documents():
    """Load the policy documents JSON file with caching."""
    with open(POLICY_DOCS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_source_types_by_subfield(data):
    """
    Group researchers by their subfield and count the source types
    of policy documents citing their work.
    """
    subfield_source_counts = defaultdict(lambda: defaultdict(int))

    for researcher in data:
        field_info = researcher.get("field_of_research", {})
        subfield = field_info.get("subfield", "Unknown")

        policy_docs = researcher.get("policy_documents", {})
        results = policy_docs.get("results", [])

        for doc in results:
            source = doc.get("source", {})
            source_type = source.get("type", "Unknown")
            subfield_source_counts[subfield][source_type] += 1

    return {subfield: dict(counts) for subfield, counts in subfield_source_counts.items()}


def create_subfield_df(results):
    """Convert results dict to a DataFrame for visualization."""
    rows = []
    for subfield, source_counts in results.items():
        total = sum(source_counts.values())
        for source_type, count in source_counts.items():
            rows.append({
                "Subfield": subfield,
                "Source Type": source_type,
                "Count": count,
                "Total": total,
                "Percentage": (count / total) * 100 if total > 0 else 0
            })
    return pd.DataFrame(rows)


# Main app
st.title("📊 Overton Policy Impact Dashboard")
st.markdown("Analyzing how PSU Social Science research is cited in policy documents")

# Load data
with st.spinner("Loading data..."):
    data = load_policy_documents()
    results = get_source_types_by_subfield(data)

st.success(f"Loaded {len(data)} researchers")

# Convert to DataFrame
df = create_subfield_df(results)

# Sidebar filters
st.sidebar.header("Filters")

# Subfield filter
all_subfields = sorted(df["Subfield"].unique())
selected_subfields = st.sidebar.multiselect(
    "Select Subfields",
    options=all_subfields,
    default=all_subfields
)

# Filter data
filtered_df = df[df["Subfield"].isin(selected_subfields)]

# Summary metrics
st.header("Summary")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Policy Documents", f"{filtered_df['Count'].sum():,}")
with col2:
    st.metric("Subfields", len(selected_subfields))
with col3:
    gov_count = filtered_df[filtered_df["Source Type"] == "government"]["Count"].sum()
    st.metric("Government Citations", f"{gov_count:,}")
with col4:
    tt_count = filtered_df[filtered_df["Source Type"] == "think tank"]["Count"].sum()
    st.metric("Think Tank Citations", f"{tt_count:,}")

# Main visualization
st.header("Source Types by Subfield")

# Aggregate by subfield for bar chart
subfield_totals = filtered_df.groupby(["Subfield", "Source Type"])["Count"].sum().reset_index()

# Stacked bar chart
fig = px.bar(
    subfield_totals,
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

source_totals = filtered_df.groupby("Source Type")["Count"].sum().reset_index()
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

# Detailed table
st.header("Detailed Data")

# Pivot table view
pivot_df = filtered_df.pivot_table(
    index="Subfield",
    columns="Source Type",
    values="Count",
    fill_value=0,
    aggfunc="sum"
)
pivot_df["Total"] = pivot_df.sum(axis=1)
pivot_df = pivot_df.sort_values("Total", ascending=False)

st.dataframe(pivot_df, use_container_width=True)

# Download option
st.download_button(
    label="Download Data as CSV",
    data=pivot_df.to_csv(),
    file_name="policy_impact_by_subfield.csv",
    mime="text/csv"
)
