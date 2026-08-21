"""Tests for cache-aware core raw acquisition."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import src.data.acquire_core as acquire_core


def _settings(tmp_path):
    return SimpleNamespace(
        wrds_username="test-user",
        wrds_password=None,
        bea_api_key="test-key",
        start_date="1952-01-01",
        end_date="2025-12-31",
        data_dir=tmp_path / "data",
        create_directories=lambda: None,
    )


def test_pull_wrds_uses_configured_username_and_closes(monkeypatch, tmp_path):
    closed = []
    connection_kwargs = {}
    connection = SimpleNamespace(close=lambda: closed.append(True))
    pulled = []

    monkeypatch.setitem(
        sys.modules,
        "wrds",
        SimpleNamespace(
            Connection=lambda **kwargs: connection_kwargs.update(kwargs) or connection
        ),
    )
    monkeypatch.setattr(
        acquire_core,
        "pull_wrds_data",
        lambda active_connection, raw_dir: pulled.append((active_connection, raw_dir)),
    )

    acquire_core._pull_wrds(_settings(tmp_path), tmp_path)

    assert connection_kwargs == {"wrds_username": "test-user", "wrds_password": ""}
    assert pulled == [(connection, tmp_path / "wrds")]
    assert closed == [True]


def test_acquire_core_reuses_complete_raw_caches(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    for relative in acquire_core.CORE_RAW_FILES:
        path = settings.data_dir / "raw" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(
        acquire_core, "pull_fred_data", lambda *args, **kwargs: pytest.fail()
    )
    monkeypatch.setattr(
        acquire_core, "pull_bea_data", lambda *args, **kwargs: pytest.fail()
    )
    monkeypatch.setattr(
        acquire_core, "pull_shiller_data", lambda *args, **kwargs: pytest.fail()
    )
    monkeypatch.setattr(
        acquire_core, "_pull_wrds", lambda *args, **kwargs: pytest.fail()
    )

    paths = acquire_core.acquire_core_data(settings)

    assert paths == [
        settings.data_dir / "raw" / relative for relative in acquire_core.CORE_RAW_FILES
    ]


def test_acquire_core_requires_wrds_only_when_cache_missing(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    settings.wrds_username = None
    monkeypatch.setattr(acquire_core, "pull_fred_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(acquire_core, "pull_bea_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(acquire_core, "pull_shiller_data", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="WRDS_USERNAME"):
        acquire_core.acquire_core_data(settings)
