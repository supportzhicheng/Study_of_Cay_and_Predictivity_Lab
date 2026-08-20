"""Tests for all Table III and Table VI specifications and timing."""

import numpy as np
import pandas as pd

from src.analysis.table_iii import (
    TABLE_III_SPECS,
    build_table_iii,
    prepare_table_iii_model,
)
from src.analysis.table_vi import HORIZONS, TABLE_VI_SPECS, build_table_vi


def forecasting_panel(periods: int = 140) -> pd.DataFrame:
    rng = np.random.default_rng(12)
    index = pd.period_range("1952Q4", periods=periods, freq="Q")
    cay = rng.normal(size=periods)
    sp_excess = 0.1 * cay + rng.normal(size=periods)
    return pd.DataFrame(
        {
            "c": np.cumsum(rng.normal(scale=0.01, size=periods)),
            "cay": cay,
            "sp_real_return": sp_excess + 0.01,
            "crsp_vw_real_return": sp_excess + rng.normal(scale=0.1, size=periods),
            "sp_excess_return": sp_excess,
            "crsp_vw_excess_return": sp_excess + rng.normal(scale=0.1, size=periods),
            "dividend_yield": rng.normal(size=periods),
            "payout_ratio": rng.normal(size=periods),
            "relative_bill_rate": rng.normal(scale=0.01, size=periods),
            "term_spread": rng.normal(scale=0.01, size=periods),
            "default_spread": rng.normal(scale=0.01, size=periods),
        },
        index=index,
    )


def test_table_iii_has_all_thirteen_rows():
    result = build_table_iii(forecasting_panel())

    assert result["row"].drop_duplicates().tolist() == list(range(1, 14))
    assert len(TABLE_III_SPECS) == 13
    assert result.groupby("row")["observations"].first().gt(0).all()
    assert result["hac_lags"].eq(1).all()


def test_table_iii_lagged_return_is_current_return_at_t():
    panel = forecasting_panel()
    spec = TABLE_III_SPECS[0]

    outcome, predictors = prepare_table_iii_model(panel, spec)

    pd.testing.assert_series_equal(
        predictors["lagged_return"], panel["sp_real_return"], check_names=False
    )
    assert outcome.iloc[0] == panel["sp_real_return"].iloc[1]


def test_table_iii_row_thirteen_uses_declared_later_start():
    panel = forecasting_panel()
    outcome, predictors = prepare_table_iii_model(panel, TABLE_III_SPECS[-1])

    assert outcome.index.min() == pd.Period("1953Q2")
    assert predictors.index.min() == pd.Period("1953Q2")


def test_table_iii_row_thirteen_has_181_historical_observations():
    result = build_table_iii(forecasting_panel(periods=184))
    row_13 = result[result["row"] == 13]

    assert row_13["sample_start"].unique().tolist() == ["1953Q2"]
    assert row_13["observations"].unique().tolist() == [181]


def test_table_vi_has_all_48_specification_horizon_models():
    result = build_table_vi(forecasting_panel())
    models = result[["specification", "horizon"]].drop_duplicates()

    assert len(TABLE_VI_SPECS) == 6
    assert tuple(HORIZONS) == (1, 2, 3, 4, 8, 12, 16, 24)
    assert len(models) == 48


def test_table_vi_hac_bandwidth_covers_every_overlap():
    result = build_table_vi(forecasting_panel())

    expected = result["horizon"].map(lambda horizon: max(1, horizon - 1))
    pd.testing.assert_series_equal(
        result["hac_lags"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )
