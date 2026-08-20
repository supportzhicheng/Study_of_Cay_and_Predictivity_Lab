"""Tests for structured CAY estimation and forecasting primitives."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.conventions import select_convention, select_panel_conventions
from src.analysis.estimate_cay import construct_fixed_cay, estimate_cay
from src.analysis.forecasting import (
    forward_change,
    forward_sum,
    newey_west_lags,
    run_hac_regression,
)
from tests.synthetic import make_synthetic_dataset


def test_hac_regression_accepts_nullable_numeric_dtypes():
    index = pd.period_range("2000Q1", periods=12, freq="Q")
    predictor = pd.Series(range(12), index=index, dtype="Float64", name="signal")
    outcome = pd.Series(range(1, 13), index=index, dtype="Float64", name="return")

    result = run_hac_regression(outcome, predictor.to_frame(), horizon=1)

    assert result.observations == 12
    assert result.coefficients["signal"] == pytest.approx(1.0)


def test_estimate_cay_uses_interior_fit_and_full_level_construction():
    frame = make_synthetic_dataset(n_periods=80, seed=5)

    result = estimate_cay(frame, leads_lags=2)

    assert result.estimation_observations < len(frame)
    assert len(result.cay) == len(frame)
    assert result.estimation_start > frame.index.min()
    assert result.estimation_end < frame.index.max()
    expected = frame["c"] - result.beta_a * frame["a"] - result.beta_y * frame["y"]
    np.testing.assert_allclose(result.cay, expected)


def test_fixed_cay_uses_declared_coefficients_and_requires_both_overrides():
    frame = make_synthetic_dataset(n_periods=20, seed=2)

    result = construct_fixed_cay(frame)

    np.testing.assert_allclose(
        result, frame["c"] - 0.31 * frame["a"] - 0.59 * frame["y"]
    )
    with pytest.raises(ValueError, match="requires both"):
        construct_fixed_cay(frame, beta_a=0.4)


def test_forward_sum_aligns_t_plus_one_through_t_plus_h():
    index = pd.period_range("2000Q1", periods=5, freq="Q")
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=index, name="return")

    result = forward_sum(series, 2)

    assert result.loc["2000Q1"] == 5.0
    assert result.loc["2000Q3"] == 9.0
    assert pd.isna(result.loc["2000Q4"])


def test_forward_change_aligns_future_level_change():
    index = pd.period_range("2000Q1", periods=4, freq="Q")
    levels = pd.Series([1.0, 1.5, 2.5, 4.0], index=index, name="c")

    result = forward_change(levels, 2)

    assert result.loc["2000Q1"] == 1.5
    assert result.loc["2000Q2"] == 2.5
    assert pd.isna(result.loc["2000Q3"])


def test_newey_west_bandwidth_uses_horizon_rule():
    assert newey_west_lags(200, 1) == 1
    assert newey_west_lags(200, 2) == 1
    assert newey_west_lags(200, 24) == 23


def test_hac_regression_recovers_slope_and_metadata():
    rng = np.random.default_rng(7)
    index = pd.period_range("1970Q1", periods=200, freq="Q")
    predictor = pd.Series(rng.normal(size=200), index=index, name="cay")
    outcome = pd.Series(
        0.5 + 2.0 * predictor + rng.normal(scale=0.1, size=200),
        index=index,
        name="return",
    )

    result = run_hac_regression(outcome, predictor.to_frame(), horizon=4)

    assert result.coefficients["cay"] == pytest.approx(2.0, abs=0.03)
    assert result.hac_lags >= 3
    assert result.observations == 200
    assert result.sample_start == index[0]
    assert result.sample_end == index[-1]


def test_forecast_slope_is_invariant_to_predictor_intercept_shift():
    index = pd.period_range("2000Q1", periods=40, freq="Q")
    predictor = pd.Series(np.linspace(-1, 1, 40), index=index, name="cay")
    outcome = pd.Series(1.0 + 3.0 * predictor, index=index, name="return")

    original = run_hac_regression(outcome, predictor.to_frame(), horizon=1, hac_lags=0)
    shifted = run_hac_regression(
        outcome, (predictor + 10).to_frame(), horizon=1, hac_lags=0
    )

    assert original.coefficients["cay"] == pytest.approx(shifted.coefficients["cay"])


def test_hac_regression_accepts_nullable_float_dtypes():
    index = pd.period_range("2000Q1", periods=12, freq="Q")
    predictor = pd.Series(
        np.linspace(-1.0, 1.0, len(index)),
        index=index,
        name="cay",
        dtype="Float64",
    )
    outcome = pd.Series(
        0.2 + 0.8 * predictor.astype(float),
        index=index,
        name="return",
        dtype="Float64",
    )

    result = run_hac_regression(outcome, predictor.to_frame(), horizon=1, hac_lags=0)
    assert result.coefficients["cay"] == pytest.approx(0.8, abs=1e-6)


def test_candidate_scoring_uses_scaled_error_and_declared_tie_break():
    selection = select_convention(
        {
            "bill_30d": {"coefficient": 1.0, "adjusted_r2": 0.10},
            "bill_3m": {"coefficient": 1.15, "adjusted_r2": 0.115},
        },
        anchors={"coefficient": 1.0, "adjusted_r2": 0.10},
        tolerances={"coefficient": 0.15, "adjusted_r2": 0.015},
        tie_break_order=["bill_30d", "bill_3m"],
    )
    assert selection.selected == "bill_30d"

    tied = select_convention(
        {"first": {"metric": 0.9}, "second": {"metric": 1.1}},
        anchors={"metric": 1.0},
        tolerances={"metric": 0.1},
        tie_break_order=["second", "first"],
    )
    assert tied.selected == "second"


def test_panel_conventions_use_source_defined_primary_columns():
    rng = np.random.default_rng(90)
    index = pd.period_range("1952Q4", periods=100, freq="Q")
    panel = pd.DataFrame(
        {
            "cay": rng.normal(size=100),
            "sp_real_return": rng.normal(size=100),
            "crsp_vw_real_return": rng.normal(size=100),
            "bill_30d_return": rng.normal(scale=0.01, size=100),
            "bill_3m_return": rng.normal(scale=0.01, size=100),
            "relative_bill_rate_30d": rng.normal(scale=0.01, size=100),
            "relative_bill_rate_3m": rng.normal(scale=0.01, size=100),
            "term_spread_10y_3m": rng.normal(scale=0.01, size=100),
            "term_spread_10y_1y": rng.normal(scale=0.01, size=100),
            "dividend_yield": rng.normal(size=100),
            "payout_ratio": rng.normal(size=100),
            "default_spread": rng.normal(scale=0.01, size=100),
        },
        index=index,
    )
    targets = {
        "table_iii": {
            "row_6": {"cay_coefficient": 0.0, "adjusted_r_squared": 0.0},
            "row_13": {
                "cay_coefficient": 0.0,
                "term_spread_coefficient": 0.0,
                "adjusted_r_squared": 0.0,
            },
        }
    }

    result = select_panel_conventions(panel, targets)

    assert result.risk_free.selected == "bill_30d"
    assert result.term_spread.selected == "term_10y_3m"
    assert set(result.risk_free.candidate_metrics) == {"bill_30d", "bill_3m"}
    assert set(result.term_spread.candidate_metrics) == {
        "term_10y_3m",
        "term_10y_1y",
    }
    assert "relative_bill_rate" in result.panel
    assert "term_spread" in result.panel
    np.testing.assert_allclose(
        result.panel["sp_excess_return"],
        result.panel["sp_real_return"] - result.panel["bill_30d_return"],
    )
    np.testing.assert_allclose(
        result.panel["relative_bill_rate"],
        result.panel["relative_bill_rate_30d"],
    )
    np.testing.assert_allclose(
        result.panel["term_spread"],
        result.panel["term_spread_10y_3m"],
    )
