"""Tests for Table II and Figure 1 data contracts."""

import numpy as np
import pandas as pd

from src.analysis.figure_1 import prepare_figure_1
from src.analysis.table_ii import TABLE_II_VARIABLES, build_table_ii


def exhibit_panel() -> pd.DataFrame:
    index = pd.period_range("1952Q4", periods=40, freq="Q")
    values = np.arange(40, dtype=float)
    return pd.DataFrame(
        {
            "sp_excess_return": np.sin(values),
            "dividend_yield": values / 100,
            "payout_ratio": np.cos(values),
            "relative_bill_rate": values / 200,
            "cay": np.sin(values / 3),
            "nber_recession": (values % 7 == 0).astype(int),
        },
        index=index,
    )


def test_table_ii_has_full_correlation_and_summary_shapes():
    result = build_table_ii(exhibit_panel())

    assert result.correlations.shape == (5, 5)
    assert result.correlations.index.tolist() == list(TABLE_II_VARIABLES)
    assert result.summary.shape == (5, 4)
    assert result.summary["observations"].eq(40).all()
    assert result.sample_start == pd.Period("1952Q4")


def test_figure_1_standardizes_over_displayed_complete_sample():
    panel = exhibit_panel()
    panel.loc[pd.Period("1953Q1"), "cay"] = np.nan

    result = prepare_figure_1(panel)

    assert pd.Period("1953Q1") not in result.index
    for column in ("cay", "sp_excess_return"):
        assert abs(result[column].mean()) < 1e-12
        assert abs(result[column].std(ddof=1) - 1.0) < 1e-12
    assert set(result["nber_recession"].unique()) <= {0, 1}
