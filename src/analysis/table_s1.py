"""Original data coverage and summary-statistics exhibit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

SUMMARY_VARIABLES = (
    "consumption_growth",
    "labor_income_growth",
    "net_worth_growth",
    "sp_excess_return",
    "crsp_vw_excess_return",
    "dividend_yield",
    "payout_ratio",
    "relative_bill_rate",
    "term_spread",
    "default_spread",
    "cay",
)


@dataclass(frozen=True)
class TableS1Result:
    coverage: pd.DataFrame
    summary: pd.DataFrame
    takeaway: str


def _statistics(sample: pd.DataFrame, sample_name: str) -> pd.DataFrame:
    rows = []
    for variable in SUMMARY_VARIABLES:
        series = sample[variable].dropna()
        rows.append(
            {
                "sample": sample_name,
                "variable": variable,
                "observations": len(series),
                "mean": series.mean(),
                "standard_deviation": series.std(ddof=1),
                "p05": series.quantile(0.05),
                "median": series.median(),
                "p95": series.quantile(0.95),
                "ar1": series.corr(series.shift(1)),
            }
        )
    return pd.DataFrame(rows)


def build_table_s1(
    panel: pd.DataFrame,
    source_notes: Mapping[str, tuple[str, str, str]] | None = None,
) -> TableS1Result:
    """Build coverage and historical/updated summary panels with a takeaway."""
    working = panel.copy()
    working["consumption_growth"] = working["c"].diff()
    working["labor_income_growth"] = working["y"].diff()
    working["net_worth_growth"] = working["a"].diff()
    missing = sorted(set(SUMMARY_VARIABLES) - set(working.columns))
    if missing:
        raise ValueError(f"Table S1 is missing variables: {missing}")

    coverage_rows = []
    notes = source_notes or {}
    for variable in SUMMARY_VARIABLES:
        series = working[variable]
        observed = series.dropna()
        source, frequency, transformation = notes.get(
            variable, ("core quarterly panel", "Quarterly", "See source metadata")
        )
        coverage_rows.append(
            {
                "variable": variable,
                "source": source,
                "frequency": frequency,
                "transformation": transformation,
                "first_quarter": str(observed.index.min())
                if not observed.empty
                else None,
                "last_quarter": str(observed.index.max())
                if not observed.empty
                else None,
                "missing_observations": int(series.isna().sum()),
            }
        )

    historical = working.loc["1952Q4":"1998Q3"]
    summary = pd.concat(
        [_statistics(historical, "historical"), _statistics(working, "updated")],
        ignore_index=True,
    )
    updated_stats = summary[summary["sample"] == "updated"].set_index("variable")
    growth_variables = [
        "consumption_growth",
        "labor_income_growth",
        "net_worth_growth",
    ]
    most_volatile = updated_stats.loc[growth_variables, "standard_deviation"].idxmax()
    predictor_variables = [
        "dividend_yield",
        "payout_ratio",
        "relative_bill_rate",
        "term_spread",
        "default_spread",
        "cay",
    ]
    most_persistent = updated_stats.loc[predictor_variables, "ar1"].idxmax()
    takeaway = (
        f"{most_volatile} has the largest updated growth volatility; "
        f"{most_persistent} is the most persistent predictor."
    )
    return TableS1Result(
        coverage=pd.DataFrame(coverage_rows), summary=summary, takeaway=takeaway
    )
