"""Tests for pinned author-data acquisition and parsing."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.pull_author_cay import (
    HISTORICAL_AUTHOR_URL,
    UPDATED_AUTHOR_URL,
    ensure_author_data,
    parse_historical_author_data,
    parse_updated_author_cay,
    pull_author_data,
)


def historical_text() -> str:
    quarters = pd.period_range("1952Q4", "1998Q3", freq="Q")
    return "\n".join(
        f"{quarter} {index + 1}.0 {index + 2}.0 {index + 3}.0 {index + 4}.0"
        for index, quarter in enumerate(quarters)
    )


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, *, timeout: int) -> FakeResponse:
        self.calls.append((url, timeout))
        return FakeResponse(self.responses[url])


def test_historical_parser_enforces_exact_paper_window():
    result = parse_historical_author_data(historical_text())

    assert len(result) == 184
    assert result["quarter"].iloc[0] == "1952Q4"
    assert result["quarter"].iloc[-1] == "1998Q3"
    assert result.columns.tolist() == [
        "quarter",
        "paper_c",
        "paper_a",
        "paper_y",
        "posted_cay",
    ]


def test_historical_parser_rejects_incomplete_window():
    incomplete = "\n".join(historical_text().splitlines()[:-1])

    with pytest.raises(ValueError, match="exactly 184"):
        parse_historical_author_data(incomplete)


def test_historical_parser_converts_missing_sentinel():
    lines = historical_text().splitlines()
    lines[0] = "1952Q4 -99.0 2.0 3.0 4.0"

    result = parse_historical_author_data("\n".join(lines))

    assert pd.isna(result.loc[0, "paper_c"])


def test_historical_parser_handles_live_comments_dates_and_extra_terminal_row():
    live_layout = "\n".join(
        [
            "@ Data used in the paper @",
            *[
                line.replace(str(quarter), f"{quarter.year}0{quarter.quarter}")
                for line, quarter in zip(
                    historical_text().splitlines(),
                    pd.period_range("1952Q4", "1998Q3", freq="Q"),
                    strict=True,
                )
            ],
            "199804 -99 11.6 -99 -99",
        ]
    )

    result = parse_historical_author_data(live_layout)

    assert len(result) == 184
    assert result["quarter"].iloc[-1] == "1998Q3"


def test_updated_parser_keeps_only_validation_cay():
    result = parse_updated_author_cay(
        "1952Q1 1.0 2.0 3.0 4.0 5.0\n1952Q2 6.0 7.0 8.0 9.0 10.0"
    )

    assert result.columns.tolist() == ["quarter", "cay"]
    assert result["cay"].tolist() == [4.0, 9.0]


def test_updated_parser_handles_live_comment_block_and_six_digit_dates():
    result = parse_updated_author_cay(
        "/* CAY Data */\n date c a y cay cayMS */\n195201 1 2 3 4 5"
    )

    assert result.to_dict(orient="records") == [{"quarter": "1952Q1", "cay": 4}]


def test_pull_uses_pinned_urls_and_writes_both_caches(tmp_path: Path):
    session = FakeSession(
        {
            HISTORICAL_AUTHOR_URL: historical_text(),
            UPDATED_AUTHOR_URL: "1952Q1 1.0 2.0 3.0 4.0 5.0",
        }
    )

    historical_paths, updated_paths = pull_author_data(
        tmp_path, session=session, vintage="2026-08-18"
    )

    assert historical_paths.data.exists()
    assert updated_paths.data.exists()
    assert session.calls == [
        (HISTORICAL_AUTHOR_URL, 60),
        (UPDATED_AUTHOR_URL, 60),
    ]


def test_ensure_author_data_reuses_valid_caches_without_network(tmp_path: Path):
    initial_session = FakeSession(
        {
            HISTORICAL_AUTHOR_URL: historical_text(),
            UPDATED_AUTHOR_URL: "1952Q1 1.0 2.0 3.0 4.0 5.0",
        }
    )
    expected = pull_author_data(tmp_path, session=initial_session, vintage="2026-08-18")
    offline_session = FakeSession({})

    actual = ensure_author_data(tmp_path, session=offline_session, vintage="2026-08-18")

    assert actual == expected
    assert offline_session.calls == []
