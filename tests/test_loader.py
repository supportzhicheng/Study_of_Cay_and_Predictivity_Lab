"""Tests for data loader utilities."""

import numpy as np
import pandas as pd
import pytest

from src.extension.loader import (
    load_cay_decomposition,
    log_transform,
    prepare_predictivity_dataset,
)
from tests.synthetic import make_synthetic_dataset


@pytest.fixture
def wealth_group_data(tmp_path):
    quarters = pd.period_range("1990Q1", "2000Q4", freq="Q")
    rows = []
    for group_index, group in enumerate(("bottom50", "middle40", "top10"), 1):
        for period_index, quarter in enumerate(quarters, 1):
            base = 100 + 10 * group_index + period_index
            rows.append(
                {
                    "quarter": str(quarter),
                    "wealth_group": group,
                    "housing_wealth_million_usd": base,
                    "financial_wealth_million_usd": 2 * base,
                    "liquid_assets_million_usd": 0.5 * base,
                }
            )
    pd.DataFrame(rows).to_csv(
        tmp_path / "cay_components_wealth_groups_q.csv", index=False
    )
    return tmp_path


def test_synthetic_dataset_shape():
    df = make_synthetic_dataset(n_periods=100)
    assert df.shape == (100, 4)
    assert list(df.columns) == ["c", "a", "y", "er"]


def test_synthetic_dataset_no_nan():
    df = make_synthetic_dataset(n_periods=80)
    assert not df.isnull().any().any()


def test_synthetic_dataset_index_type():
    df = make_synthetic_dataset(n_periods=50)
    assert isinstance(df.index, pd.PeriodIndex)


def test_synthetic_dataset_seed_reproducibility():
    df1 = make_synthetic_dataset(seed=7)
    df2 = make_synthetic_dataset(seed=7)
    pd.testing.assert_frame_equal(df1, df2)


def test_log_transform_applies_log():
    df = make_synthetic_dataset(n_periods=40)
    # Shift to positive before log
    df["c"] = df["c"] - df["c"].min() + 1
    df["a"] = df["a"] - df["a"].min() + 1
    df["y"] = df["y"] - df["y"].min() + 1
    out = log_transform(df, cols=["c"])
    assert np.allclose(out["c"], np.log(df["c"]))
    # Other columns unchanged
    pd.testing.assert_series_equal(out["a"], df["a"])


def test_load_cay_decomposition_wealth_groups(wealth_group_data):
    df = load_cay_decomposition(
        dataset="wealth_groups",
        component_data_dir=wealth_group_data,
        start="1990Q1",
        end="1991Q4",
    )
    assert isinstance(df.index, pd.PeriodIndex)
    assert df.index.freqstr == "Q-DEC"
    assert "wealth_group" in df.columns
    assert "housing_wealth_million_usd" in df.columns


def test_prepare_predictivity_dataset_has_subcay_and_target(wealth_group_data):
    df = prepare_predictivity_dataset(
        dataset="wealth_groups",
        component_data_dir=wealth_group_data,
        train_periods=20,
        prediction_window=1,
        min_history_periods=4,
        start="1990Q1",
        end="2000Q4",
    )
    required = {
        "segment",
        "target_future_growth",
        "sub_cay_housing",
        "sub_cay_financial",
        "sub_cay_liquid",
    }
    assert required.issubset(set(df.columns))
    assert (
        not df[
            [
                "target_future_growth",
                "sub_cay_housing",
                "sub_cay_financial",
                "sub_cay_liquid",
            ]
        ]
        .isna()
        .any()
        .any()
    )
    assert df.attrs["train_periods"] == 20
    assert df.attrs["prediction_window"] == 1


def test_prepare_predictivity_dataset_invalid_train_periods():
    with pytest.raises(ValueError, match="train_periods must be positive"):
        prepare_predictivity_dataset(dataset="wealth_groups", train_periods=0)
