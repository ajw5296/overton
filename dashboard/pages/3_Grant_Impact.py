"""
Grant Impact Analysis Page
Explore grant funding and its relationship to policy impact.
Currently limited to HHD researchers with RMD data.
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
    page_title="Grant Impact",
    page_icon="💰",
    layout="wide"
)

st.title("💰 Grant Impact Analysis")
st.markdown("Exploring grant funding and its relationship to policy impact")

# Load data
with st.spinner("Loading data..."):
    summary = load_summary()

if not summary:
    st.warning("No data available. Run the pipeline first.")
    st.stop()

# Filter to researchers with grants
researchers_with_grants = [r for r in summary if r.get("grants_count", 0) > 0]

if not researchers_with_grants:
    st.info("No grant data available yet. Grant data comes from the PSU RMD API (currently HHD college only).")
    st.stop()

df = pd.DataFrame(researchers_with_grants)

# Summary metrics
st.header("Summary")
col1, col2, col3, col4 = st.columns(4)

total_dollars = df["total_grant_dollars"].sum()
total_grants = df["grants_count"].sum()
with_policy = len(df[df["policy_documents_total"] > 0])

with col1:
    st.metric("Researchers with Grants", len(df))
with col2:
    st.metric("Total Grants", int(total_grants))
with col3:
    st.metric("Total Funding", f"${total_dollars:,.0f}")
with col4:
    st.metric("Also Have Policy Citations", with_policy)

st.divider()

# Grants by organization/subfield
st.header("Funding by Research Area")

org_funding = (
    df.groupby("rmd_org")
    .agg(
        total_funding=("total_grant_dollars", "sum"),
        num_grants=("grants_count", "sum"),
        researchers=("orcid", "count"),
        policy_docs=("policy_documents_total", "sum"),
    )
    .sort_values("total_funding", ascending=False)
    .reset_index()
    .rename(columns={"rmd_org": "Department"})
)

if not org_funding.empty:
    fig = px.bar(
        org_funding,
        x="Department",
        y="total_funding",
        title="Total Grant Funding by Department",
        labels={"total_funding": "Total Funding ($)"},
    )
    fig.update_layout(xaxis_tickangle=-45, height=500)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        org_funding.style.format({
            "total_funding": "${:,.0f}",
            "num_grants": "{:.0f}",
            "researchers": "{:.0f}",
            "policy_docs": "{:.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

# Scatter: grants vs policy impact
st.header("Grants vs Policy Impact")
st.markdown("Each dot is a researcher. Size indicates number of grants.")

scatter_df = df[df["policy_documents_total"] > 0].copy()
if not scatter_df.empty:
    fig = px.scatter(
        scatter_df,
        x="total_grant_dollars",
        y="policy_documents_total",
        size="grants_count",
        hover_name="display_name",
        color="primary_domain",
        title="Grant Funding vs Policy Document Citations",
        labels={
            "total_grant_dollars": "Total Grant Funding ($)",
            "policy_documents_total": "Policy Documents",
            "primary_domain": "Domain",
        },
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No researchers with both grants and policy citations found.")

# Top funded researchers
st.header("Top Funded Researchers")
top_funded = df.nlargest(20, "total_grant_dollars")[
    ["display_name", "rmd_org", "grants_count", "total_grant_dollars",
     "policy_documents_total", "h_index"]
]
top_funded.columns = ["Name", "Department", "Grants", "Total Funding",
                       "Policy Docs", "H-Index"]

st.dataframe(
    top_funded.style.format({
        "Total Funding": "${:,.0f}",
    }),
    use_container_width=True,
    hide_index=True,
)
