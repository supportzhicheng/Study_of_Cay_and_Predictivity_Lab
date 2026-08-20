"""Transform acquired source data into normalized quarterly contracts."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _require_datetime_index(frame: pd.DataFrame) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Monthly source data must use a DatetimeIndex.")


def quarterly_last(frame: pd.DataFrame) -> pd.DataFrame:
    """Take the last observed value in each calendar quarter."""
    _require_datetime_index(frame)
    result = frame.groupby(frame.index.to_period("Q")).last()
    result.index.name = "quarter"
    return result


def quarterly_mean(frame: pd.DataFrame) -> pd.DataFrame:
    """Average observed values within each calendar quarter."""
    _require_datetime_index(frame)
    result = frame.groupby(frame.index.to_period("Q")).mean()
    result.index.name = "quarter"
    return result


def quarterly_max(frame: pd.DataFrame) -> pd.DataFrame:
    """Take the maximum observed value in each calendar quarter."""
    _require_datetime_index(frame)
    result = frame.groupby(frame.index.to_period("Q")).max()
    result.index.name = "quarter"
    return result


def allocate_labor_taxes(frame: pd.DataFrame) -> pd.Series:
    """Allocate personal taxes to labor using the LL income-share formula."""
    capital_and_labor = (
        frame["wages"]
        + frame["proprietors_income"]
        + frame["rental_income"]
        + frame["dividend_income"]
        + frame["interest_income"]
    )
    if (capital_and_labor <= 0).any():
        raise ValueError("Labor-tax allocation denominator must be positive.")
    return (frame["personal_taxes"] * frame["wages"] / capital_and_labor).rename(
        "labor_taxes"
    )


def build_core_macro(bea: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    """Construct log real per-capita consumption, wealth, and labor income."""
    labor_taxes = allocate_labor_taxes(bea)
    labor_income = (
        bea["wages"]
        + bea["transfers"]
        + bea["supplements"]
        - bea["social_insurance"]
        - labor_taxes
    )

    joined = pd.concat(
        [
            labor_income.rename("labor_income"),
            fred[
                [
                    "total_real_pce",
                    "household_net_worth",
                    "pce_price_index",
                    "population_candidate",
                ]
            ],
        ],
        axis=1,
    )
    real_levels = pd.DataFrame(index=joined.index)
    pce_deflator = joined["pce_price_index"] / 100.0
    real_levels["c"] = joined["total_real_pce"] / joined["population_candidate"]
    real_levels["a"] = (
        joined["household_net_worth"] / pce_deflator / joined["population_candidate"]
    )
    real_levels["y"] = (
        joined["labor_income"] / pce_deflator / joined["population_candidate"]
    )
    if (real_levels <= 0).any().any():
        raise ValueError("Real per-capita macro levels must be positive.")
    return np.log(real_levels)


def quarterly_log_inflation(cpi: pd.Series) -> pd.Series:
    """Sum monthly log CPI inflation within each quarter."""
    if not isinstance(cpi.index, pd.DatetimeIndex):
        raise ValueError("CPI must use a DatetimeIndex.")
    if (cpi <= 0).any():
        raise ValueError("CPI values must be positive.")
    monthly = np.log(cpi).diff()
    result = monthly.groupby(monthly.index.to_period("Q")).sum(min_count=1)
    result.index.name = "quarter"
    return result.rename("inflation")


def build_crsp_market(
    market: pd.DataFrame, treasury: pd.DataFrame, cpi: pd.Series
) -> pd.DataFrame:
    """Construct quarterly CRSP real, excess, and real 30-day bill returns."""
    market_monthly = np.log1p(pd.to_numeric(market["vwretd"], errors="coerce"))
    bill_monthly = np.log1p(pd.to_numeric(treasury["t30ret"], errors="coerce"))
    market_quarterly = market_monthly.groupby(market.index.to_period("Q")).sum(
        min_count=1
    )
    bill_quarterly = bill_monthly.groupby(treasury.index.to_period("Q")).sum(
        min_count=1
    )
    inflation = quarterly_log_inflation(cpi)
    result = pd.concat(
        [market_quarterly.rename("market"), bill_quarterly.rename("bill"), inflation],
        axis=1,
    )
    return pd.DataFrame(
        {
            "crsp_vw_real_return": result["market"] - result["inflation"],
            "crsp_vw_excess_return": result["market"] - result["bill"],
            "bill_30d_return": result["bill"] - result["inflation"],
        }
    )


def relative_bill_rate(nominal_rate: pd.Series) -> pd.Series:
    """Subtract the prior four-quarter mean from the current nominal rate."""
    prior_mean = nominal_rate.shift(1).rolling(4, min_periods=4).mean()
    return (nominal_rate - prior_mean).rename(nominal_rate.name)


def build_rates(
    fred_quarterly: pd.DataFrame,
    inflation: pd.Series,
    nominal_bill_30d: pd.Series,
) -> pd.DataFrame:
    """Construct both retained bill-rate and term-spread candidates."""
    yields = (
        fred_quarterly[
            [
                "tbill_3m_yield",
                "treasury_1y_yield",
                "treasury_10y_yield",
                "baa_corporate_yield",
                "aaa_corporate_yield",
            ]
        ]
        / 100.0
    )
    nominal_bill_3m = 0.25 * np.log1p(yields["tbill_3m_yield"])
    return pd.DataFrame(
        {
            "bill_3m_return": nominal_bill_3m - inflation,
            "relative_bill_rate_30d": relative_bill_rate(nominal_bill_30d),
            "relative_bill_rate_3m": relative_bill_rate(nominal_bill_3m),
            "term_spread_10y_3m": yields["treasury_10y_yield"]
            - yields["tbill_3m_yield"],
            "term_spread_10y_1y": yields["treasury_10y_yield"]
            - yields["treasury_1y_yield"],
            "default_spread": yields["baa_corporate_yield"]
            - yields["aaa_corporate_yield"],
        }
    )


def build_shiller_market(
    shiller: pd.DataFrame, real_bill_30d: pd.Series
) -> pd.DataFrame:
    """Construct quarterly S&P fallback returns and valuation ratios."""
    _require_datetime_index(shiller)
    if (shiller[["P", "D", "E", "CPI"]] <= 0).any().any():
        raise ValueError("Shiller price, dividend, earnings, and CPI must be positive.")

    nominal_total_return = np.log(
        (shiller["P"] + shiller["D"] / 12.0) / shiller["P"].shift(1)
    )
    inflation = np.log(shiller["CPI"]).diff()
    quarter = shiller.index.to_period("Q")
    nominal_quarterly = nominal_total_return.groupby(quarter).sum(min_count=1)
    inflation_quarterly = inflation.groupby(quarter).sum(min_count=1)

    trailing_dividends = (shiller["D"] / 12.0).rolling(12, min_periods=12).sum()
    quarterly_earnings = (shiller["E"] / 12.0).groupby(quarter).sum(min_count=3)
    quarter_end = shiller.groupby(quarter).last()
    dividend_yield = np.log(trailing_dividends.groupby(quarter).last()) - np.log(
        quarter_end["P"]
    )
    payout_ratio = np.log(trailing_dividends.groupby(quarter).last()) - np.log(
        quarterly_earnings
    )

    real_return = nominal_quarterly - inflation_quarterly
    return pd.DataFrame(
        {
            "sp_real_return": real_return,
            "sp_excess_return": real_return - real_bill_30d,
            "dividend_yield": dividend_yield,
            "payout_ratio": payout_ratio,
        }
    )
