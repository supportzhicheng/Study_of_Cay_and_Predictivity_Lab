"""Forward-outcome timing and OLS/Newey-West forecasting primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm


def _validate_quarterly(obj: pd.Series | pd.DataFrame) -> None:
    if not isinstance(obj.index, pd.PeriodIndex) or not obj.index.freqstr.startswith(
        "Q"
    ):
        raise ValueError("Forecast data must use a quarterly PeriodIndex.")
    if obj.index.has_duplicates:
        raise ValueError("Forecast data must use unique quarterly observations.")


def forward_sum(series: pd.Series, horizon: int) -> pd.Series:
    """Align the sum from t+1 through t+h with predictor date t."""
    _validate_quarterly(series)
    if horizon <= 0:
        raise ValueError("horizon must be positive.")
    shifted = pd.concat([series.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return shifted.sum(axis=1, min_count=horizon).rename(series.name)


def forward_change(series: pd.Series, horizon: int) -> pd.Series:
    """Align the log-level change x(t+h)-x(t) with predictor date t."""
    _validate_quarterly(series)
    if horizon <= 0:
        raise ValueError("horizon must be positive.")
    return (series.shift(-horizon) - series).rename(series.name)


def newey_west_lags(observations: int, horizon: int) -> int:
    """Return the automatic bandwidth, covering overlapping outcomes."""
    if observations <= 0:
        raise ValueError("observations must be positive.")
    if horizon <= 0:
        raise ValueError("horizon must be positive.")
    automatic = math.floor(4 * (observations / 100) ** (2 / 9))
    return max(horizon - 1, automatic)


@dataclass(frozen=True)
class ForecastResult:
    coefficients: dict[str, float]
    t_statistics: dict[str, float]
    p_values: dict[str, float]
    adjusted_r_squared: float
    observations: int
    sample_start: pd.Period
    sample_end: pd.Period
    hac_lags: int


def run_hac_regression(
    outcome: pd.Series,
    predictors: pd.DataFrame,
    *,
    horizon: int,
    hac_lags: int | None = None,
) -> ForecastResult:
    """Fit OLS with a constant and Newey-West HAC inference."""
    _validate_quarterly(outcome)
    _validate_quarterly(predictors)
    if predictors.columns.duplicated().any():
        raise ValueError("Predictor names must be unique.")
    if predictors.shape[1] == 0:
        raise ValueError("At least one predictor is required.")
    if hac_lags is not None and hac_lags < 0:
        raise ValueError("hac_lags must be nonnegative.")

    outcome_name = outcome.name or "outcome"
    combined = pd.concat([outcome.rename(outcome_name), predictors], axis=1).dropna()
    if combined.empty:
        raise ValueError("No complete observations remain for forecasting regression.")
    combined = combined.astype(float)
    y = combined.iloc[:, 0]
    x = sm.add_constant(combined.iloc[:, 1:], has_constant="add")
    bandwidth = (
        hac_lags if hac_lags is not None else newey_west_lags(len(combined), horizon)
    )
    result = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": bandwidth})
    return ForecastResult(
        coefficients={name: float(value) for name, value in result.params.items()},
        t_statistics={name: float(value) for name, value in result.tvalues.items()},
        p_values={name: float(value) for name, value in result.pvalues.items()},
        adjusted_r_squared=float(result.rsquared_adj),
        observations=int(result.nobs),
        sample_start=combined.index.min(),
        sample_end=combined.index.max(),
        hac_lags=bandwidth,
    )
