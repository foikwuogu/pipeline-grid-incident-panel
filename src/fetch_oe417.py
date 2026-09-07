"""
Fetch DOE OE-417 Electric Emergency Incident and Disturbance Report data.

Source landing page: https://www.oe.netl.doe.gov/OE417_annual_summary.aspx
Per-year XLS files are linked from this page; earliest year with a usable XLS
is ~2002 (2000-2001 are PDF-only per the page, so no structured data there).

Like the PHMSA fetcher, this scrapes the landing page for .xls/.xlsx links
rather than hardcoding a URL pattern, since DOE's per-year filenames aren't
perfectly consistent across the archive.
"""
from __future__ import annotations
import glob
import io
import os
import re
import requests
import pandas as pd

LANDING_PAGE = "https://www.oe.netl.doe.gov/OE417_annual_summary.aspx"
EARLIEST_USABLE_YEAR = 2002  # 2000-2001 archives are PDF-only, no structured table
LATEST_DIRECT_URL_YEAR = 2025
DIRECT_URL_TEMPLATE = "https://www.oe.netl.doe.gov/docs/OE417_{year}.xls"
REQUEST_TIMEOUT_SECONDS = 10

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _find_year_xls_links(html: str) -> dict[int, str]:
    links = {}
    for href in re.findall(r'href="([^"]+\.xlsx?)"', html, flags=re.IGNORECASE):
        year_match = re.search(r"(19|20)\d{2}", href)
        if not year_match:
            continue
        year = int(year_match.group(0))
        url = href if href.startswith("http") else f"https://www.oe.netl.doe.gov/{href.lstrip('/')}"
        links[year] = url
    return links


def _direct_year_links(start_year: int) -> dict[int, str]:
    return {
        year: DIRECT_URL_TEMPLATE.format(year=year)
        for year in range(max(start_year, EARLIEST_USABLE_YEAR), LATEST_DIRECT_URL_YEAR + 1)
    }


def validate_oe417_urls(urls: list[str], timeout: int = REQUEST_TIMEOUT_SECONDS) -> list[dict[str, object]]:
    results = []
    for url in urls:
        entry: dict[str, object] = {"url": url, "status": None, "ok": False, "content_type": None}
        try:
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, stream=True)
            entry["status"] = response.status_code
            entry["content_type"] = response.headers.get("Content-Type", "")
            entry["ok"] = response.status_code == 200 and (
                "xls" in str(entry["content_type"]).lower() or url.lower().endswith(".xls")
            )
            response.close()
        except Exception as exc:  # noqa: BLE001
            entry["status"] = str(exc)
        results.append(entry)
    return results


def fetch_all(start_year: int = 2010, session: requests.Session | None = None) -> pd.DataFrame:
    session = session or requests.Session()
    session.headers.update(BROWSER_HEADERS)

    effective_start = max(start_year, EARLIEST_USABLE_YEAR)
    year_links: dict[int, str] = {}
    try:
        resp = session.get(LANDING_PAGE, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        year_links = _find_year_xls_links(resp.text)
    except requests.RequestException as exc:
        print(f"WARN: DOE OE-417 landing page fetch failed ({exc}); trying direct annual XLS URLs.")

    direct_links = _direct_year_links(effective_start)
    year_links = {**direct_links, **year_links}

    frames = []
    for year, url in sorted(year_links.items()):
        if year < effective_start:
            continue
        try:
            file_resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            file_resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"WARN: could not fetch OE-417 file for {year}: {exc}")
            if isinstance(exc, (requests.ConnectTimeout, requests.ConnectionError)):
                print("WARN: OE-417 host is not reachable; skipping remaining direct annual URLs and trying local files.")
                break
            continue
        try:
            df = pd.read_excel(io.BytesIO(file_resp.content))
        except Exception as e:  # noqa: BLE001
            print(f"WARN: could not parse OE-417 file for {year}: {e}")
            continue
        df["oe417_source_year"] = year
        frames.append(df)

    if not frames:
        return _load_local_downloads(effective_start)
    return pd.concat(frames, ignore_index=True)


def _load_local_downloads(effective_start: int, raw_dir: str = "data/raw") -> pd.DataFrame:
    combined_csv = os.path.join(raw_dir, "oe417.csv")
    if os.path.exists(combined_csv):
        df = pd.read_csv(combined_csv, low_memory=False, encoding_errors="replace")
        if "oe417_source_year" in df.columns:
            df = df[pd.to_numeric(df["oe417_source_year"], errors="coerce") >= effective_start]
        print(f"Using local OE-417 combined CSV: {combined_csv} ({len(df)} rows from {effective_start} onward)")
        return df

    frames = []
    patterns = ["OE417_*.xls", "OE417_*.xlsx"]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(os.path.join(raw_dir, pattern)))

    for path in sorted(set(paths)):
        name = os.path.basename(path)
        if name.startswith("sample_"):
            continue
        year_match = re.search(r"(19|20)\d{2}", name)
        year = int(year_match.group(0)) if year_match else None
        if year is not None and year < effective_start:
            continue
        try:
            if path.lower().endswith(".csv"):
                df = pd.read_csv(path, low_memory=False, encoding_errors="replace")
            else:
                df = pd.read_excel(path)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not parse local OE-417 file {path}: {exc}")
            continue
        if year is not None:
            df["oe417_source_year"] = year
        frames.append(df)

    if frames:
        print(f"Using local OE-417 annual files from {raw_dir}: {len(frames)} file(s)")
        return pd.concat(frames, ignore_index=True)

    raise RuntimeError(
        "DOE OE-417 could not be fetched from this network, and no local OE-417 files were found.\n"
        f"Place annual OE-417 .xls/.xlsx files for {effective_start} onward in data/raw/, "
        "or place one combined file named oe417.csv.\n"
        f"Valid annual filenames: OE417_{effective_start}.xls through OE417_{LATEST_DIRECT_URL_YEAR}.xls.\n"
        "If oe417.csv is present, the pipeline skips XLS ingestion and uses the combined CSV instead.\n"
        "After placing files, rerun: python src/pipeline.py --full --start-year <1986|2010>"
    )


if __name__ == "__main__":
    import sys
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2010
    df = fetch_all(start_year=start)
    print(df.shape, "rows x cols")
    df.to_csv("data/raw/oe417.csv", index=False)
