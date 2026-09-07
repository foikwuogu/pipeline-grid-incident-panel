"""
Apply the control-system/telecom classification (config/
control_system_telecom_classification.yaml) to the harmonized incident panel.

Supports: per-category keywords + regex, source_system filtering, incident_id
overrides (single label, wins outright), and keyword-scoped exclusion phrases
(e.g. "radio" as a telecom keyword, but "police radio" doesn't count).
"""
from __future__ import annotations
import re
import yaml
import pandas as pd


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _keyword_is_excluded(keyword: str, text: str, exclude_phrases: list[str]) -> bool:
    """True if every occurrence of `keyword` in `text` sits inside an
    exclude phrase (e.g. keyword 'radio' inside text 'police radio failed')
    is suppressed because 'police radio' is an exclude phrase containing
    'radio'. If the keyword also appears elsewhere outside any exclude
    phrase, it is NOT excluded.
    """
    if keyword not in text:
        return False
    applicable_excludes = [p for p in exclude_phrases if keyword in p]
    if not applicable_excludes:
        return False
    stripped = text
    for phrase in applicable_excludes:
        stripped = stripped.replace(phrase, "")
    return keyword not in stripped


def classify_row(row: pd.Series, config: dict) -> list[str]:
    overrides = {o["incident_id"]: o["label"] for o in config.get("overrides", []) if o.get("incident_id")}

    incident_id = row.get("incident_id")
    if incident_id in overrides:
        return [overrides[incident_id]]

    text = str(row.get("cause_text", "")).lower()
    source_system = row.get("source_system")
    exclude_phrases = [p.lower() for p in config.get("exclude_keywords", [])]

    matched = []
    for pattern_spec in config.get("patterns", []):
        allowed_sources = pattern_spec.get("source_system")
        if allowed_sources and source_system not in allowed_sources:
            continue

        label = pattern_spec["label"]
        hit = False

        for kw in pattern_spec.get("keywords", []):
            kw_lower = kw.lower()
            if kw_lower in text and not _keyword_is_excluded(kw_lower, text, exclude_phrases):
                hit = True
                break

        if not hit:
            for pattern in pattern_spec.get("regex", []):
                if re.search(pattern, text, flags=re.IGNORECASE):
                    hit = True
                    break

        if hit:
            matched.append(label)

    return matched or [config.get("no_match_label", "not control-system/telecom related")]


def apply_classification(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    df = df.copy()
    df["control_telecom_categories"] = [
        ", ".join(classify_row(row, config)) for _, row in df.iterrows()
    ]
    no_match = config.get("no_match_label", "not control-system/telecom related")
    df["control_or_telecom_involved"] = df["control_telecom_categories"].apply(
        lambda cats: cats != no_match
    )
    return df
