"""Tests for the credentialed real-data bootstrap orchestration."""

from __future__ import annotations

import logging
import sys
import threading
from types import SimpleNamespace

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
        lambda active_connection, raw_dir: pulled.append(
            (active_connection, raw_dir)
        ),
    )
    settings = SimpleNamespace(wrds_username="test-user")

    bootstrap._pull_wrds(settings, tmp_path)

    assert connection_kwargs == {"wrds_username": "test-user"}
    assert pulled == [(connection, tmp_path / "wrds")]
    assert closed == [True]


def test_bootstrap_runs_acquisitions_concurrently_and_logs_progress(
    monkeypatch, tmp_path, caplog
):
    acquisition_names = {
        "author data",
        "FRED data",
        "BEA data",
        "Shiller data",
        "WRDS data",
    }
    started: set[str] = set()
    release = threading.Event()
    lock = threading.Lock()
    downstream_steps: list[str] = []

    def acquire(name: str) -> None:
        with lock:
            started.add(name)
            if started == acquisition_names:
                release.set()
        assert release.wait(timeout=2), "acquisition steps did not run concurrently"

    monkeypatch.setattr(
        bootstrap, "ensure_author_data", lambda *args, **kwargs: acquire("author data")
    )
    monkeypatch.setattr(
        bootstrap, "pull_fred_data", lambda *args, **kwargs: acquire("FRED data")
    )
    monkeypatch.setattr(
        bootstrap, "pull_bea_data", lambda *args, **kwargs: acquire("BEA data")
    )
    monkeypatch.setattr(
        bootstrap,
        "pull_shiller_data",
        lambda *args, **kwargs: acquire("Shiller data"),
    )
    monkeypatch.setattr(
        bootstrap, "_pull_wrds", lambda *args, **kwargs: acquire("WRDS data")
    )
    monkeypatch.setattr(
        bootstrap,
        "normalize_pulled_sources",
        lambda *args, **kwargs: downstream_steps.append("normalize"),
    )
    monkeypatch.setattr(
        bootstrap,
        "build_panel",
        lambda *args, **kwargs: downstream_steps.append("panel"),
    )
    monkeypatch.setattr(
        bootstrap,
        "generate_exhibits",
        lambda *args, **kwargs: downstream_steps.append("exhibits"),
    )

    settings = SimpleNamespace(
        wrds_username="test-user",
        bea_api_key="test-key",
        start_date="1952-01-01",
        end_date="2025-12-31",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        create_directories=lambda: None,
    )
    caplog.set_level(logging.INFO, logger=bootstrap.__name__)

    bootstrap.bootstrap_real_data(settings)

    assert started == acquisition_names
    assert downstream_steps == ["normalize", "panel", "exhibits"]
    messages = [record.getMessage() for record in caplog.records]
    for name in acquisition_names:
        assert f"Starting {name}" in messages
        assert any(message.startswith(f"Completed {name} in ") for message in messages)
    assert "Starting source normalization" in messages
    assert "Starting panel build" in messages
    assert "Starting exhibit generation" in messages