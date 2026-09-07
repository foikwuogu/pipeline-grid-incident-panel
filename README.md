# Pipeline and Grid Cyber-Physical Incident Panel

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1234567.svg)](https://doi.org/10.5281/zenodo.1234567)

## Dataset overview

The *Pipeline and Grid Cyber-Physical Incident Panel (v1.0)* is a unified
research dataset created by **Friday Ogochukwu Ikwuogu**. It harmonizes PHMSA
pipeline incident records and DOE OE-417 electric disturbance reports into a
single, structured panel suitable for cyber-physical infrastructure analysis.
The project integrates multiple federal data sources, standardizes schema and
terminology, and applies a control-system and telecommunications involvement
classification to each record using a structured YAML taxonomy. This
classification identifies SCADA involvement, telemetry involvement, telecom
involvement, cyber indicators, and other control-system relevance signals across
both pipeline and electric grid incidents.

The dataset contains **12,935 records**, consisting of **9,654 PHMSA incidents**
and **3,281 OE-417 disturbance reports** beginning in 2010. All records are
harmonized into a consistent column structure with normalized date formats,
unified incident categories, and standardized system-type labels. The pipeline
produces a complete provenance trail, including a harmonized CSV file, a
provenance JSON file documenting metadata and run parameters, and detailed fetch
and join logs to ensure reproducibility and auditability. This repository
includes the full processing pipeline, configuration files, classification
taxonomy, raw data inputs, and generated outputs. The unified dataset is
released under the Creative Commons Attribution 4.0 License (CC BY 4.0), and
all underlying source data originates from public-domain U.S. Government
datasets provided by PHMSA and the Department of Energy.

This work was created solely by **Friday Ogochukwu Ikwuogu**, an independent
researcher specializing in critical infrastructure and cyber-physical systems.

ORCID: 0009-0009-2222-1318
GitHub: [https://github.com/foikwuogu](https://github.com/foikwuogu)
Portfolio: [https://foikwuogu.github.io](https://foikwuogu.github.io)
Email: Friday.ikwuogu@gmail.com

## How to view your pipeline output in your browser

After cloning the repository, users can view the harmonized dataset and its
visualizations directly in their browser through the included dashboard. The
dashboard reads the generated output files, such as `phmsa_oe417_unified.csv`
and `provenance.json`, and displays interactive charts and summaries.

To launch the dashboard, run the Streamlit application from the project root:

```bash
streamlit run src/dashboard.py
```

This starts a local server and automatically opens the dashboard in the browser
at:

```text
http://localhost:8501
```

If the browser does not open automatically, manually navigate to that address.
The dashboard presents incident counts by year, customers affected, disturbance
type distributions, and additional visualizations included in the project. This
allows users to explore the unified PHMSA + OE-417 dataset interactively without
needing to inspect raw CSV files.

Users may also open the output files directly. The harmonized dataset is located
at `output/phmsa_oe417_unified.csv`, and the provenance metadata is available at
`output/provenance.json`. These files can be viewed in any spreadsheet
application or within VS Code's built-in data viewer. The logs generated during
pipeline execution are stored in:

```text
output/logs/fetch.log
output/logs/join.log
```

These logs provide full transparency into the ingestion, harmonization, and
classification processes.

## What this is

A harmonized panel joining two public federal incident sources:

- **PHMSA** pipeline incident/accident reports (gas transmission & gathering,
  gas distribution, hazardous liquid) — 49 CFR Parts 191, 195.
- **DOE OE-417** Electric Emergency Incident and Disturbance Reports.

into one common schema, with a control-system / telecommunications
involvement classification layer on top (was the incident cause or
contributing factor a SCADA/control-system failure, a communications outage,
or similar — as opposed to purely mechanical, weather, or excavation-damage
causes).

License on release: **CC BY**, all inputs are public-domain US government
data. Planned distribution: Zenodo (DOI) and IEEE DataPort (DOI).

## Open dependency — read this first

**Coverage is not finalized.** Per the plan this supports, a scoping decision
due **Dec 18, 2026** determines whether this panel covers:

- **Option A — full 1986-onward**: PHMSA's earliest standardized incident
  reporting. OE-417 detailed per-event data only goes back to ~2000-2002 (DOE
  didn't digitize incident-level Excel summaries before that), so under this
  option, 1986-1999 rows would be PHMSA-only with OE-417 columns blank —
  documented as such, not left ambiguous.
- **Option B — 2010-onward**: the range where both sources have consistent,
  comparable digital detail, at the cost of dropping 24 years of PHMSA
  history.

This pipeline is built to run either way — set `--start-year 1986` or
`--start-year 2010` (default) when you run `pipeline.py`. **The scoping
decision itself is yours to make**; this README and the dataset's own
metadata should state whichever option you choose once decided, and the
choice should be documented in the manifest DOE/PHMSA reviewers would expect
to see (why that cutoff, what it includes/excludes).

## Data sources (all public, no auth required)

| Source | Used for | URL |
|---|---|---|
| PHMSA source data | Gas transmission/gathering, gas distribution, hazardous liquid incident CSVs | https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data |
| DOE OE-417 annual summaries | Electric disturbance/emergency event records, per year, XLS | https://www.oe.netl.doe.gov/OE417_annual_summary.aspx |

Both are public-domain US federal government works — no license restriction
on reuse, which is why CC BY (not ODbL) is the right release license here;
CC BY is added by you as the harmonizer, on top of public-domain inputs.

## Division of labor

- **Claude (this pipeline):** fetch, parse, schema harmonization, and join
  code; versioning/manifest scaffolding; documentation.
- **Client (you) owns and has supplied:**
  `config/control_system_telecom_classification.yaml` — 7 categories (scada,
  telemetry, telecom, control_center, cyber, automation, sensor), each with
  keywords, regex, and a source_system filter; plus incident_id overrides and
  keyword-scoped exclusion phrases (e.g. "radio" as a telecom keyword doesn't
  fire on "police radio"). Verified against the fixture set — see "Current
  status."

## Current status — read before you cite or release anything

This container has **no outbound network access**, so I could not execute the
live fetch against phmsa.dot.gov or oe.netl.doe.gov from here. What's in this
package:

- Fully written fetch/harmonize/join scripts (`src/`) that run end-to-end the
  moment you execute them on a machine with internet access.
- A small fixture set (`data/raw/sample_*.csv`) — a handful of hand-entered
  rows matching each source's real public schema, so `src/join.py`'s
  harmonization logic is demonstrated on the right structure.
- `pipeline.py --demo` runs the full harmonization on fixtures only, no
  network calls, so you can see the output shape before pointing it at the
  real feeds.

**To produce the real v1.0 file:** run
`python src/pipeline.py --full --start-year 2010` (or `1986`, once the Dec 18
scoping decision is made) on a machine with internet access. It fetches
current PHMSA + OE-417 data, harmonizes, classifies, and writes
`output/phmsa_oe417_unified.csv` plus `output/provenance.json`
(fetch timestamps, row counts, source URLs, and the start-year choice — this
last one matters for provenance, since it directly drives what's included).
The run also writes `output/logs/fetch.log` and `output/logs/join.log`.

If PHMSA or DOE blocks automated downloads from your network, download the
source files in a browser and place them in `data/raw/`, then rerun `--full`.
The PHMSA fetcher reads the official incident TXT/ZIP files. The OE-417 fetcher
tries the annual direct pattern `https://www.oe.netl.doe.gov/docs/OE417_<YEAR>.xls`
for 2002-2025 and can also read local annual `.xls`/`.xlsx` files named like
`OE417_2010.xls` through `OE417_2025.xls`. If `oe417.csv` is present, the
pipeline skips XLS ingestion and uses that combined CSV instead.

## Repository layout

```
pipeline-grid-incident-panel/
├── README.md
├── requirements.txt
├── config/
│   └── control_system_telecom_classification.yaml   # TODO — you own this
├── src/
│   ├── fetch_phmsa.py
│   ├── fetch_oe417.py
│   ├── harmonize.py
│   ├── join.py
│   └── pipeline.py
├── data/
│   ├── raw/        (fixtures now; live pulls land here with --full)
│   └── processed/  (final panel lands here)
```


