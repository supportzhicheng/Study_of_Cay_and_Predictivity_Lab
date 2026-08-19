#!/usr/bin/env python3
"""Build cay decomposition component series from FRB Z.1 package data."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_HOUSEHOLDS_PATH = ROOT / "raw" / "FRB_Z1_S14_b_Q.csv"
RAW_HNPO_PATH = ROOT / "raw" / "FRB_Z1_S1M_b_Q.csv"
OUT_COMPONENTS_HOUSEHOLDS = ROOT / "cay_components_households_q.csv"
OUT_COMPONENTS_HNPO = ROOT / "cay_components_hnpo_q.csv"
OUT_METADATA = ROOT / "series_metadata.csv"

HH_HOUSING_CODE = "LM155035015.Q"
HH_FINANCIAL_CODE = "FL194090005.Q"
HH_CHECKABLE_CODE = "FL193020005.Q"
HH_DEPOSITS_CODE = "FL193030205.Q"
HH_MMF_CODE = "FL193034005.Q"

HNPO_HOUSING_CODE = "LM155035005.Q"
HNPO_FINANCIAL_CODE = "FL154090005.Q"
HNPO_CHECKABLE_CODE = "FL153020005.Q"
HNPO_DEPOSITS_CODE = "FL153030005.Q"
HNPO_MMF_CODE = "FL153034005.Q"


def _to_float(value: str) -> float | None:
    value = value.strip()
    if value == "":
        return None
    return float(value)


def _read_series(path: Path) -> tuple[list[str], dict[str, list[float | None]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    quarters = header[6:]
    series: dict[str, list[float | None]] = {}

    for row in rows[1:]:
        if len(row) < 7:
            continue
        series_code = row[5].strip()
        values = [_to_float(x) for x in row[6:]]
        series[series_code] = values

    return quarters, series


def _check_required(series: dict[str, list[float | None]], required: list[str]) -> None:
    missing = [code for code in required if code not in series]
    if missing:
        raise RuntimeError(f"Missing required series in raw file: {missing}")


def _write_components(
    quarters: list[str],
    series: dict[str, list[float | None]],
    out_path: Path,
    housing_code: str,
    financial_code: str,
    checkable_code: str,
    deposits_code: str,
    mmf_code: str,
) -> None:
    housing = series[housing_code]
    financial = series[financial_code]
    checkable = series[checkable_code]
    deposits = series[deposits_code]
    mmf = series[mmf_code]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "quarter",
                "housing_wealth_million_usd",
                "financial_wealth_million_usd",
                "liquid_assets_million_usd",
            ]
        )

        for i, quarter in enumerate(quarters):
            h = housing[i]
            fin = financial[i]
            liq_parts = (checkable[i], deposits[i], mmf[i])
            liq = None if any(x is None for x in liq_parts) else sum(liq_parts)  # type: ignore[arg-type]

            writer.writerow(
                [
                    quarter,
                    "" if h is None else int(h) if h.is_integer() else h,
                    "" if fin is None else int(fin) if fin.is_integer() else fin,
                    "" if liq is None else int(liq) if liq.is_integer() else liq,
                ]
            )


def _write_metadata(out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dataset",
                "component",
                "source_table",
                "series_code",
                "construction",
                "unit",
                "frequency",
            ]
        )
        writer.writerow(
            [
                "households",
                "housing_wealth",
                "S14.b (Balance Sheet of Households)",
                HH_HOUSING_CODE,
                "Direct series",
                "Million USD",
                "Quarterly",
            ]
        )
        writer.writerow(
            [
                "households",
                "financial_wealth",
                "S14.b (Balance Sheet of Households)",
                HH_FINANCIAL_CODE,
                "Direct series",
                "Million USD",
                "Quarterly",
            ]
        )
        writer.writerow(
            [
                "households",
                "liquid_assets",
                "S14.b (Balance Sheet of Households)",
                f"{HH_CHECKABLE_CODE} + {HH_DEPOSITS_CODE} + {HH_MMF_CODE}",
                "Sum of checkable deposits & currency, other deposits incl. time/savings, and money market fund shares",
                "Million USD",
                "Quarterly",
            ]
        )
        writer.writerow(
            [
                "households_and_nonprofits",
                "housing_wealth",
                "S1M.b (Balance Sheet of Households and Nonprofit Organizations)",
                HNPO_HOUSING_CODE,
                "Direct series",
                "Million USD",
                "Quarterly",
            ]
        )
        writer.writerow(
            [
                "households_and_nonprofits",
                "financial_wealth",
                "S1M.b (Balance Sheet of Households and Nonprofit Organizations)",
                HNPO_FINANCIAL_CODE,
                "Direct series",
                "Million USD",
                "Quarterly",
            ]
        )
        writer.writerow(
            [
                "households_and_nonprofits",
                "liquid_assets",
                "S1M.b (Balance Sheet of Households and Nonprofit Organizations)",
                f"{HNPO_CHECKABLE_CODE} + {HNPO_DEPOSITS_CODE} + {HNPO_MMF_CODE}",
                "Sum of checkable deposits & currency, time/savings deposits, and money market fund shares",
                "Million USD",
                "Quarterly",
            ]
        )


def main() -> None:
    if not RAW_HOUSEHOLDS_PATH.exists():
        raise FileNotFoundError(f"Raw input file not found: {RAW_HOUSEHOLDS_PATH}")
    if not RAW_HNPO_PATH.exists():
        raise FileNotFoundError(f"Raw input file not found: {RAW_HNPO_PATH}")

    hh_quarters, hh_series = _read_series(RAW_HOUSEHOLDS_PATH)
    _check_required(
        hh_series,
        [
            HH_HOUSING_CODE,
            HH_FINANCIAL_CODE,
            HH_CHECKABLE_CODE,
            HH_DEPOSITS_CODE,
            HH_MMF_CODE,
        ],
    )
    _write_components(
        hh_quarters,
        hh_series,
        OUT_COMPONENTS_HOUSEHOLDS,
        HH_HOUSING_CODE,
        HH_FINANCIAL_CODE,
        HH_CHECKABLE_CODE,
        HH_DEPOSITS_CODE,
        HH_MMF_CODE,
    )

    hnpo_quarters, hnpo_series = _read_series(RAW_HNPO_PATH)
    _check_required(
        hnpo_series,
        [
            HNPO_HOUSING_CODE,
            HNPO_FINANCIAL_CODE,
            HNPO_CHECKABLE_CODE,
            HNPO_DEPOSITS_CODE,
            HNPO_MMF_CODE,
        ],
    )
    _write_components(
        hnpo_quarters,
        hnpo_series,
        OUT_COMPONENTS_HNPO,
        HNPO_HOUSING_CODE,
        HNPO_FINANCIAL_CODE,
        HNPO_CHECKABLE_CODE,
        HNPO_DEPOSITS_CODE,
        HNPO_MMF_CODE,
    )

    _write_metadata(OUT_METADATA)


if __name__ == "__main__":
    main()
