"""Tests for distinct analysis modes and original diagnostics."""

import numpy as np
import pandas as pd

from src.analysis.figure_s1 import prepare_figure_s1
from src.analysis.modes import estimate_analysis_modes
from src.analysis.table_s1 import SUMMARY_VARIABLES, build_table_s1


def diagnostic_panel(periods: int = 210) -> pd.DataFrame:
    rng = np.random.default_rng(44)
    index = pd.period_range("1952Q4", periods=periods, freq="Q")
    trend = np.cumsum(rng.normal(scale=0.02, size=periods))
    c = trend + rng.normal(scale=0.02, size=periods)
    a = 1.5 * trend + rng.normal(scale=0.03, size=periods)
    y = 0.8 * trend + rng.normal(scale=0.02, size=periods)
    return pd.DataFrame(
        {
            "c": c,
            "a": a,
            "y": y,
            "paper_c": c[:periods] + 0.01,
            "paper_a": a[:periods] - 0.02,
            "paper_y": y[:periods] + 0.03,
            "posted_cay": c - 0.31 * a - 0.59 * y,
            "sp_excess_return": rng.normal(size=periods),
            "crsp_vw_excess_return": rng.normal(size=periods),
            "dividend_yield": rng.normal(size=periods),
            "payout_ratio": rng.normal(size=periods),
            "relative_bill_rate": rng.normal(size=periods),
            "term_spread": rng.normal(size=periods),
            "default_spread": rng.normal(size=periods),
            "cay": c - 0.25 * a - 0.65 * y,
            "nber_recession": (np.arange(periods) % 20 < 3).astype(int),
        },
        index=index,
    )


def test_analysis_modes_remain_separate_and_comparison_has_declared_columns():
    result = estimate_analysis_modes(diagnostic_panel(), leads_lags=2)

    assert result.historical_comparison.columns.tolist() == [
        "posted_cay",
        "cay_paper_inputs",
        "cay_current_vintage",
    ]
    assert len(result.historical_comparison) == 184
    assert len(result.updated.cay) == 210
    assert not result.paper_inputs.cay.equals(result.current_vintage_historical.cay)


def test_table_s1_has_coverage_and_both_summary_samples():
    result = build_table_s1(diagnostic_panel())

    assert result.coverage["variable"].tolist() == list(SUMMARY_VARIABLES)
    assert set(result.summary["sample"]) == {"historical", "updated"}
    assert len(result.summary) == 2 * len(SUMMARY_VARIABLES)
    assert "largest updated growth volatility" in result.takeaway
    assert "most persistent predictor" in result.takeaway


def test_figure_s1_indexes_first_common_quarter_and_has_two_panel_data_groups():
    result = prepare_figure_s1(diagnostic_panel())

    indexed = [column for column in result if column.endswith("_indexed")]
    growth = [column for column in result if column.endswith("_growth_4q")]
    assert len(indexed) == 3
    assert len(growth) == 3
    np.testing.assert_allclose(result[indexed].iloc[0], 100.0)
    assert result[growth].iloc[:4].isna().all().all()
