"""Tests for RollingPredictivityMonitor."""

import pytest

from cay_lab.analysis.cay_builder import CayBuilder
from cay_lab.data.loader import make_synthetic_dataset
from cay_lab.monitor.rolling_monitor import RollingPredictivityMonitor


@pytest.fixture
def df_with_cay():
    df = make_synthetic_dataset(n_periods=120, seed=42)
    builder = CayBuilder(df, lags=0).fit()
    df["cay"] = builder.cay
    return df


def test_run_returns_self(df_with_cay):
    monitor = RollingPredictivityMonitor(
        df_with_cay, target_col="er", predictor_col="cay", window=30
    )
    assert monitor.run() is monitor


def test_rolling_results_shape(df_with_cay):
    monitor = RollingPredictivityMonitor(
        df_with_cay, target_col="er", predictor_col="cay", window=30
    )
    monitor.run()
    res = monitor.rolling_results_
    # Expect (n - window + 1) rows
    assert len(res) > 0
    assert set(res.columns) >= {"end_date", "t_stat", "r_squared", "n_obs", "status"}


def test_status_is_valid(df_with_cay):
    monitor = RollingPredictivityMonitor(
        df_with_cay, target_col="er", predictor_col="cay", window=30
    )
    monitor.run()
    valid = {
        RollingPredictivityMonitor.STATUS_ACTIVE,
        RollingPredictivityMonitor.STATUS_WEAKENED,
        RollingPredictivityMonitor.STATUS_LOST,
    }
    assert monitor.status() in valid


def test_expanding_window(df_with_cay):
    monitor = RollingPredictivityMonitor(
        df_with_cay, target_col="er", predictor_col="cay", window=None
    )
    monitor.run()
    assert len(monitor.rolling_results_) > 0


def test_latest_summary_keys(df_with_cay):
    monitor = RollingPredictivityMonitor(
        df_with_cay, target_col="er", predictor_col="cay", window=30
    )
    monitor.run()
    summary = monitor.latest_summary()
    assert "status" in summary
    assert "t_stat" in summary
    assert "r_squared" in summary
