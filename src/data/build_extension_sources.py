#!/usr/bin/env python3
"""Build extension datasets for wealth-group and region decomposition."""

from __future__ import annotations

import csv
import io
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from src.settings import load_settings

DFA_ZIP_URL = "https://www.federalreserve.gov/releases/z1/dataviz/download/zips/dfa.zip"
STATES = ["CA", "IL", "TX"]
STATE_NAMES = {"CA": "California", "IL": "Illinois", "TX": "Texas"}

FRED_HPI_IDS = {"CA": "CASTHPI", "IL": "ILSTHPI", "TX": "TXSTHPI", "US": "USSTHPI"}
FRED_PCPI_IDS = {"CA": "CAPCPI", "IL": "ILPCPI", "TX": "TXPCPI"}
FRED_POP_IDS = {"CA": "CAPOP", "IL": "ILPOP", "TX": "TXPOP"}


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8-sig")
        except Exception as exc:  # network-layer transient errors
            last_exc = exc
            if attempt == 5:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch URL after retries: {url}") from last_exc


def _quarter_key(q: str) -> tuple[int, int]:
    year = int(q[:4])
    quarter = int(q[-1])
    return (year, quarter)


def _ensure_dfa_detail_csv(raw_dir: Path, *, allow_network: bool) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "dfa.zip"
    detail_path = raw_dir / "dfa-networth-levels-detail.csv"
    if not zip_path.exists() and not allow_network:
        raise FileNotFoundError(f"Missing pinned DFA archive: {zip_path}")
    if not zip_path.exists():
        zip_path.write_bytes(urllib.request.urlopen(DFA_ZIP_URL, timeout=60).read())
    if not detail_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extract("dfa-networth-levels-detail.csv", raw_dir)
    return detail_path


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_wealth_group_dataset(
    raw_dir: Path, normalized_dir: Path, *, allow_network: bool = False
) -> Path:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    detail_path = _ensure_dfa_detail_csv(raw_dir, allow_network=allow_network)
    rows = _read_csv_dicts(detail_path)

    group_map = {
        "TopPt1": "top10",
        "RemainingTop1": "top10",
        "Next9": "top10",
        "Next40": "middle40",
        "Bottom50": "bottom50",
    }

    agg: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"housing": 0.0, "financial": 0.0, "liquid": 0.0}
    )

    for row in rows:
        category = row["Category"]
        group = group_map.get(category)
        if group is None:
            continue
        quarter = row["Date"].replace(":", "")
        housing = float(row["Real estate"])
        financial = float(row["Financial assets"])
        liquid = float(row["Deposits"]) + float(row["Money market fund shares"])

        bucket = agg[(quarter, group)]
        bucket["housing"] += housing
        bucket["financial"] += financial
        bucket["liquid"] += liquid

    out_path = normalized_dir / "cay_components_wealth_groups_q.csv"
    ordered = sorted(agg.keys(), key=lambda x: (_quarter_key(x[0]), x[1]))
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "quarter",
                "wealth_group",
                "housing_wealth_million_usd",
                "financial_wealth_million_usd",
                "liquid_assets_million_usd",
            ]
        )
        for quarter, group in ordered:
            vals = agg[(quarter, group)]
            writer.writerow(
                [
                    quarter,
                    group,
                    round(vals["housing"], 3),
                    round(vals["financial"], 3),
                    round(vals["liquid"], 3),
                ]
            )
    return out_path


def _fetch_fred_series(
    series_id: str, raw_dir: Path, *, allow_network: bool
) -> list[dict[str, str]]:
    cache_path = raw_dir / f"fred_{series_id}.csv"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8-sig")
    elif allow_network:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        text = _fetch_text(url)
        cache_path.write_text(text, encoding="utf-8")
    else:
        raise FileNotFoundError(f"Missing pinned FRED source: {cache_path}")
    return list(csv.DictReader(io.StringIO(text)))


def _load_national_components(normalized_dir: Path) -> dict[str, dict[str, float]]:
    path = normalized_dir / "cay_components_hnpo_q.csv"
    rows = _read_csv_dicts(path)
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        quarter = row["quarter"]
        try:
            out[quarter] = {
                "housing": float(row["housing_wealth_million_usd"]),
                "financial": float(row["financial_wealth_million_usd"]),
                "liquid": float(row["liquid_assets_million_usd"]),
            }
        except ValueError:
            continue
    return out


def build_regional_proxy_dataset(
    raw_dir: Path, normalized_dir: Path, *, allow_network: bool = False
) -> Path:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    national = _load_national_components(normalized_dir)
    quarters = [
        q
        for q in sorted(national.keys(), key=_quarter_key)
        if _quarter_key(q) >= (1989, 3)
    ]

    hpi_q: dict[str, dict[str, float]] = {s: {} for s in list(STATES) + ["US"]}
    for state_or_us, series_id in FRED_HPI_IDS.items():
        rows = _fetch_fred_series(series_id, raw_dir, allow_network=allow_network)
        for row in rows:
            date = row["observation_date"]
            value = row[series_id]
            if value == ".":
                continue
            year, month, _ = date.split("-")
            q_num = (int(month) - 1) // 3 + 1
            q = f"{year}Q{q_num}"
            hpi_q[state_or_us][q] = float(value)

    pcpi_y: dict[str, dict[int, float]] = {s: {} for s in STATES}
    pop_y: dict[str, dict[int, float]] = {s: {} for s in STATES}
    for state, series_id in FRED_PCPI_IDS.items():
        for row in _fetch_fred_series(series_id, raw_dir, allow_network=allow_network):
            value = row[series_id]
            if value == ".":
                continue
            year = int(row["observation_date"][:4])
            pcpi_y[state][year] = float(value)
    for state, series_id in FRED_POP_IDS.items():
        for row in _fetch_fred_series(series_id, raw_dir, allow_network=allow_network):
            value = row[series_id]
            if value == ".":
                continue
            year = int(row["observation_date"][:4])
            pop_y[state][year] = float(value)

    fdic: dict[tuple[int, str], float] = {}

    out_rows: list[list[object]] = []
    for q in quarters:
        year = int(q[:4])
        if any(q not in hpi_q[s] for s in STATES) or q not in hpi_q["US"]:
            continue
        if any(year not in pcpi_y[s] or year not in pop_y[s] for s in STATES):
            continue

        income = {s: pcpi_y[s][year] * pop_y[s][year] for s in STATES}
        income_total = sum(income.values())
        if income_total == 0:
            continue
        financial_share = {s: income[s] / income_total for s in STATES}

        pop_total = sum(pop_y[s][year] for s in STATES)
        housing_raw = {}
        for s in STATES:
            pop_share = pop_y[s][year] / pop_total
            housing_raw[s] = pop_share * (hpi_q[s][q] / hpi_q["US"][q])
        housing_total = sum(housing_raw.values())
        if housing_total == 0:
            continue
        housing_share = {s: housing_raw[s] / housing_total for s in STATES}

        has_fdic = all((year, s) in fdic for s in STATES)
        if has_fdic:
            liquid_total = sum(fdic[(year, s)] for s in STATES)
            liquid_share = {s: fdic[(year, s)] / liquid_total for s in STATES}
            liquid_source = "fdic_state_branch_deposits_annual"
        else:
            liquid_share = financial_share.copy()
            liquid_source = "income_share_fallback"

        nat = national[q]
        for s in STATES:
            out_rows.append(
                [
                    q,
                    STATE_NAMES[s],
                    round(housing_share[s], 6),
                    round(financial_share[s], 6),
                    round(liquid_share[s], 6),
                    round(nat["housing"] * housing_share[s], 3),
                    round(nat["financial"] * financial_share[s], 3),
                    round(nat["liquid"] * liquid_share[s], 3),
                    liquid_source,
                ]
            )

    out_path = normalized_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "quarter",
                "region",
                "housing_share_within_ca_il_tx",
                "financial_share_within_ca_il_tx",
                "liquid_share_within_ca_il_tx",
                "housing_proxy_scaled_million_usd",
                "financial_proxy_scaled_million_usd",
                "liquid_proxy_scaled_million_usd",
                "liquid_share_source",
            ]
        )
        writer.writerows(out_rows)

    method_path = normalized_dir / "region_proxy_method.csv"
    with method_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dimension", "method", "source"])
        writer.writerow(
            [
                "housing",
                "Within-CA/IL/TX share = population share x (state HPI / US HPI), then normalized",
                "FRED CASTHPI, ILSTHPI, TXSTHPI, USSTHPI; CAPOP, ILPOP, TXPOP",
            ]
        )
        writer.writerow(
            [
                "financial",
                "Within-CA/IL/TX share = state estimated personal income share (PCPI x population)",
                "FRED CAPCPI, ILPCPI, TXPCPI; CAPOP, ILPOP, TXPOP",
            ]
        )
        writer.writerow(
            [
                "liquid",
                "Within-CA/IL/TX share = financial share (income-based) in this build; optional FDIC deposit override supported via fdic_state_deposits_annual_ca_il_tx.csv",
                "FRED CAPCPI, ILPCPI, TXPCPI; CAPOP, ILPOP, TXPOP",
            ]
        )
        writer.writerow(
            [
                "scaled proxies",
                "State proxy levels scale national HNPO quarterly components by within-three-state shares for comparative analysis",
                "National base: cay_components_hnpo_q.csv",
            ]
        )
    return out_path


def main() -> None:
    settings = load_settings([])
    allow_network = settings.extension_acquisition_mode == "latest"
    print(
        build_wealth_group_dataset(
            settings.extension_raw_dir,
            settings.extension_normalized_dir,
            allow_network=allow_network,
        )
    )
    print(
        build_regional_proxy_dataset(
            settings.extension_raw_dir,
            settings.extension_normalized_dir,
            allow_network=allow_network,
        )
    )


if __name__ == "__main__":
    main()
