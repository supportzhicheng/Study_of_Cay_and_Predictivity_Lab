"""Shared segment-level and rolling predictivity calculations."""

from __future__ import annotations

import math

import pandas as pd
from statsmodels.tools import add_constant

from src.extension.predictive_regression import PredictiveRegression

STATUS_ACTIVE = "ACTIVE"
STATUS_WEAKENED = "WEAKENED"
STATUS_LOST = "LOST"


def classify_status(
    max_abs_t: float,
    t_active: float = 1.96,
    t_weak: float = 1.28,
) -> str:
    """Classify predictivity from the largest absolute HAC t-statistic."""
    if math.isnan(max_abs_t):
        return STATUS_LOST
    if max_abs_t > t_active:
        return STATUS_ACTIVE
    if max_abs_t > t_weak:
        return STATUS_WEAKENED
    return STATUS_LOST


def rolling_predictivity(
    frame: pd.DataFrame,
    predictor_cols: list[str],
    target_col: str,
    train_periods: int,
) -> pd.DataFrame:
    """Run rolling one-period regressions for every segment."""
    rows: list[dict[str, object]] = []
    for segment, segment_frame in frame.groupby("segment", sort=True):
        segment_frame = segment_frame.sort_index()
        if len(segment_frame) <= train_periods:
            continue

        for split in range(train_periods, len(segment_frame)):
            train = segment_frame.iloc[split - train_periods : split]
            test = segment_frame.iloc[[split]]
            regression = PredictiveRegression(
                train,
                target_col=target_col,
                predictor_cols=predictor_cols,
                horizon=0,
            ).fit()

            test_predictors = add_constant(test[predictor_cols], has_constant="add")
            prediction = float(regression.result_.predict(test_predictors).iloc[0])
            actual = float(test[target_col].iloc[0])
            t_statistics = {
                column: float(regression.t_stat(column)) for column in predictor_cols
            }
            row: dict[str, object] = {
                "quarter": str(test.index[0]),
                "segment": segment,
                "prediction": prediction,
                "actual": actual,
                "error": actual - prediction,
                "abs_error": abs(actual - prediction),
                "r_squared": float(regression.r_squared()),
                "n_obs": int(regression.result_.nobs),
                "status": classify_status(
                    max(abs(value) for value in t_statistics.values())
                ),
            }
            for column in predictor_cols:
                row[f"t_stat_{column}"] = t_statistics[column]
                row[f"coef_{column}"] = float(regression.result_.params[column])
            rows.append(row)

    return pd.DataFrame(rows)


def segment_predictivity_tests(
    frame: pd.DataFrame,
    predictor_cols: list[str],
    target_col: str,
) -> pd.DataFrame:
    """Run one full-sample predictive regression per segment."""
    rows: list[dict[str, object]] = []
    for segment, segment_frame in frame.groupby("segment", sort=True):
        regression = PredictiveRegression(
            segment_frame.sort_index(),
            target_col=target_col,
            predictor_cols=predictor_cols,
            horizon=0,
        ).fit()
        t_statistics = {
            column: float(regression.t_stat(column)) for column in predictor_cols
        }
        row: dict[str, object] = {
            "segment": segment,
            "r_squared": float(regression.r_squared()),
            "n_obs": int(regression.result_.nobs),
            "status": classify_status(
                max(abs(value) for value in t_statistics.values())
            ),
            "target_col": target_col,
        }
        for column in predictor_cols:
            row[f"coef_{column}"] = float(regression.result_.params[column])
            row[f"t_stat_{column}"] = t_statistics[column]
            row[f"p_value_{column}"] = float(regression.result_.pvalues[column])
        rows.append(row)
    return pd.DataFrame(rows).sort_values("segment").reset_index(drop=True)
