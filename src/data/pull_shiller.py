"""Acquire Robert Shiller's public S&P workbook."""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from typing import Protocol, Sequence

import pandas as pd
import requests

from src.settings import load_settings

SHILLER_WORKBOOK_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
REQUIRED_COLUMNS = ("P", "D", "E", "CPI")


class HttpResponse(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class HttpSession(Protocol):
    def get(self, url: str, *, timeout: int) -> HttpResponse: ...


def parse_shiller_month(value: object) -> pd.Timestamp:
    """Parse Shiller's numeric YYYY.MM month convention without float drift."""
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Shiller month value: {value!r}") from exc
    year = int(numeric)
    month = int(round((numeric - year) * 100))
    if month < 1 or month > 12:
        raise ValueError(f"Invalid Shiller month value: {value!r}")
    return pd.Timestamp(year=year, month=month, day=1)


def normalize_shiller_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the workbook's monthly market columns."""
    normalized = frame.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    date_column = "Date" if "Date" in normalized.columns else normalized.columns[0]
    missing = sorted(set(REQUIRED_COLUMNS) - set(normalized.columns))
    if missing:
        raise ValueError(f"Shiller workbook is missing required columns: {missing}")

    normalized = normalized.dropna(subset=[date_column])
    dates = pd.DatetimeIndex(
        [parse_shiller_month(value) for value in normalized[date_column]]
    )
    result = normalized.loc[:, REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    result.index = dates
    result.index.name = "date"
    return result.sort_index()


def fetch_shiller_data(session: HttpSession | None = None) -> pd.DataFrame:
    """Download and parse the pinned public workbook through an HTTP boundary."""
    client = session or requests.Session()
    response = client.get(SHILLER_WORKBOOK_URL, timeout=60)
    response.raise_for_status()
    raw = pd.read_excel(BytesIO(response.content), sheet_name="Data", skiprows=7)
    return normalize_shiller_frame(raw)


def pull_shiller_data(raw_dir: Path, session: HttpSession | None = None) -> Path:
    """Write the normalized monthly workbook fields to a raw cache."""
    frame = fetch_shiller_data(session)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "shiller_monthly.parquet"
    frame.to_parquet(path)
    return path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    print(pull_shiller_data(args.raw_dir or settings.data_dir / "raw" / "shiller"))


if __name__ == "__main__":
    main()
