"""
Orchestrates: fetch PHMSA + OE-417 -> harmonize -> classify -> write versioned
output + manifest.

Usage:
    python src/pipeline.py --full --start-year 2010 --version v1.0
    python src/pipeline.py --demo            # uses data/raw/sample_* fixtures only
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, redirect_stdout
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import fetch_phmsa
import fetch_oe417
import harmonize
import join as join_mod


OUTPUT_DIR = Path("output")
LOG_DIR = OUTPUT_DIR / "logs"
OUTPUT_CSV = OUTPUT_DIR / "phmsa_oe417_unified.csv"
PROVENANCE_JSON = OUTPUT_DIR / "provenance.json"
FETCH_LOG = LOG_DIR / "fetch.log"
JOIN_LOG = LOG_DIR / "join.log"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


@contextmanager
def _tee_stdout(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as log_file:
        with redirect_stdout(_Tee(sys.stdout, log_file)):
            yield


def run_full(version: str, start_year: int) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with _tee_stdout(FETCH_LOG):
        print("Fetching PHMSA incident tables...")
        phmsa_tables = fetch_phmsa.fetch_all()

        print(f"Fetching DOE OE-417 data from {start_year} onward...")
        oe417_raw = fetch_oe417.fetch_all(start_year=start_year)

    with _tee_stdout(JOIN_LOG):
        print("Harmonizing and joining PHMSA + OE-417 records...")
        phmsa_harmonized = harmonize.harmonize_phmsa(phmsa_tables)
        oe417_harmonized = harmonize.harmonize_oe417(oe417_raw)
        panel = harmonize.union(phmsa_harmonized, oe417_harmonized)

        _finish(panel, version, start_year, mode="full")


def run_demo(version: str) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with _tee_stdout(FETCH_LOG):
        print("Running in --demo mode: using fixtures in data/raw/sample_*, no network calls.")
        phmsa_transmission = pd.read_csv("data/raw/sample_phmsa_gas_transmission_gathering.csv")
        phmsa_distribution = pd.read_csv("data/raw/sample_phmsa_gas_distribution.csv")
        oe417_raw = pd.read_csv("data/raw/sample_oe417.csv")

    phmsa_tables = {
        "gas_transmission_gathering": phmsa_transmission,
        "gas_distribution": phmsa_distribution,
    }

    with _tee_stdout(JOIN_LOG):
        print("Harmonizing and joining PHMSA + OE-417 records...")
        phmsa_harmonized = harmonize.harmonize_phmsa(phmsa_tables)
        oe417_harmonized = harmonize.harmonize_oe417(oe417_raw)
        panel = harmonize.union(phmsa_harmonized, oe417_harmonized)

        _finish(panel, version, start_year=2010, mode="demo")


def _finish(panel: pd.DataFrame, version: str, start_year: int, mode: str) -> None:
    config = join_mod.load_yaml("config/control_system_telecom_classification.yaml")
    panel = join_mod.apply_classification(panel, config)

    OUTPUT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUTPUT_CSV, index=False)
    generated_at_utc = datetime.now(timezone.utc).isoformat()
    row_count_by_source = panel["source_system"].value_counts().to_dict()

    manifest = {
        "title": "PHMSA + OE-417 Unified Incident Dataset",
        "description": "A harmonized dataset combining PHMSA pipeline incidents and DOE OE-417 electric disturbance events. Includes unified schema, classification labels, provenance, and source URLs.",
        "dataset_version": version,
        "version": version,
        "upload_type": "dataset",
        "run_mode": mode,
        "start_year": start_year,
        "generated_at_utc": generated_at_utc,
        "row_count": len(panel),
        "row_count_by_source": row_count_by_source,
        "creators": [
            {
                "name": "Friday Ogochukwu Ikwuogu",
                "orcid": "0009-0009-2222-1318",
                "affiliation": "Independent Researcher, Odessa, Texas, USA",
            }
        ],
        "keywords": [
            "PHMSA",
            "OE-417",
            "Pipeline Safety",
            "Electric Disturbance",
            "Critical Infrastructure",
            "SCADA",
            "Telemetry",
            "Cyber Events",
            "Telecom Outages",
        ],
        "sources": {
            "phmsa": [
                "https://www.phmsa.dot.gov/",
                "https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data",
            ],
            "oe417": [
                "https://www.oe.netl.doe.gov/",
                "https://www.oe.netl.doe.gov/OE417_annual_summary.aspx",
                "https://www.oe.netl.doe.gov/docs/OE417_<YEAR>.xls",
            ],
        },
        "provenance": {
            "start_year": start_year,
            "generated_on": generated_at_utc[:10],
            "sources": {
                "phmsa": [
                    "https://www.phmsa.dot.gov/",
                    "https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data",
                ],
                "oe417": [
                    "https://www.oe.netl.doe.gov/",
                    "https://www.oe.netl.doe.gov/docs/OE417_<YEAR>.xls",
                ],
            },
            "fetch_timestamps": {
                "phmsa": generated_at_utc,
                "oe417": generated_at_utc,
            },
            "row_counts": {
                "phmsa": int(row_count_by_source.get("PHMSA", 0)),
                "oe417": int(row_count_by_source.get("OE-417", 0)),
                "combined": len(panel),
            },
        },
        "files": [
            str(OUTPUT_CSV).replace("\\", "/"),
            str(PROVENANCE_JSON).replace("\\", "/"),
            str(FETCH_LOG).replace("\\", "/"),
            str(JOIN_LOG).replace("\\", "/"),
            "config/control_system_telecom_classification.yaml",
        ],
        "contacts": {
            "google_scholar": "https://scholar.google.com/citations?pli=1&authuser=3&user=XADxRNkAAAAJ",
            "researchgate": "https://www.researchgate.net/profile/Friday-O-Ikwuogu/research",
            "github": "https://github.com/foikwuogu",
            "portfolio": "Ikwuogufoikwuogu.github.io",
            "linkedin": "Ogochukwu Friday Ikwuogu",
            "email": "Friday.ikwuogu@gmail.com|ikwuogu_f57913@utpb.edu | ogochukwu.f.ikwuogu@ieee.org",
        },
        "author": "Friday Ogochukwu Ikwuogu (ORCID 0009-0009-2222-1318)",
        "license": "CC BY",
        "note_if_demo": "Fixture-only run — NOT the real dataset. Re-run with --full on a networked machine." if mode == "demo" else None,
        "note_on_scoping": "start_year reflects the Dec 18, 2026 scoping decision (1986 vs 2010 onward) — confirm this matches the final decision before release.",
    }
    with open(PROVENANCE_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {OUTPUT_CSV} ({len(panel)} rows)")
    print(f"Wrote {PROVENANCE_JSON}")
    print(f"Wrote {FETCH_LOG}")
    print(f"Wrote {JOIN_LOG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Fetch live data from PHMSA and OE-417")
    parser.add_argument("--demo", action="store_true", help="Use bundled fixtures only, no network")
    parser.add_argument("--start-year", type=int, default=2010, help="1986 or 2010 per the Dec 18, 2026 scoping decision")
    parser.add_argument("--version", default="v1.0")
    args = parser.parse_args()

    try:
        if args.full:
            run_full(args.version, args.start_year)
        elif args.demo:
            run_demo(args.version)
        else:
            parser.error("Pass --full (live fetch) or --demo (fixtures only).")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
