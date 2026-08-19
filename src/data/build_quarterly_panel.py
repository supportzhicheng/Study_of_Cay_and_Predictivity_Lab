"""Merge normalized quarterly sources into the core analysis panel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from src.data.cache import sha256_file
from src.data.contracts import normalize_quarterly_source
from src.data.source_registry import required_panel_sources

HISTORICAL_INDEX = pd.period_range("1952Q4", "1998Q3", freq="Q")


def build_quarterly_panel(sources: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Validate and outer-merge all required normalized source families."""
    missing_sources = sorted(set(required_panel_sources()) - set(sources))
    if missing_sources:
        raise ValueError(f"Missing required source families: {missing_sources}")

    frames: list[pd.DataFrame] = []
    seen_columns: set[str] = set()
    for source_id in required_panel_sources():
        normalized = normalize_quarterly_source(sources[source_id], source_id)
        duplicates = sorted(seen_columns & set(normalized.columns))
        if duplicates:
            raise ValueError(f"Duplicate panel columns are not allowed: {duplicates}")
        seen_columns.update(normalized.columns)
        frames.append(normalized)

    if "posted_cay" in sources:
        posted = normalize_quarterly_source(sources["posted_cay"], "posted_cay").rename(
            columns={"cay": "posted_cay_updated"}
        )
        duplicates = sorted(seen_columns & set(posted.columns))
        if duplicates:
            raise ValueError(f"Duplicate panel columns are not allowed: {duplicates}")
        frames.append(posted)

    panel = pd.concat(frames, axis=1, join="outer").sort_index()
    panel.index.name = "quarter"
    panel["consumption_growth"] = panel["c"].diff()
    return panel


def validate_historical_sample(
    panel: pd.DataFrame, required_columns: Sequence[str]
) -> pd.DataFrame:
    """Require all 184 paper-window quarters and complete exhibit columns."""
    missing_columns = sorted(set(required_columns) - set(panel.columns))
    if missing_columns:
        raise ValueError(f"Historical sample is missing columns: {missing_columns}")
    historical = panel.reindex(HISTORICAL_INDEX)
    missing_quarters = HISTORICAL_INDEX.difference(panel.index)
    if len(missing_quarters):
        raise ValueError(
            f"Historical sample is missing quarters: {missing_quarters.tolist()}"
        )
    missing_values = historical[list(required_columns)].isna().sum()
    incomplete = missing_values[missing_values > 0].to_dict()
    if incomplete:
        raise ValueError(f"Historical sample contains missing values: {incomplete}")
    return historical


def latest_common_quarter(
    panel: pd.DataFrame, required_columns: Sequence[str]
) -> pd.Period:
    """Return the latest observed quarter complete for an exhibit."""
    missing = sorted(set(required_columns) - set(panel.columns))
    if missing:
        raise ValueError(f"Panel is missing required columns: {missing}")
    complete = panel[list(required_columns)].dropna()
    if complete.empty:
        raise ValueError("No complete observations for the requested columns.")
    return complete.index.max()


def write_quarterly_panel(
    panel: pd.DataFrame,
    processed_dir: Path,
    *,
    source_vintages: Mapping[str, str],
) -> tuple[Path, Path]:
    """Write the processed panel and required metadata contract."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    data_path = processed_dir / "core_quarterly.parquet"
    metadata_path = processed_dir / "core_quarterly.metadata.json"
    panel.to_parquet(data_path)
    metadata = {
        "sample_start": str(panel.index.min()),
        "sample_end": str(panel.index.max()),
        "observations": len(panel),
        "columns": panel.columns.tolist(),
        "missing_counts": {
            column: int(value) for column, value in panel.isna().sum().items()
        },
        "source_vintages": dict(source_vintages),
        "sha256": sha256_file(data_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data_path, metadata_path
