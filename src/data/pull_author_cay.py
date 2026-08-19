"""Acquire and normalize archived and updated author-posted CAY files."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Protocol, Sequence

import pandas as pd
import requests

from src.data.cache import CachePaths, sha256_file, write_normalized_cache
from src.data.contracts import normalize_quarterly_source
from src.data.source_registry import get_source_spec
from src.settings import load_settings

HISTORICAL_AUTHOR_URL = (
    "https://web.archive.org/web/20010119094600id_/"
    "http://www.ny.frb.org:80/rmaghome/economist/lettau/lldata.txt"
)
UPDATED_AUTHOR_URL = (
    "https://raw.githubusercontent.com/mlettau/Data/"
    "1c5dd897fcd6aa8c38e4229de5bcfb849b18a57a/"
    "cay-data/cay_current.txt"
)
HISTORICAL_START = pd.Period("1952Q4", freq="Q")
HISTORICAL_END = pd.Period("1998Q3", freq="Q")


class HttpResponse(Protocol):
    text: str

    def raise_for_status(self) -> None: ...


class HttpSession(Protocol):
    def get(self, url: str, *, timeout: int) -> HttpResponse: ...


def _normalize_author_quarter(value: str) -> str | None:
    match = re.fullmatch(r"(\d{4})(?:Q|0)?([1-4])", value)
    return f"{match.group(1)}Q{match.group(2)}" if match else None


def _read_whitespace_data(text: str, column_names: list[str]) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        quarter = _normalize_author_quarter(fields[0])
        if quarter is None:
            continue
        expected_values = len(column_names) - 1
        if len(fields) < expected_values + 1:
            raise ValueError(f"Incomplete author data row for {quarter}.")
        rows.append([quarter, *fields[1 : expected_values + 1]])
    frame = pd.DataFrame(rows, columns=column_names)
    if frame.empty:
        raise ValueError("Author data file contains no observations.")
    for column in column_names[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame.replace(-99.0, float("nan"))


def parse_historical_author_data(text: str) -> pd.DataFrame:
    """Parse the archived paper-window macro inputs and validation CAY."""
    frame = _read_whitespace_data(
        text, ["quarter", "paper_c", "paper_a", "paper_y", "posted_cay"]
    )
    quarter_index = pd.PeriodIndex(frame["quarter"], freq="Q")
    frame = frame.loc[
        (quarter_index >= HISTORICAL_START) & (quarter_index <= HISTORICAL_END)
    ].reset_index(drop=True)
    quarters = pd.PeriodIndex(frame.pop("quarter").astype(str), freq="Q")
    expected = pd.period_range(HISTORICAL_START, HISTORICAL_END, freq="Q")
    if not quarters.equals(expected):
        raise ValueError(
            "Archived author data must contain exactly 184 consecutive quarters "
            "from 1952Q4 through 1998Q3."
        )
    frame.insert(0, "quarter", quarters.astype(str))
    return frame


def parse_updated_author_cay(text: str) -> pd.DataFrame:
    """Parse updated author data while retaining CAY for validation only."""
    frame = _read_whitespace_data(
        text,
        [
            "quarter",
            "consumption",
            "wealth",
            "labor_income",
            "cay",
            "markov_switching_cay",
        ],
    )
    return frame[["quarter", "cay"]]


def fetch_text(url: str, session: HttpSession | None = None) -> str:
    """Fetch a text source through an injectable HTTP boundary."""
    client = session or requests.Session()
    response = client.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def pull_author_data(
    cache_dir: Path,
    *,
    session: HttpSession | None = None,
    vintage: str | None = None,
) -> tuple[CachePaths, CachePaths]:
    """Download both pinned author files and write normalized caches."""
    retrieval_vintage = vintage or date.today().isoformat()
    historical = parse_historical_author_data(
        fetch_text(HISTORICAL_AUTHOR_URL, session)
    )
    updated = parse_updated_author_cay(fetch_text(UPDATED_AUTHOR_URL, session))

    historical_paths = write_normalized_cache(
        historical,
        "paper_macro",
        cache_dir,
        vintage=retrieval_vintage,
        retrieval_description="Pinned archived paper-era author file",
        extra_metadata={"url": HISTORICAL_AUTHOR_URL},
    )
    updated_paths = write_normalized_cache(
        updated,
        "posted_cay",
        cache_dir,
        vintage=retrieval_vintage,
        retrieval_description="Pinned updated author-posted CAY validation file",
        extra_metadata={"url": UPDATED_AUTHOR_URL, "validation_only": True},
    )
    return historical_paths, updated_paths


def cached_author_data(cache_dir: Path) -> tuple[CachePaths, CachePaths] | None:
    """Return hash-verified author caches, or None when either cache is absent."""
    cached_paths = []
    for source_id in ("paper_macro", "posted_cay"):
        spec = get_source_spec(source_id)
        paths = CachePaths(
            data=cache_dir / f"{spec.filename_stem}.parquet",
            metadata=cache_dir / f"{spec.filename_stem}.metadata.json",
        )
        if not paths.data.exists() or not paths.metadata.exists():
            return None
        metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
        if metadata.get("sha256") != sha256_file(paths.data):
            raise ValueError(f"Cached author data hash mismatch: {paths.data}")
        normalize_quarterly_source(pd.read_parquet(paths.data), source_id)
        cached_paths.append(paths)
    return cached_paths[0], cached_paths[1]


def ensure_author_data(
    cache_dir: Path,
    *,
    session: HttpSession | None = None,
    vintage: str | None = None,
) -> tuple[CachePaths, CachePaths]:
    """Reuse valid author caches, otherwise acquire both pinned files."""
    cached = cached_author_data(cache_dir)
    return cached or pull_author_data(cache_dir, session=session, vintage=vintage)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--vintage")
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    paths = pull_author_data(
        args.cache_dir or settings.data_dir / "normalized", vintage=args.vintage
    )
    for result in paths:
        print(result.data)
        print(result.metadata)


if __name__ == "__main__":
    main()
