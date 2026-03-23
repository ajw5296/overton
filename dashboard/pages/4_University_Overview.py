"""
University Overview Page
Cross-domain aggregate metrics across Penn State.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import load_summary

# Page config
st.set_page_config(
    page_title="University Overview",
    page_icon="🏛️",
    layout="wide"
)

st.title("🏛️ University Overview")
st.markdown("Cross-domain research impact metrics across Penn State")

# Load data
with st.spinner("Loading data..."):
    summary = load_summary()

if not summary:
    st.warning("No data available. Run the pipeline first.")
    st.stop()

df = pd.DataFrame(summary)

# Top-level metrics
st.header("Penn State at a Glance")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Researchers", f"{len(df):,}")
with col2:
    with_policy = len(df[df["policy_documents_total"] > 0])
    st.metric("With Policy Citations", f"{with_policy:,}")
with col3:
    st.metric("Total Policy Docs", f"{df['policy_documents_total'].sum():,}")
with col4:
    st.metric("Avg H-Index", f"{df['h_index'].mean():.1f}")
with col5:
    st.metric("Total Works", f"{df['works_count'].sum():,}")

st.divider()

# Domain breakdown
st.header("Researchers by Domain")

domain_stats = (
    df.groupby("primary_domain")
    .agg(
        researchers=("orcid", "count"),
        with_policy=("policy_documents_total", lambda x: (x > 0).sum()),
        total_policy_docs=("policy_documents_total", "sum"),
        avg_h_index=("h_index", "mean"),
        avg_citations=("cited_by_count", "mean"),
        total_works=("works_count", "sum"),
    )
    .sort_values("researchers", ascending=False)
    .reset_index()
    .rename(columns={"primary_domain": "Domain"})
)

domain_stats["policy_rate"] = (
    domain_stats["with_policy"] / domain_stats["researchers"] * 100
).round(1)

col1, col2 = st.columns(2)

with col1:
    fig = px.bar(
        domain_stats,
        x="Domain",
        y="researchers",
        title="Researchers by Domain",
        color="Domain",
    )
    fig.update_layout(xaxis_tickangle=-45, height=500, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = px.bar(
        domain_stats,
        x="Domain",
        y="policy_rate",
        title="Policy Impact Rate by Domain (%)",
        color="Domain",
    )
    fig.update_layout(
        xaxis_tickangle=-45, height=500, showlegend=False,
        yaxis_title="% of Researchers with Policy Citations"
    )
    st.plotly_chart(fig, use_container_width=True)

# Domain table
st.dataframe(
    domain_stats.style.format({
        "avg_h_index": "{:.1f}",
        "avg_citations": "{:,.0f}",
        "total_works": "{:,}",
        "policy_rate": "{:.1f}%",
    }),
    use_container_width=True,
    hide_index=True,
)

# Field-level breakdown
st.divider()
st.header("Top Fields by Policy Impact")

field_stats = (
    df[df["policy_documents_total"] > 0]
    .groupby("primary_field")
    .agg(
        researchers=("orcid", "count"),
        total_policy_docs=("policy_documents_total", "sum"),
        avg_h_index=("h_index", "mean"),
    )
    .sort_values("total_policy_docs", ascending=False)
    .head(20)
    .reset_index()
    .rename(columns={"primary_field": "Field"})
)

if not field_stats.empty:
    fig = px.bar(
        field_stats,
        x="Field",
        y="total_policy_docs",
        title="Top 20 Fields by Policy Document Citations",
        color="total_policy_docs",
        color_continuous_scale="Blues",
    )
    fig.update_layout(xaxis_tickangle=-45, height=500)
    st.plotly_chart(fig, use_container_width=True)

# Top researchers by policy impact
st.divider()
st.header("Top Researchers by Policy Impact")

top_impact = (
    df[df["policy_documents_total"] > 0]
    .nlargest(25, "policy_documents_total")[
        ["display_name", "primary_field", "primary_domain",
         "policy_documents_total", "h_index", "cited_by_count", "works_count"]
    ]
)
top_impact.columns = ["Name", "Field", "Domain", "Policy Docs",
                       "H-Index", "Citations", "Works"]

st.dataframe(
    top_impact.style.format({
        "Citations": "{:,}",
        "Works": "{:,}",
    }),
    use_container_width=True,
    hide_index=True,
)

# Download full summary
st.divider()
st.download_button(
    label="Download Full Summary as CSV",
    data=df.to_csv(index=False),
    file_name="psu_researchers_summary.csv",
    mime="text/csv"
)
