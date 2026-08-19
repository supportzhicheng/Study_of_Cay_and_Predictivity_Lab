"""Acquire the public FRED series used by the core replication."""

from __future__ import annotations

import argparse
import json
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Protocol, Sequence

import pandas as pd
import requests

from src.data.cache import sha256_file
from src.settings import load_settings

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES = {
    "PCECC96": "total_real_pce",
    "PCECTPI": "pce_price_index",
    "CNP16OV": "population_candidate",
    "BOGZ1LM152090005Q": "household_net_worth",
    "TB3MS": "tbill_3m_yield",
    "GS1": "treasury_1y_yield",
    "GS10": "treasury_10y_yield",
    "BAA": "baa_corporate_yield",
    "AAA": "aaa_corporate_yield",
    "USRECQ": "nber_recession",
}


class HttpResponse(Protocol):
    text: str

    def raise_for_status(self) -> None: ...


class HttpSession(Protocol):
    def get(
        self, url: str, *, params: dict[str, str], timeout: int
    ) -> HttpResponse: ...


def fetch_fred_series(
    series_id: str,
    internal_name: str,
    *,
    session: HttpSession | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.Series:
    """Fetch one FRED CSV and rename it at the acquisition boundary."""
    client = session or requests.Session()
    params = {"id": series_id}
    if start_date:
        params["cosd"] = start_date
    if end_date:
        params["coed"] = end_date
    response = client.get(FRED_CSV_URL, params=params, timeout=60)
    response.raise_for_status()

    frame = pd.read_csv(StringIO(response.text))
    date_column = "DATE" if "DATE" in frame.columns else "observation_date"
    if date_column not in frame or series_id not in frame:
        raise ValueError(f"FRED response for '{series_id}' has unexpected columns.")
    dates = pd.to_datetime(frame[date_column], errors="raise")
    values = pd.to_numeric(frame[series_id].replace(".", None), errors="coerce")
    return pd.Series(values.to_numpy(), index=dates, name=internal_name)


def pull_fred_data(
    raw_dir: Path,
    *,
    session: HttpSession | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    vintage: str | None = None,
) -> tuple[Path, Path]:
    """Fetch all registered FRED inputs and write a raw combined cache."""
    columns = [
        fetch_fred_series(
            series_id,
            internal_name,
            session=session,
            start_date=start_date,
            end_date=end_date,
        )
        for series_id, internal_name in FRED_SERIES.items()
    ]
    frame = pd.concat(columns, axis=1).sort_index()
    frame.index.name = "date"
    raw_dir.mkdir(parents=True, exist_ok=True)
    data_path = raw_dir / "fred_inputs.parquet"
    metadata_path = raw_dir / "fred_inputs.metadata.json"
    frame.to_parquet(data_path)
    metadata = {
        "provider": "FRED",
        "series": FRED_SERIES,
        "vintage": vintage or date.today().isoformat(),
        "sample_start": str(frame.index.min().date()),
        "sample_end": str(frame.index.max().date()),
        "row_count": len(frame),
        "missing_counts": {
            column: int(value) for column, value in frame.isna().sum().items()
        },
        "sha256": sha256_file(data_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data_path, metadata_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    paths = pull_fred_data(
        args.raw_dir or settings.data_dir / "raw" / "fred",
        start_date=settings.start_date,
        end_date=settings.end_date,
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
