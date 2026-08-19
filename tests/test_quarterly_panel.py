"""Tests for normalized panel assembly, historical coverage, and endpoints."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.build_quarterly_panel import (
    build_quarterly_panel,
    latest_common_quarter,
    validate_historical_sample,
    write_quarterly_panel,
)
from src.data.normalize_sources import build_shiller_market


def source_frames(index: pd.PeriodIndex) -> dict[str, pd.DataFrame]:
    def frame(**columns):
        return pd.DataFrame({"quarter": index.astype(str), **columns})

    size = len(index)
    return {
        "paper_macro": frame(
            paper_c=np.arange(size),
            paper_a=np.arange(size),
            paper_y=np.arange(size),
            posted_cay=np.arange(size),
        ),
        "core_macro": frame(c=np.arange(size), a=np.arange(size), y=np.arange(size)),
        "sp_market": frame(
            sp_real_return=np.zeros(size),
            sp_excess_return=np.zeros(size),
            dividend_yield=np.zeros(size),
            payout_ratio=np.zeros(size),
        ),
        "crsp_market": frame(
            crsp_vw_real_return=np.zeros(size),
            crsp_vw_excess_return=np.zeros(size),
            bill_30d_return=np.zeros(size),
        ),
        "rates": frame(
            bill_3m_return=np.zeros(size),
            relative_bill_rate_30d=np.zeros(size),
            relative_bill_rate_3m=np.zeros(size),
            term_spread_10y_3m=np.zeros(size),
            term_spread_10y_1y=np.zeros(size),
            default_spread=np.zeros(size),
        ),
        "recessions": frame(nber_recession=np.zeros(size)),
    }


def test_shiller_market_builds_real_excess_returns_and_ratios():
    dates = pd.date_range("1999-01-31", periods=15, freq="ME")
    shiller = pd.DataFrame(
        {
            "P": np.linspace(100, 114, 15),
            "D": np.full(15, 12.0),
            "E": np.full(15, 24.0),
            "CPI": np.linspace(100, 103, 15),
        },
        index=dates,
    )
    bill = pd.Series(0.001, index=pd.period_range("1999Q1", "2000Q1", freq="Q"))

    result = build_shiller_market(shiller, bill)

    assert result.columns.tolist() == [
        "sp_real_return",
        "sp_excess_return",
        "dividend_yield",
        "payout_ratio",
    ]
    complete = result.dropna()
    np.testing.assert_allclose(
        complete["sp_real_return"] - complete["sp_excess_return"], 0.001
    )


def test_panel_requires_all_six_source_families():
    sources = source_frames(pd.period_range("2000Q1", periods=2, freq="Q"))
    del sources["rates"]

    with pytest.raises(ValueError, match="Missing required source families.*rates"):
        build_quarterly_panel(sources)


def test_optional_posted_cay_is_renamed_and_growth_is_added():
    index = pd.period_range("2000Q1", periods=2, freq="Q")
    sources = source_frames(index)
    sources["posted_cay"] = pd.DataFrame(
        {"quarter": index.astype(str), "cay": [1.0, 2.0]}
    )

    panel = build_quarterly_panel(sources)

    assert "posted_cay_updated" in panel
    assert "cay" not in panel
    assert pd.isna(panel["consumption_growth"].iloc[0])
    assert panel["consumption_growth"].iloc[1] == 1.0


def test_historical_sample_requires_exact_184_quarters_and_complete_values():
    index = pd.period_range("1952Q4", "1998Q3", freq="Q")
    panel = build_quarterly_panel(source_frames(index))

    historical = validate_historical_sample(panel, ["c", "a", "y"])

    assert len(historical) == 184
    with pytest.raises(ValueError, match="missing quarters"):
        validate_historical_sample(panel.drop(index[10]), ["c", "a", "y"])


def test_latest_common_quarter_does_not_fill_missing_endpoint():
    index = pd.period_range("2000Q1", periods=4, freq="Q")
    panel = pd.DataFrame(
        {"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 2.0, np.nan, np.nan]}, index=index
    )

    assert latest_common_quarter(panel, ["a", "b"]) == pd.Period("2000Q2")


def test_panel_writer_records_hash_and_source_vintages(tmp_path: Path):
    index = pd.period_range("2000Q1", periods=2, freq="Q")
    panel = build_quarterly_panel(source_frames(index))

    data_path, metadata_path = write_quarterly_panel(
        panel, tmp_path, source_vintages={"core_macro": "2026-08-18"}
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert data_path.exists()
    assert metadata["sample_start"] == "2000Q1"
    assert metadata["sample_end"] == "2000Q2"
    assert metadata["source_vintages"] == {"core_macro": "2026-08-18"}
    assert len(metadata["sha256"]) == 64
