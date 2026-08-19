"""Table VI long-horizon consumption and return forecasting models."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.forecasting import forward_change, forward_sum, run_hac_regression

HORIZONS = (1, 2, 3, 4, 8, 12, 16, 24)


@dataclass(frozen=True)
class TableVISpec:
    specification: int
    outcome_kind: str
    predictors: tuple[str, ...]


TABLE_VI_SPECS = (
    TableVISpec(1, "consumption_growth", ("cay",)),
    TableVISpec(2, "sp_excess_return", ("cay",)),
    TableVISpec(3, "sp_excess_return", ("dividend_yield",)),
    TableVISpec(4, "sp_excess_return", ("dividend_yield", "payout_ratio")),
    TableVISpec(5, "sp_excess_return", ("relative_bill_rate",)),
    TableVISpec(
        6,
        "sp_excess_return",
        ("cay", "dividend_yield", "payout_ratio", "relative_bill_rate"),
    ),
)


def _forward_outcome(panel: pd.DataFrame, spec: TableVISpec, horizon: int) -> pd.Series:
    if spec.outcome_kind == "consumption_growth":
        if "c" not in panel:
            raise ValueError("Table VI is missing consumption log level 'c'.")
        return forward_change(panel["c"], horizon).rename("consumption_growth")
    if "sp_excess_return" not in panel:
        raise ValueError("Table VI is missing S&P excess returns.")
    return forward_sum(panel["sp_excess_return"], horizon)


def build_table_vi(panel: pd.DataFrame) -> pd.DataFrame:
    """Run six specifications at all eight declared horizons."""
    rows: list[dict] = []
    for spec in TABLE_VI_SPECS:
        missing = sorted(set(spec.predictors) - set(panel.columns))
        if missing:
            raise ValueError(f"Table VI is missing predictors: {missing}")
        for horizon in HORIZONS:
            outcome = _forward_outcome(panel, spec, horizon)
            result = run_hac_regression(
                outcome, panel.loc[:, spec.predictors], horizon=horizon
            )
            for term, coefficient in result.coefficients.items():
                rows.append(
                    {
                        "specification": spec.specification,
                        "horizon": horizon,
                        "outcome": spec.outcome_kind,
                        "predictors": ", ".join(spec.predictors),
                        "term": term,
                        "coefficient": coefficient,
                        "t_statistic": result.t_statistics[term],
                        "p_value": result.p_values[term],
                        "adjusted_r_squared": result.adjusted_r_squared,
                        "observations": result.observations,
                        "sample_start": str(result.sample_start),
                        "sample_end": str(result.sample_end),
                        "hac_lags": result.hac_lags,
                    }
                )
    return (
        pd.DataFrame(rows)
        .sort_values(["specification", "horizon", "term"])
        .reset_index(drop=True)
    )
