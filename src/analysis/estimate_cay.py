"""Structured CAY estimation for historical and updated analysis modes."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.cay_builder import CayBuilder


@dataclass(frozen=True)
class CayEstimate:
    """Long-run coefficients, paper-convention CAY, and estimation metadata."""

    cay: pd.Series
    fixed_cay: pd.Series
    beta_a: float
    beta_y: float
    intercept: float
    estimation_start: pd.Period
    estimation_end: pd.Period
    estimation_observations: int
    leads_lags: int


def construct_fixed_cay(
    frame: pd.DataFrame,
    *,
    beta_a: float | None = None,
    beta_y: float | None = None,
) -> pd.Series:
    """Construct the declared fixed-coefficient robustness series."""
    if (beta_a is None) != (beta_y is None):
        raise ValueError("Fixed CAY requires both beta_a and beta_y.")
    asset_coefficient = 0.31 if beta_a is None else beta_a
    income_coefficient = 0.59 if beta_y is None else beta_y
    return (
        frame["c"] - asset_coefficient * frame["a"] - income_coefficient * frame["y"]
    ).rename("cay_fixed")


def estimate_cay(frame: pd.DataFrame, leads_lags: int = 8) -> CayEstimate:
    """Estimate DLS coefficients and construct full-sample CAY series."""
    builder = CayBuilder(frame, lags=leads_lags).fit()
    return CayEstimate(
        cay=builder.cay,
        fixed_cay=construct_fixed_cay(frame),
        beta_a=float(builder.coef_["beta_a"]),
        beta_y=float(builder.coef_["beta_y"]),
        intercept=float(builder.coef_["const"]),
        estimation_start=builder.estimation_start_,
        estimation_end=builder.estimation_end_,
        estimation_observations=int(builder.model_result_.nobs),
        leads_lags=leads_lags,
    )
