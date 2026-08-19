"""Table III one-quarter-ahead forecasting specifications."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.forecasting import ForecastResult, run_hac_regression


@dataclass(frozen=True)
class TableIIISpec:
    row: int
    outcome: str
    predictors: tuple[str, ...]
    start: str = "1952Q4"


TABLE_III_SPECS = (
    TableIIISpec(1, "sp_real_return", ("lagged_return",)),
    TableIIISpec(2, "sp_real_return", ("cay",)),
    TableIIISpec(3, "sp_real_return", ("lagged_return", "cay")),
    TableIIISpec(4, "crsp_vw_real_return", ("lagged_return", "cay")),
    TableIIISpec(5, "sp_excess_return", ("lagged_return",)),
    TableIIISpec(6, "sp_excess_return", ("cay",)),
    TableIIISpec(7, "sp_excess_return", ("lagged_return", "cay")),
    TableIIISpec(8, "crsp_vw_excess_return", ("lagged_return", "cay")),
    TableIIISpec(9, "sp_excess_return", ("dividend_yield",)),
    TableIIISpec(10, "sp_excess_return", ("cay", "dividend_yield")),
    TableIIISpec(11, "sp_excess_return", ("dividend_yield", "payout_ratio")),
    TableIIISpec(12, "sp_excess_return", ("cay", "dividend_yield", "payout_ratio")),
    TableIIISpec(
        13,
        "sp_excess_return",
        (
            "lagged_return",
            "cay",
            "dividend_yield",
            "payout_ratio",
            "relative_bill_rate",
            "term_spread",
            "default_spread",
        ),
        start="1953Q2",
    ),
)


def prepare_table_iii_model(
    panel: pd.DataFrame, spec: TableIIISpec
) -> tuple[pd.Series, pd.DataFrame]:
    """Construct next-quarter outcome and date-t predictors for one row."""
    sample = panel.loc[pd.Period(spec.start, freq="Q") :]
    if spec.outcome not in sample:
        raise ValueError(f"Table III is missing outcome '{spec.outcome}'.")
    outcome = sample[spec.outcome].shift(-1).rename(spec.outcome)
    predictors = pd.DataFrame(index=sample.index)
    for predictor in spec.predictors:
        if predictor == "lagged_return":
            predictors[predictor] = sample[spec.outcome]
        elif predictor in sample:
            predictors[predictor] = sample[predictor]
        else:
            raise ValueError(f"Table III is missing predictor '{predictor}'.")
    return outcome, predictors


def _tidy_result(spec: TableIIISpec, result: ForecastResult) -> list[dict]:
    return [
        {
            "row": spec.row,
            "outcome": spec.outcome,
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
        for term, coefficient in result.coefficients.items()
    ]


def build_table_iii(panel: pd.DataFrame) -> pd.DataFrame:
    """Run all 13 declared one-quarter-ahead forecasting models."""
    rows: list[dict] = []
    for spec in TABLE_III_SPECS:
        outcome, predictors = prepare_table_iii_model(panel, spec)
        rows.extend(
            _tidy_result(spec, run_hac_regression(outcome, predictors, horizon=1))
        )
    return pd.DataFrame(rows).sort_values(["row", "term"]).reset_index(drop=True)
