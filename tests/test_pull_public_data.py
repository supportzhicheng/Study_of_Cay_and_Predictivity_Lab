"""Tests for public FRED and BEA acquisition adapters."""

import pandas as pd
import pytest

from src.data.pull_bea import BeaComponent, build_bea_params, select_component_rows
from src.data.pull_fred import FRED_CSV_URL, fetch_fred_series


class FakeTextResponse:
    text = "DATE,GS10\n2000-01-01,6.66\n2000-02-01,.\n"

    def raise_for_status(self) -> None:
        return None


class FakeFredSession:
    def __init__(self):
        self.call = None

    def get(self, url, *, params, timeout):
        self.call = (url, params, timeout)
        return FakeTextResponse()


def test_fred_fetch_renames_series_at_boundary():
    session = FakeFredSession()

    result = fetch_fred_series(
        "GS10",
        "treasury_10y_yield",
        session=session,
        start_date="2000-01-01",
        end_date="2000-12-31",
    )

    assert result.name == "treasury_10y_yield"
    assert result.iloc[0] == 6.66
    assert pd.isna(result.iloc[1])
    assert session.call == (
        FRED_CSV_URL,
        {"id": "GS10", "cosd": "2000-01-01", "coed": "2000-12-31"},
        60,
    )


def test_bea_request_pins_dataset_table_frequency_and_all_years():
    component = BeaComponent("services", "NIPA", "T20306", "Services")

    params = build_bea_params(component, "test-key")

    assert params == {
        "UserID": "test-key",
        "method": "GetData",
        "datasetname": "NIPA",
        "TableName": "T20306",
        "Frequency": "Q",
        "Year": "X",
        "ResultFormat": "JSON",
    }


def test_bea_component_matching_is_exact_and_numeric():
    component = BeaComponent("services", "NIPA", "T20306", "Services")
    rows = [
        {"LineDescription": "Services", "TimePeriod": "2000Q2", "DataValue": "1,200.5"},
        {"LineDescription": "Other services", "TimePeriod": "2000Q1", "DataValue": "9"},
        {"LineDescription": "Services", "TimePeriod": "2000Q1", "DataValue": "1,100.0"},
    ]

    result = select_component_rows(rows, component)

    assert result.index.astype(str).tolist() == ["2000Q1", "2000Q2"]
    assert result.tolist() == [1100.0, 1200.5]


def test_bea_social_insurance_selects_current_aggregate_not_employer_rows():
    component = BeaComponent(
        "social_insurance",
        "NIPA",
        "T20100",
        "Less: Contributions for government social insurance, domestic",
    )
    rows = [
        {
            "LineDescription": "Employer contributions for government social insurance",
            "TimePeriod": "2000Q1",
            "DataValue": "4",
        },
        {
            "LineDescription": "Less: Contributions for government social insurance, domestic",
            "TimePeriod": "2000Q1",
            "DataValue": "10",
        },
    ]

    result = select_component_rows(rows, component)

    assert result.iloc[0] == 10.0


def test_bea_personal_taxes_selects_less_line():
    component = BeaComponent(
        "personal_taxes", "NIPA", "T20100", "Less: Personal current taxes"
    )
    rows = [
        {
            "LineDescription": "Less: Personal current taxes",
            "TimePeriod": "2000Q1",
            "DataValue": "12",
        }
    ]

    result = select_component_rows(rows, component)

    assert result.iloc[0] == 12.0


def test_bea_prefix_match_rejects_multiple_descriptions():
    component = BeaComponent(
        "social_insurance", "NIPA", "T20100", "Contributions", prefix_match=True
    )
    rows = [
        {
            "LineDescription": "Contributions A",
            "TimePeriod": "2000Q1",
            "DataValue": "1",
        },
        {
            "LineDescription": "Contributions B",
            "TimePeriod": "2000Q1",
            "DataValue": "2",
        },
    ]

    with pytest.raises(ValueError, match="exactly one BEA line"):
        select_component_rows(rows, component)
