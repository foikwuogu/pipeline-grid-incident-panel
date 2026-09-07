"""
Fetch PHMSA pipeline incident/accident data (operator submissions).

Source landing page: https://www.phmsa.dot.gov/data-and-statistics/pipeline/
distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data

PHMSA doesn't expose a single stable bulk-download URL for this dataset — the
landing page links to per-system-type CSV/ZIP files (gas transmission &
gathering, gas distribution, hazardous liquid, LNG, UNGS), and the exact
filenames/versions change as PHMSA republishes. This script scrapes the
landing page for those links rather than hardcoding a filename, so it keeps
working as PHMSA rotates file versions.
"""
from __future__ import annotations
import glob
import io
import os
import re
import zipfile
import requests
import pandas as pd

LANDING_PAGE = (
    "https://www.phmsa.dot.gov/data-and-statistics/pipeline/"
    "distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data"
)

# Which system types we keep, and the filename keyword used to identify them.
SYSTEM_TYPE_KEYWORDS = {
    "gas_transmission_gathering": ["transmission", "gathering"],
    "gas_distribution": ["distribution"],
    "hazardous_liquid": ["hazardous_liquid", "hazardous liquid", "hl_"],
}

FALLBACK_DATA_LINKS = [
    "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/incident_gas_distribution_jan2010_present.zip",
    "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/incident_gas_transmission_gathering_jan2010_present.zip",
    "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/accident_hazardous_liquid_jan2010_present.zip",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _find_data_links(html: str) -> list[str]:
    hrefs = re.findall(r'href="([^"]+\.(?:csv|zip|xlsx))"', html, flags=re.IGNORECASE)
    return [h if h.startswith("http") else f"https://www.phmsa.dot.gov{h}" for h in hrefs]


def _classify(url: str) -> str | None:
    lower = url.lower()
    for system_type, keywords in SYSTEM_TYPE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return system_type
    return None


def fetch_all(session: requests.Session | None = None) -> dict[str, pd.DataFrame]:
    """Returns {system_type: DataFrame} for each PHMSA incident system type found."""
    session = session or requests.Session()
    session.headers.update(BROWSER_HEADERS)

    try:
        resp = session.get(LANDING_PAGE, timeout=30)
        resp.raise_for_status()
        links = _find_data_links(resp.text)
    except requests.RequestException as exc:
        print(f"WARN: PHMSA landing page fetch failed ({exc}); trying known 2010-present ZIP links.")
        links = FALLBACK_DATA_LINKS

    results: dict[str, list[pd.DataFrame]] = {}
    for url in links:
        system_type = _classify(url)
        if system_type is None:
            continue
        try:
            file_resp = session.get(url, timeout=60)
            file_resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"WARN: could not fetch PHMSA {system_type} file {url}: {exc}")
            continue

        if url.lower().endswith(".zip"):
            _read_zip(file_resp.content, url, system_type, results)
        else:
            df = _read_any(io.BytesIO(file_resp.content), url)
            results.setdefault(system_type, []).append(df)

    if not results:
        results = _load_local_downloads()
        if results:
            loaded = ", ".join(f"{system_type} ({len(frames)} file(s))" for system_type, frames in sorted(results.items()))
            print(f"Using local PHMSA files from data/raw: {loaded}")

    if not results:
        urls = "\n".join(f"  - {url}" for url in FALLBACK_DATA_LINKS)
        raise RuntimeError(
            "PHMSA blocked automated downloads from this network, and no local PHMSA files were found.\n"
            "Download these ZIP files in your browser and place them in data/raw/, then rerun --full:\n"
            f"{urls}"
        )

    return {k: pd.concat(v, ignore_index=True) for k, v in results.items()}


def _read_zip(
    content: bytes,
    name_hint: str,
    system_type: str,
    results: dict[str, list[pd.DataFrame]],
) -> None:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if not lower.endswith((".csv", ".xlsx", ".txt", ".tsv")):
                continue
            if any(skip in lower for skip in ("dictionary", "layout", "readme", "instructions")):
                continue
            with zf.open(name) as f:
                df = _read_any(f, name)
                results.setdefault(system_type, []).append(df)


def _load_local_downloads(raw_dir: str = "data/raw") -> dict[str, list[pd.DataFrame]]:
    results: dict[str, list[pd.DataFrame]] = {}
    patterns = ["*.zip", "*.csv", "*.xlsx", "*.txt", "*.tsv"]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(os.path.join(raw_dir, pattern)))

    for path in sorted(paths):
        name = os.path.basename(path)
        if name.startswith("sample_"):
            continue
        system_type = _classify(name)
        if system_type is None:
            continue
        if path.lower().endswith(".zip"):
            with open(path, "rb") as f:
                _read_zip(f.read(), path, system_type, results)
        else:
            df = _read_any(path, path)
            results.setdefault(system_type, []).append(df)
    return results


def _read_any(fileobj, name_hint: str) -> pd.DataFrame:
    if name_hint.lower().endswith(".xlsx"):
        return pd.read_excel(fileobj)
    if name_hint.lower().endswith((".txt", ".tsv")):
        return pd.read_csv(fileobj, sep="\t", low_memory=False, encoding_errors="replace")
    return pd.read_csv(fileobj, low_memory=False, encoding_errors="replace")


if __name__ == "__main__":
    tables = fetch_all()
    for system_type, df in tables.items():
        print(system_type, df.shape)
        df.to_csv(f"data/raw/phmsa_{system_type}.csv", index=False)
