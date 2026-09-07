"""Streamlit dashboard for the PHMSA + OE-417 unified output."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components


DATA_PATH = Path("output/phmsa_oe417_unified.csv")


@st.cache_data(show_spinner=False)
def load_data(path: Path, modified_at: float) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce")
    df["customers_affected"] = pd.to_numeric(df.get("customers_affected"), errors="coerce").fillna(0)
    df["type_of_disturbance"] = df.get("type_of_disturbance", df.get("cause_text", "Unknown")).fillna("Unknown")
    return df


st.set_page_config(page_title="PHMSA + OE-417 Dashboard", layout="wide")

st.title("PHMSA + OE-417 Dashboard")

if not DATA_PATH.exists():
    st.error("Run `python src/pipeline.py --full --start-year 2010` before opening the dashboard.")
    st.stop()

auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
if auto_refresh:
    components.html("<script>setTimeout(() => window.parent.location.reload(), 30000)</script>", height=0)

data_modified_at = DATA_PATH.stat().st_mtime
df = load_data(DATA_PATH, data_modified_at)
st.sidebar.caption(f"Data file: {DATA_PATH}")

source_options = sorted(df["source_system"].dropna().unique())
selected_sources = st.sidebar.multiselect("Source", source_options, default=source_options)
filtered = df[df["source_system"].isin(selected_sources)] if selected_sources else df.iloc[0:0]

metric_cols = st.columns(4)
metric_cols[0].metric("Total Incidents", f"{len(filtered):,}")
metric_cols[1].metric("PHMSA", f"{(filtered['source_system'] == 'PHMSA').sum():,}")
metric_cols[2].metric("OE-417", f"{(filtered['source_system'] == 'OE-417').sum():,}")
metric_cols[3].metric("Control/Telecom", f"{filtered['control_or_telecom_involved'].fillna(False).sum():,}")

yearly = filtered.dropna(subset=["year"]).groupby("year", as_index=False).size()
yearly.columns = ["year", "incidents"]
yearly["year"] = yearly["year"].astype(int)

st.subheader("Total Incidents per Year")
st.plotly_chart(px.bar(yearly, x="year", y="incidents", color="incidents"), use_container_width=True)

affected = filtered.dropna(subset=["year"]).groupby("year", as_index=False)["customers_affected"].sum()
affected["year"] = affected["year"].astype(int)

st.subheader("Customers Affected per Year")
st.plotly_chart(px.line(affected, x="year", y="customers_affected", markers=True), use_container_width=True)

types = filtered["type_of_disturbance"].value_counts().head(20).reset_index()
types.columns = ["type", "count"]

st.subheader("Distribution of Disturbance Types")
st.plotly_chart(px.pie(types, names="type", values="count"), use_container_width=True)

categories = filtered["control_telecom_categories"].value_counts().reset_index()
categories.columns = ["category", "count"]

st.subheader("Control-System / Telecom Classification")
st.plotly_chart(px.bar(categories, x="count", y="category", orientation="h"), use_container_width=True)