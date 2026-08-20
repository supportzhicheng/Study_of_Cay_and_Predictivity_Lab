"""Tests for the credentialed real-data bootstrap orchestration."""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest

import src.bootstrap_real_data as bootstrap


def test_pull_wrds_uses_configured_username_and_closes(monkeypatch, tmp_path):
    connection = SimpleNamespace(close=lambda: closed.append(True))
    connection_kwargs = {}
    closed: list[bool] = []
    pulled: list[tuple[object, object]] = []

    def connect(**kwargs):
        connection_kwargs.update(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "wrds", SimpleNamespace(Connection=connect))
    monkeypatch.setattr(
        bootstrap,
        "pull_wrds_data",
        lambda active_connection, raw_dir: pulled.append((active_connection, raw_dir)),
    )
    settings = SimpleNamespace(wrds_username="test-user", wrds_password=None)

    bootstrap._pull_wrds(settings, tmp_path)

    assert connection_kwargs == {
        "wrds_username": "test-user",
        "wrds_password": "",
    }
    assert pulled == [(connection, tmp_path / "wrds")]
    assert closed == [True]


def _settings(tmp_path):
    return SimpleNamespace(
        wrds_username="test-user",
        wrds_password=None,
        bea_api_key="test-key",
        start_date="1952-01-01",
        end_date="2025-12-31",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        create_directories=lambda: None,
    )


def _patch_bootstrap_steps(monkeypatch, calls):
    def record(name):
        return lambda *args, **kwargs: calls.append(name)

    monkeypatch.setattr(bootstrap, "ensure_author_data", record("author data"))
    monkeypatch.setattr(bootstrap, "pull_fred_data", record("FRED data"))
    monkeypatch.setattr(bootstrap, "pull_bea_data", record("BEA data"))
    monkeypatch.setattr(bootstrap, "pull_shiller_data", record("Shiller data"))
    monkeypatch.setattr(bootstrap, "_pull_wrds", record("WRDS data"))
    monkeypatch.setattr(
        bootstrap, "normalize_pulled_sources", record("source normalization")
    )
    monkeypatch.setattr(bootstrap, "build_panel", record("panel build"))
    monkeypatch.setattr(bootstrap, "generate_exhibits", record("exhibit generation"))


def test_bootstrap_runs_steps_sequentially_and_logs_progress(
    monkeypatch, tmp_path, caplog
):
    calls = []
    _patch_bootstrap_steps(monkeypatch, calls)
    caplog.set_level(logging.INFO, logger=bootstrap.__name__)

    bootstrap.bootstrap_real_data(_settings(tmp_path))

    expected = [
        "author data",
        "FRED data",
        "BEA data",
        "Shiller data",
        "WRDS data",
        "source normalization",
        "panel build",
        "exhibit generation",
    ]
    assert calls == expected
    messages = [record.getMessage() for record in caplog.records]
    for name in expected:
        assert f"Starting {name}" in messages
        assert any(message.startswith(f"Completed {name} in ") for message in messages)


def test_bootstrap_reuses_complete_raw_caches(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    for relative in (
        "fred/fred_inputs.parquet",
        "bea/bea_components.parquet",
        "shiller/shiller_monthly.parquet",
        "wrds/crsp_market_monthly.parquet",
        "wrds/crsp_treasury_monthly.parquet",
    ):
        path = settings.data_dir / "raw" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    calls = []
    _patch_bootstrap_steps(monkeypatch, calls)

    bootstrap.bootstrap_real_data(settings)

    assert calls == [
        "author data",
        "source normalization",
        "panel build",
        "exhibit generation",
    ]


def test_bootstrap_stops_after_acquisition_failure(monkeypatch, tmp_path, caplog):
    calls = []
    _patch_bootstrap_steps(monkeypatch, calls)

    def fail_fred(*args, **kwargs):
        calls.append("FRED data")
        raise RuntimeError("FRED unavailable")

    monkeypatch.setattr(bootstrap, "pull_fred_data", fail_fred)
    caplog.set_level(logging.INFO, logger=bootstrap.__name__)

    with pytest.raises(RuntimeError, match="FRED unavailable"):
        bootstrap.bootstrap_real_data(_settings(tmp_path))

    assert calls == ["author data", "FRED data"]
    assert any(
        record.getMessage().startswith("Failed FRED data after ")
        for record in caplog.records
    )
