"""Tests for normalized quarterly source contracts."""

import pandas as pd
import pytest

from src.data.contracts import normalize_quarterly_source
from src.data.source_registry import get_source_spec, required_panel_sources


def test_normalization_sorts_quarterly_labels():
    frame = pd.DataFrame(
        {
            "quarter": ["2000Q2", "2000Q1"],
            "c": [2.0, 1.0],
            "a": [4.0, 3.0],
            "y": [6.0, 5.0],
        }
    )

    result = normalize_quarterly_source(frame, "core_macro")

    assert isinstance(result.index, pd.PeriodIndex)
    assert result.index.tolist() == [pd.Period("2000Q1"), pd.Period("2000Q2")]
    assert result.index.name == "quarter"


def test_dates_are_converted_to_quarters():
    frame = pd.DataFrame(
        {
            "date": ["2000-03-31", "2000-06-30"],
            "nber_recession": [0, 1],
        }
    )

    result = normalize_quarterly_source(frame, "recessions")

    assert result.index.astype(str).tolist() == ["2000Q1", "2000Q2"]


def test_duplicate_converted_quarters_are_rejected():
    frame = pd.DataFrame(
        {
            "date": ["2000-01-31", "2000-03-31"],
            "nber_recession": [0, 1],
        }
    )

    with pytest.raises(ValueError, match="Duplicate quarters"):
        normalize_quarterly_source(frame, "recessions")


def test_missing_quarter_field_is_rejected():
    frame = pd.DataFrame({"nber_recession": [0, 1]})

    with pytest.raises(ValueError, match="quarter.*date"):
        normalize_quarterly_source(frame, "recessions")


def test_missing_required_column_is_rejected():
    frame = pd.DataFrame({"quarter": ["2000Q1"], "c": [1.0], "a": [2.0]})

    with pytest.raises(ValueError, match="missing required columns.*y"):
        normalize_quarterly_source(frame, "core_macro")


def test_nonnumeric_required_column_is_rejected():
    frame = pd.DataFrame({"quarter": ["2000Q1"], "c": ["bad"], "a": [2.0], "y": [3.0]})

    with pytest.raises(ValueError, match="column 'c' must be numeric"):
        normalize_quarterly_source(frame, "core_macro")


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="Unknown source"):
        get_source_spec("not_a_source")


def test_six_sources_are_required_and_posted_cay_is_optional():
    required = required_panel_sources()

    assert len(required) == 6
    assert "posted_cay" not in required
    assert get_source_spec("posted_cay").required_for_panel is False
