"""Tests for licensed CRSP and public Shiller acquisition adapters."""

import pandas as pd
import pytest

from src.data.pull_shiller import (
    SHILLER_WORKBOOK_URL,
    normalize_shiller_frame,
    parse_shiller_month,
)
from src.data.pull_wrds import (
    MARKET_TABLE_CANDIDATES,
    build_select_query,
    discover_table,
    validate_table_name,
)


class FakeWrdsConnection:
    def __init__(self, tables: dict[str, list[str]]):
        self.tables = tables
        self.calls: list[str] = []

    def list_tables(self, library: str) -> list[str]:
        self.calls.append(library)
        return self.tables.get(library, [])


def test_wrds_discovers_first_available_candidate():
    connection = FakeWrdsConnection({"crsp": [], "crspm": ["msi"]})

    result = discover_table(connection, MARKET_TABLE_CANDIDATES)

    assert result == "crspm.msi"
    assert connection.calls == ["crsp", "crspm"]


def test_wrds_rejects_unsafe_table_name():
    with pytest.raises(ValueError, match="Unsafe WRDS table"):
        validate_table_name("crsp.msi; DROP TABLE users")


def test_wrds_query_uses_only_declared_fields():
    assert build_select_query("crsp.msi", ("date", "vwretd")) == (
        "SELECT date, vwretd FROM crsp.msi"
    )
    with pytest.raises(ValueError, match="field list"):
        build_select_query("crsp.msi", ("date; DELETE",))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1871.01, "1871-01-01"), (1871.1, "1871-10-01"), (2000.12, "2000-12-01")],
)
def test_shiller_month_parsing(raw, expected):
    assert parse_shiller_month(raw) == pd.Timestamp(expected)


def test_shiller_month_rejects_invalid_month():
    with pytest.raises(ValueError, match="Invalid Shiller month"):
        parse_shiller_month(2000.13)


def test_shiller_workbook_uses_reachable_official_http_endpoint():
    assert SHILLER_WORKBOOK_URL == "http://www.econ.yale.edu/~shiller/data/ie_data.xls"


def test_shiller_frame_requires_market_and_cpi_columns():
    raw = pd.DataFrame({"Date": [2000.01], "P": [100], "D": [2], "E": [4]})

    with pytest.raises(ValueError, match="missing required columns.*CPI"):
        normalize_shiller_frame(raw)


def test_shiller_frame_normalizes_monthly_index_and_numeric_values():
    raw = pd.DataFrame(
        {
            "Date": [2000.02, 2000.01],
            "P": ["101", "100"],
            "D": ["2.1", "2.0"],
            "E": ["4.1", "4.0"],
            "CPI": ["170", "169"],
        }
    )

    result = normalize_shiller_frame(raw)

    assert result.index.tolist() == [
        pd.Timestamp("2000-01-01"),
        pd.Timestamp("2000-02-01"),
    ]
    assert result.columns.tolist() == ["P", "D", "E", "CPI"]
    assert result.loc[pd.Timestamp("2000-01-01"), "P"] == 100
