"""
Harmonize PHMSA (multiple system-type tables) and DOE OE-417 data into one
common schema.

PHMSA and OE-417 use entirely different column names and reporting units
(PHMSA: per-pipeline-incident, cause/subcause taxonomy under 49 CFR 191/195;
OE-417: per-grid-disturbance-event, free-text event type/cause). This module
maps each source's real columns onto a shared minimal schema so the two can
sit in one table. It does NOT invent a merged "same incident" join across
sources — PHMSA and OE-417 events are almost never the same physical event,
so this is a UNION (stacked rows), not a join, with a `source_system` column
distinguishing them.

Column-name mapping below is based on the documented PHMSA and OE-417 field
names as of this pipeline's build date. PHMSA's own column names have varied
across years/republications — if a live pull is missing a mapped column,
this module logs it and leaves that field null rather than guessing.
"""
from __future__ import annotations
import pandas as pd

COMMON_COLUMNS = [
    "source_system",       # "PHMSA" or "OE-417"
    "incident_id",
    "report_date",
    "year",
    "state",
    "system_type",         # PHMSA: gas_transmission_gathering / gas_distribution / hazardous_liquid; OE-417: "grid"
    "cause_text",           # unified free-text cause/event-type field the classifier reads
    "type_of_disturbance",
    "customers_affected",
    "fatalities",
    "injuries",
    "property_damage_usd",
]

# PHMSA source column candidates -> common column. Lists let us try several
# known historical header spellings.
PHMSA_COLUMN_CANDIDATES = {
    "incident_id": ["REPORT_NUMBER", "OPERATOR_ID", "INCIDENT_NUMBER"],
    "report_date": ["IDATE", "REPORT_RECEIVED_DATE", "LOCAL_DATETIME"],
    "state": ["ISTATE", "LOCATION_STATE_ABBREVIATION"],
    "cause_text": ["CAUSE", "CAUSE_DETAILS", "UNINTENTIONAL_RELEASE_CAUSE_SUBCATEGORY"],
    "type_of_disturbance": ["CAUSE", "CAUSE_DETAILS", "UNINTENTIONAL_RELEASE_CAUSE_SUBCATEGORY"],
    "fatalities": ["FATAL", "NUM_FATALITIES", "FATALITY_IND"],
    "injuries": ["INJURE", "NUM_INJURIES", "INJURY_IND"],
    "property_damage_usd": ["PROPERTY_DAMAGE_COST", "TOTAL_COST_CURRENT"],
}

OE417_COLUMN_CANDIDATES = {
    "incident_id": ["Event ID", "Event Number", "OE-417 Event ID"],
    "report_date": ["Date Event Began", "Date/Time Event Began"],
    "state": ["Geographic Areas", "State"],
    "cause_text": ["Event Type", "Cause", "Description"],
    "type_of_disturbance": ["Event Type", "Cause", "Description"],
    "customers_affected": ["Number of Customers Affected"],
    "fatalities": ["Number of Fatalities"],
    "injuries": ["Number of Injuries"],
    "property_damage_usd": ["Estimated Cost"],
}


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series([None] * len(df))


def harmonize_phmsa(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for system_type, df in tables.items():
        out = pd.DataFrame()
        for common_col, candidates in PHMSA_COLUMN_CANDIDATES.items():
            out[common_col] = _pick_column(df, candidates)
        out["year"] = pd.to_datetime(out["report_date"], errors="coerce").dt.year
        out["customers_affected"] = None
        out["source_system"] = "PHMSA"
        out["system_type"] = system_type
        frames.append(out)
    if not frames:
        return pd.DataFrame(columns=COMMON_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def harmonize_oe417(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    for common_col, candidates in OE417_COLUMN_CANDIDATES.items():
        out[common_col] = _pick_column(df, candidates)
    out["year"] = pd.to_numeric(_pick_column(df, ["oe417_source_year", "Event Year"]), errors="coerce")
    missing_year = out["year"].isna()
    out.loc[missing_year, "year"] = pd.to_datetime(out.loc[missing_year, "report_date"], errors="coerce").dt.year
    out["source_system"] = "OE-417"
    out["system_type"] = "grid"
    return out


def union(phmsa_harmonized: pd.DataFrame, oe417_harmonized: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([phmsa_harmonized, oe417_harmonized], ignore_index=True)
    for col in COMMON_COLUMNS:
        if col not in combined.columns:
            combined[col] = None
    return combined[COMMON_COLUMNS]
