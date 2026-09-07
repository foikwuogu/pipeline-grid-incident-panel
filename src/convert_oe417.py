"""Convert a combined DOE OE-417 workbook into data/raw/oe417.csv.

Expected input by default:
    data/raw/DOE_Electric_Disturbance_Events.xlsx

Output:
    data/raw/oe417.csv
"""
from __future__ import annotations

import argparse
import os
import re
from typing import Any

import pandas as pd


DEFAULT_INPUT = "data/raw/DOE_Electric_Disturbance_Events.xlsx"
DEFAULT_OUTPUT = "data/raw/oe417.csv"


def _clean_name(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return text


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_name(value).lower()).strip()


def _unique_columns(values: list[Any]) -> list[str]:
    counts: dict[str, int] = {}
    columns = []
    for index, value in enumerate(values):
        name = _clean_name(value) or f"Unnamed: {index}"
        count = counts.get(name, 0)
        counts[name] = count + 1
        columns.append(name if count == 0 else f"{name}.{count}")
    return columns


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for row_index, row in raw.iterrows():
        normalized = {_norm(value) for value in row.tolist()}
        has_date = bool({"date", "date event began"} & normalized)
        has_event = bool({"type of disturbance", "event type"} & normalized)
        if has_date and has_event:
            return int(row_index)
    return None


def _first_present(row: pd.Series, candidates: list[str]) -> Any:
    for candidate in candidates:
        if candidate in row.index and not pd.isna(row[candidate]):
            return row[candidate]
    return None


def _read_sheet(path: str, sheet_name: str) -> pd.DataFrame | None:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw)
    if header_row is None:
        print(f"WARN: skipped OE-417 sheet {sheet_name}: no event header row found")
        return None

    data = raw.iloc[header_row + 1 :].copy()
    data.columns = _unique_columns(raw.iloc[header_row].tolist())
    data = data.dropna(how="all")

    year_match = re.search(r"(19|20)\d{2}", str(sheet_name))
    sheet_year = int(year_match.group(0)) if year_match else None
    rows = []
    event_number = 0

    for _, row in data.iterrows():
        event_date = _first_present(row, ["Date Event Began", "Date"])
        event_type = _first_present(row, ["Event Type", "Type of Disturbance"])
        area = _first_present(row, ["Area Affected", "Area", "Geographic Areas"])

        if pd.isna(event_date) or _norm(event_date) in {"", "date", "date time"}:
            continue
        if pd.isna(event_type) and pd.isna(area):
            continue

        event_number += 1
        year = sheet_year or _infer_year(event_date)
        event_id = f"OE417-{year or sheet_name}-{event_number:04d}"
        alert_criteria = _first_present(row, ["Alert Criteria"])
        event_type_text = _clean_name(event_type)
        if alert_criteria is not None and _clean_name(alert_criteria):
            event_type_text = f"{event_type_text}; {_clean_name(alert_criteria)}" if event_type_text else _clean_name(alert_criteria)

        rows.append(
            {
                "Event ID": event_id,
                "Date Event Began": event_date,
                "Time Event Began": _first_present(row, ["Time Event Began", "Time"]),
                "Date of Restoration": _first_present(row, ["Date of Restoration", "Restoration"]),
                "Time of Restoration": _first_present(row, ["Time of Restoration"]),
                "Geographic Areas": area,
                "NERC Region": _first_present(row, ["NERC Region"]),
                "Event Type": event_type_text,
                "Alert Criteria": alert_criteria,
                "Demand Loss (MW)": _first_present(row, ["Demand Loss (MW)", "Loss (megawatts)"]),
                "Number of Customers Affected": _first_present(row, ["Number of Customers Affected", "Number of Customers Affected 1"]),
                "Number of Fatalities": None,
                "Number of Injuries": None,
                "Estimated Cost": None,
                "oe417_source_year": year,
                "oe417_source_sheet": sheet_name,
            }
        )

    return pd.DataFrame(rows)


def _infer_year(value: Any) -> int | None:
    if hasattr(value, "year"):
        return int(value.year)
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def convert_oe417(input_path: str = DEFAULT_INPUT, output_path: str = DEFAULT_OUTPUT) -> pd.DataFrame:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"OE-417 workbook not found: {input_path}")

    workbook = pd.ExcelFile(input_path)
    frames = []
    for sheet_name in workbook.sheet_names:
        frame = _read_sheet(input_path, sheet_name)
        if frame is not None and not frame.empty:
            frames.append(frame)

    if not frames:
        raise RuntimeError(f"No OE-417 event rows were found in {input_path}")

    combined = pd.concat(frames, ignore_index=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    combined.to_csv(output_path, index=False)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert DOE OE-417 workbook to data/raw/oe417.csv")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to DOE_Electric_Disturbance_Events.xlsx")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to write oe417.csv")
    args = parser.parse_args()

    df = convert_oe417(args.input, args.output)
    years = sorted(year for year in df["oe417_source_year"].dropna().unique())
    print(f"Wrote {args.output} ({len(df)} rows, {len(years)} years: {years[0]}-{years[-1]})")


if __name__ == "__main__":
    main()