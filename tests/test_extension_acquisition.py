"""Tests for explicit extension source acquisition boundaries."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

import src.data.extension_acquisition as acquisition
from src.extension.chartbook import _fetch_risky_asset_quarterly_prices
from src.settings import load_settings


def test_baseline_import_copies_and_verifies_local_bundle(monkeypatch, tmp_path):
    source = tmp_path / "bundle" / "source.csv"
    source.parent.mkdir()
    source.write_text("pinned bytes\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "_data" / "raw" / "extension" / "source.csv"
    settings = load_settings(
        argv=[
            "--EXTENSION_INPUT_DIR",
            str(source.parent),
            "--EXTENSION_ACQUISITION_MODE",
            "baseline",
        ],
        environ={},
        project_root=tmp_path,
    )
    monkeypatch.setattr(
        acquisition,
        "_declared_sources",
        lambda settings: [(Path("_data/raw/extension/source.csv"), digest)],
    )

    assert acquisition.acquire_extension_sources(settings) == [destination]
    assert destination.read_bytes() == source.read_bytes()
    assert acquisition.extension_sources_current(settings)


def test_baseline_import_rejects_hash_mismatch(monkeypatch, tmp_path):
    path = tmp_path / "_data" / "raw" / "extension" / "source.csv"
    path.parent.mkdir(parents=True)
    path.write_text("mutable\n", encoding="utf-8")
    settings = load_settings(
        argv=["--EXTENSION_ACQUISITION_MODE", "baseline"],
        environ={},
        project_root=tmp_path,
    )
    monkeypatch.setattr(
        acquisition,
        "_declared_sources",
        lambda settings: [(Path("_data/raw/extension/source.csv"), "0" * 64)],
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        acquisition.acquire_extension_sources(settings)
    assert not acquisition.extension_sources_current(settings)


def test_chartbook_requires_declared_market_cache(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run extension_acquire"):
        _fetch_risky_asset_quarterly_prices(
            "QQQ", "2023Q1", "2026Q1", tmp_path / "market"
        )


def test_chartbook_reads_cached_market_prices(tmp_path):
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    dates = pd.date_range("2023-01-03", "2026-04-01", freq="D")
    pd.DataFrame({"date": dates, "price": range(1, len(dates) + 1)}).to_csv(
        market_dir / "QQQ.csv", index=False
    )

    result = _fetch_risky_asset_quarterly_prices("QQQ", "2023Q1", "2026Q1", market_dir)

    assert result.index.min() == pd.Period("2023Q1")
    assert result.index.max() == pd.Period("2026Q1")
