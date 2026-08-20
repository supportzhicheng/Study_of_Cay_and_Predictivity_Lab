"""Tests for extension source builder parsing."""

import csv

from src.data.build_extension_s14 import _read_series, _to_float


def test_z1_availability_markers_are_missing_values():
    assert _to_float("") is None
    assert _to_float("ND") is None
    assert _to_float("NA") is None
    assert _to_float("1.25") == 1.25


def test_z1_wide_table_layout_is_transposed(tmp_path):
    path = tmp_path / "S1M_b.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "SERIES_A.Q", "SERIES_B.Q"])
        writer.writerow(["2000:Q1", "1.0", "ND"])
        writer.writerow(["2000:Q2", "2.0", "3.0"])

    quarters, series = _read_series(path)

    assert quarters == ["2000Q1", "2000Q2"]
    assert series == {"SERIES_A.Q": [1.0, 2.0], "SERIES_B.Q": [None, 3.0]}
