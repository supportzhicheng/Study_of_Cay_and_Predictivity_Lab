"""Table II correlations and summary statistics."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TABLE_II_VARIABLES = (
    "sp_excess_return",
    "dividend_yield",
    "payout_ratio",
    "relative_bill_rate",
    "cay",
)


@dataclass(frozen=True)
class TableIIResult:
    correlations: pd.DataFrame
    summary: pd.DataFrame
    sample_start: pd.Period
    sample_end: pd.Period


def build_table_ii(panel: pd.DataFrame) -> TableIIResult:
    """Build the complete-case Table II descriptive statistics."""
    missing = sorted(set(TABLE_II_VARIABLES) - set(panel.columns))
    if missing:
        raise ValueError(f"Table II is missing columns: {missing}")
    sample = panel.loc[:, TABLE_II_VARIABLES].dropna()
    if sample.empty:
        raise ValueError("Table II has no complete observations.")
    summary = pd.DataFrame(
        {
            "observations": sample.count(),
            "mean": sample.mean(),
            "standard_deviation": sample.std(ddof=1),
            "ar1": sample.apply(lambda series: series.corr(series.shift(1))),
        }
    )
    return TableIIResult(
        correlations=sample.corr(),
        summary=summary,
        sample_start=sample.index.min(),
        sample_end=sample.index.max(),
    )
