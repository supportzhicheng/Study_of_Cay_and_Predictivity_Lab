"""Tests for CayDecomposer."""

import pytest

from cay_lab.analysis.decomposition import CayDecomposer
from cay_lab.data.loader import make_synthetic_dataset


@pytest.fixture
def df():
    return make_synthetic_dataset(n_periods=120, seed=1)


def test_fit_returns_self(df):
    d = CayDecomposer(df, cay_lags=0)
    assert d.fit() is d


def test_results_has_expected_rows(df):
    d = CayDecomposer(df, cay_lags=0).fit()
    # 7 subsets of {c,a,y} + 1 cay row
    assert len(d.results_) == 8


def test_shapley_sums_to_full_r2(df):
    """Sum of Shapley values should ≈ R² of full {c,a,y} model."""
    d = CayDecomposer(df, cay_lags=0).fit()
    full_r2 = d.results_.loc[d.results_["predictors"] == "a+c+y", "r_squared"].values[0]
    assert abs(d.shapley_.sum() - full_r2) < 1e-9


def test_shapley_components(df):
    d = CayDecomposer(df, cay_lags=0).fit()
    assert set(d.shapley_.index) == {"c", "a", "y"}


def test_summary_string(df):
    d = CayDecomposer(df, cay_lags=0).fit()
    s = d.summary()
    assert "Shapley" in s
    assert "R²" in s
