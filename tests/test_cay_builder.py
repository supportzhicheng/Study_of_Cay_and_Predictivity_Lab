"""Tests for CayBuilder (DOLS cointegration)."""

import numpy as np
import pytest

from cay_lab.analysis.cay_builder import CayBuilder
from cay_lab.data.loader import make_synthetic_dataset


@pytest.fixture
def df():
    return make_synthetic_dataset(n_periods=120, seed=0)


def test_fit_returns_self(df):
    builder = CayBuilder(df, lags=0)
    assert builder.fit() is builder


def test_cay_is_series(df):
    builder = CayBuilder(df, lags=0).fit()
    import pandas as pd

    assert isinstance(builder.cay, pd.Series)


def test_cay_length(df):
    builder = CayBuilder(df, lags=0).fit()
    # cay should cover the full df length
    assert len(builder.cay) == len(df)


def test_coef_keys(df):
    builder = CayBuilder(df, lags=1).fit()
    assert set(builder.coef_.keys()) == {"const", "beta_a", "beta_y"}


def test_reported_cay_does_not_subtract_intercept(df):
    builder = CayBuilder(df, lags=0).fit()
    expected = (
        df["c"] - builder.coef_["beta_a"] * df["a"] - builder.coef_["beta_y"] * df["y"]
    )
    np.testing.assert_allclose(builder.cay, expected)
    intercept_subtracted = expected - builder.coef_["const"]
    np.testing.assert_allclose(
        builder.cay - intercept_subtracted, builder.coef_["const"]
    )


def test_missing_columns_raises():
    import pandas as pd

    bad_df = pd.DataFrame({"c": [1, 2], "a": [1, 2]})  # missing 'y'
    with pytest.raises(ValueError, match="missing columns"):
        CayBuilder(bad_df)


def test_summary_string(df):
    builder = CayBuilder(df, lags=0).fit()
    s = builder.summary()
    assert "beta_a" in s
    assert "beta_y" in s


def test_dols_lags(df):
    builder = CayBuilder(df, lags=2).fit()
    assert builder.coef_ is not None


def test_dols_includes_contemporaneous_changes(df):
    builder = CayBuilder(df, lags=1).fit()

    assert "da_lag0" in builder.model_result_.model.exog_names
    assert "dy_lag0" in builder.model_result_.model.exog_names


def test_negative_lags_raise(df):
    with pytest.raises(ValueError, match="nonnegative"):
        CayBuilder(df, lags=-1)


def test_nonquarterly_index_raises(df):
    bad = df.copy()
    bad.index = bad.index.to_timestamp()

    with pytest.raises(ValueError, match="quarterly PeriodIndex"):
        CayBuilder(bad)
