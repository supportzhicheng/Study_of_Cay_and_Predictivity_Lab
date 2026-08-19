"""Validation for normalized quarterly source data."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.data.source_registry import get_source_spec


def _quarter_index(values: Iterable[object] | pd.Index) -> pd.PeriodIndex:
    if isinstance(values, pd.PeriodIndex):
        if not values.freqstr.startswith("Q"):
            raise ValueError("PeriodIndex must have quarterly frequency.")
        return values.asfreq("Q")

    raw = pd.Index(values)
    text = raw.astype(str).str.strip()
    is_quarter_label = text.str.fullmatch(r"\d{4}Q[1-4]")
    if is_quarter_label.all():
        return pd.PeriodIndex(text, freq="Q")

    dates = pd.to_datetime(raw, errors="coerce")
    if dates.isna().any():
        invalid = sorted(set(text[dates.isna()].tolist()))
        raise ValueError(f"Invalid quarterly date values: {invalid}")
    return dates.to_period("Q")


def normalize_quarterly_source(frame: pd.DataFrame, source_id: str) -> pd.DataFrame:
    """Validate one registered source and return a sorted quarterly copy."""
    spec = get_source_spec(source_id)
    if frame.empty:
        raise ValueError(f"Source '{source_id}' is empty.")

    normalized = frame.copy()
    if "quarter" in normalized.columns:
        quarter_values = normalized.pop("quarter")
    elif "date" in normalized.columns:
        quarter_values = normalized.pop("date")
    elif not isinstance(normalized.index, pd.RangeIndex):
        quarter_values = normalized.index
    else:
        raise ValueError("Source must provide a 'quarter' or 'date' field.")

    index = _quarter_index(quarter_values)
    if index.has_duplicates:
        duplicates = sorted(set(index[index.duplicated(keep=False)].astype(str)))
        raise ValueError(f"Duplicate quarters are not allowed: {duplicates}")

    missing = sorted(set(spec.required_columns) - set(normalized.columns))
    if missing:
        raise ValueError(f"Source '{source_id}' is missing required columns: {missing}")

    for column in spec.required_columns:
        try:
            normalized[column] = pd.to_numeric(normalized[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Source '{source_id}' column '{column}' must be numeric."
            ) from exc

    normalized.index = index
    normalized.index.name = "quarter"
    return normalized.sort_index()
