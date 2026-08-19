"""Build normalized quarterly sources from acquired raw caches."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from src.data.cache import CachePaths, write_normalized_cache
from src.data.normalize_sources import (
    build_core_macro,
    build_crsp_market,
    build_rates,
    build_shiller_market,
    quarterly_last,
    quarterly_log_inflation,
    quarterly_max,
    quarterly_mean,
)
from src.settings import load_settings

RAW_FILES = {
    "bea": Path("bea/bea_components.parquet"),
    "fred": Path("fred/fred_inputs.parquet"),
    "crsp_market": Path("wrds/crsp_market_monthly.parquet"),
    "crsp_treasury": Path("wrds/crsp_treasury_monthly.parquet"),
    "shiller": Path("shiller/shiller_monthly.parquet"),
}


def _require_raw_files(raw_dir: Path) -> dict[str, Path]:
    paths = {name: raw_dir / relative for name, relative in RAW_FILES.items()}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing acquired raw caches. Run the corresponding pull commands: "
            + ", ".join(missing)
        )
    return paths


def _datetime_index(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    result = frame.copy()
    if column in result.columns:
        result[column] = pd.to_datetime(result[column], errors="raise")
        result = result.set_index(column)
    if not isinstance(result.index, pd.DatetimeIndex):
        result.index = pd.to_datetime(result.index, errors="raise")
    return result.sort_index()


def normalize_pulled_sources(
    raw_dir: Path,
    normalized_dir: Path,
    *,
    vintage: str | None = None,
) -> dict[str, CachePaths]:
    """Transform all current-vintage raw caches into quarterly contracts."""
    paths = _require_raw_files(raw_dir)
    retrieval_vintage = vintage or date.today().isoformat()

    bea = pd.read_parquet(paths["bea"])
    if not isinstance(bea.index, pd.PeriodIndex):
        bea.index = pd.PeriodIndex(bea.index, freq="Q")

    fred = _datetime_index(pd.read_parquet(paths["fred"]), "date")
    fred_last_columns = [
        "total_real_pce",
        "pce_price_index",
        "household_net_worth",
        "tbill_3m_yield",
        "treasury_1y_yield",
        "treasury_10y_yield",
        "baa_corporate_yield",
        "aaa_corporate_yield",
    ]
    fred_quarterly = quarterly_last(fred[fred_last_columns])
    fred_quarterly["population_candidate"] = quarterly_mean(
        fred[["population_candidate"]]
    )["population_candidate"]
    recessions = quarterly_max(fred[["nber_recession"]])

    market = _datetime_index(pd.read_parquet(paths["crsp_market"]), "date")
    treasury = _datetime_index(pd.read_parquet(paths["crsp_treasury"]), "caldt")
    shiller = _datetime_index(pd.read_parquet(paths["shiller"]), "date")
    inflation = quarterly_log_inflation(shiller["CPI"])
    crsp = build_crsp_market(market, treasury, shiller["CPI"])

    nominal_bill_30d = (
        np.log1p(treasury["t30ret"])
        .groupby(treasury.index.to_period("Q"))
        .sum(min_count=1)
    )
    rates = build_rates(fred_quarterly, inflation, nominal_bill_30d)
    macro = build_core_macro(bea, fred_quarterly)
    sp_market = build_shiller_market(shiller, crsp["bill_30d_return"])

    source_frames = {
        "core_macro": macro,
        "sp_market": sp_market,
        "crsp_market": crsp,
        "rates": rates,
        "recessions": recessions,
    }
    return {
        source_id: write_normalized_cache(
            frame,
            source_id,
            normalized_dir,
            vintage=retrieval_vintage,
            retrieval_description="Normalized from acquired raw source caches",
        )
        for source_id, frame in source_frames.items()
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--normalized-dir", type=Path)
    parser.add_argument("--vintage")
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    results = normalize_pulled_sources(
        args.raw_dir or settings.data_dir / "raw",
        args.normalized_dir or settings.data_dir / "normalized",
        vintage=args.vintage,
    )
    for source_id, paths in results.items():
        print(f"{source_id}: {paths.data}")


if __name__ == "__main__":
    main()
