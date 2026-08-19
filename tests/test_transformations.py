"""Tests for quarterly macro, return, and predictor transformations."""

import numpy as np
import pandas as pd
import pytest

from src.data.normalize_sources import (
    allocate_labor_taxes,
    build_core_macro,
    build_crsp_market,
    build_rates,
    quarterly_last,
    quarterly_log_inflation,
    quarterly_max,
    quarterly_mean,
)


def test_frequency_conversions_use_declared_aggregations():
    index = pd.date_range("2000-01-31", periods=3, freq="ME")
    frame = pd.DataFrame({"value": [1.0, 3.0, 2.0]}, index=index)

    assert quarterly_last(frame).iloc[0, 0] == 2.0
    assert quarterly_mean(frame).iloc[0, 0] == 2.0
    assert quarterly_max(frame).iloc[0, 0] == 3.0


def test_labor_tax_allocation_formula():
    frame = pd.DataFrame(
        {
            "wages": [50.0],
            "proprietors_income": [10.0],
            "rental_income": [10.0],
            "dividend_income": [20.0],
            "interest_income": [10.0],
            "personal_taxes": [20.0],
        }
    )

    assert allocate_labor_taxes(frame).iloc[0] == 10.0


def test_core_macro_uses_declared_consumption_and_labor_formulas():
    index = pd.period_range("2000Q1", periods=1, freq="Q")
    bea = pd.DataFrame(
        {
            "nondurable_goods": [60.0],
            "services": [50.0],
            "clothing_footwear": [10.0],
            "wages": [50.0],
            "transfers": [10.0],
            "supplements": [10.0],
            "social_insurance": [5.0],
            "personal_taxes": [20.0],
            "proprietors_income": [10.0],
            "rental_income": [10.0],
            "dividend_income": [20.0],
            "interest_income": [10.0],
        },
        index=index,
    )
    fred = pd.DataFrame(
        {
            "household_net_worth": [1000.0],
            "pce_price_index": [2.0],
            "population_candidate": [10.0],
        },
        index=index,
    )

    result = build_core_macro(bea, fred)

    np.testing.assert_allclose(result.loc[index[0]], np.log([10.0, 50.0, 2.75]))


def test_core_macro_rejects_nonpositive_real_levels():
    index = pd.period_range("2000Q1", periods=1, freq="Q")
    bea = pd.DataFrame(
        {
            "nondurable_goods": [1.0],
            "services": [1.0],
            "clothing_footwear": [3.0],
            "wages": [10.0],
            "transfers": [0.0],
            "supplements": [0.0],
            "social_insurance": [0.0],
            "personal_taxes": [0.0],
            "proprietors_income": [1.0],
            "rental_income": [1.0],
            "dividend_income": [1.0],
            "interest_income": [1.0],
        },
        index=index,
    )
    fred = pd.DataFrame(
        {
            "household_net_worth": [100.0],
            "pce_price_index": [1.0],
            "population_candidate": [10.0],
        },
        index=index,
    )

    with pytest.raises(ValueError, match="must be positive"):
        build_core_macro(bea, fred)


def test_crsp_quarterly_log_compounding_and_real_returns():
    dates = pd.date_range("2000-01-31", periods=4, freq="ME")
    market = pd.DataFrame({"vwretd": [0.01, 0.02, 0.03, 0.04]}, index=dates)
    treasury = pd.DataFrame({"t30ret": [0.001, 0.002, 0.003, 0.004]}, index=dates)
    cpi = pd.Series([100.0, 101.0, 102.0, 104.0], index=dates)

    result = build_crsp_market(market, treasury, cpi)

    nominal_market_q1 = np.log1p([0.01, 0.02, 0.03]).sum()
    nominal_bill_q1 = np.log1p([0.001, 0.002, 0.003]).sum()
    inflation_q1 = np.log(102.0 / 100.0)
    assert result.loc[pd.Period("2000Q1"), "crsp_vw_real_return"] == pytest.approx(
        nominal_market_q1 - inflation_q1
    )
    assert result.loc[pd.Period("2000Q1"), "crsp_vw_excess_return"] == pytest.approx(
        nominal_market_q1 - nominal_bill_q1
    )


def test_quarterly_inflation_sums_monthly_log_changes():
    dates = pd.date_range("2000-01-31", periods=3, freq="ME")
    cpi = pd.Series([100.0, 101.0, 102.0], index=dates)

    result = quarterly_log_inflation(cpi)

    assert result.iloc[0] == pytest.approx(np.log(102.0 / 100.0))


def test_rate_candidates_and_four_quarter_relative_rates():
    index = pd.period_range("2000Q1", periods=5, freq="Q")
    fred = pd.DataFrame(
        {
            "tbill_3m_yield": [4.0] * 5,
            "treasury_1y_yield": [5.0] * 5,
            "treasury_10y_yield": [7.0] * 5,
            "baa_corporate_yield": [8.0] * 5,
            "aaa_corporate_yield": [6.0] * 5,
        },
        index=index,
    )
    inflation = pd.Series([0.005] * 5, index=index)
    nominal_30d = pd.Series([0.001, 0.002, 0.003, 0.004, 0.005], index=index)

    result = build_rates(fred, inflation, nominal_30d)

    assert result["relative_bill_rate_30d"].iloc[:3].isna().all()
    assert result["relative_bill_rate_30d"].iloc[3] == pytest.approx(0.0015)
    assert result["term_spread_10y_3m"].iloc[0] == pytest.approx(0.03)
    assert result["term_spread_10y_1y"].iloc[0] == pytest.approx(0.02)
    assert result["default_spread"].iloc[0] == pytest.approx(0.02)
    assert result["bill_3m_return"].iloc[0] == pytest.approx(
        0.25 * np.log1p(0.04) - 0.005
    )
