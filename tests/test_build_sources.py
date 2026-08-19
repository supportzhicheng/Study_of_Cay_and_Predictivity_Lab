"""Tests for raw-to-normalized source orchestration."""

from pathlib import Path

import pytest

from src.data.build_sources import RAW_FILES, normalize_pulled_sources


def test_normalization_reports_every_missing_raw_cache(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as error:
        normalize_pulled_sources(tmp_path / "raw", tmp_path / "normalized")

    message = str(error.value)
    for relative_path in RAW_FILES.values():
        assert str(relative_path) in message
    assert "pull commands" in message
