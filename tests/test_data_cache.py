"""Tests for normalized caches and local source imports."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.cache import sha256_file, write_normalized_cache
from src.data.import_local import find_local_input, import_local_source


def core_macro_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "quarter": ["2000Q2", "2000Q1"],
            "c": [2.0, 1.0],
            "a": [4.0, 3.0],
            "y": [6.0, 5.0],
        }
    )


def test_cache_writes_parquet_and_complete_metadata(tmp_path: Path):
    paths = write_normalized_cache(
        core_macro_frame(),
        "core_macro",
        tmp_path,
        vintage="2026-08-18",
        retrieval_description="deterministic test fixture",
    )

    cached = pd.read_parquet(paths.data)
    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))

    assert cached.index.astype(str).tolist() == ["2000Q1", "2000Q2"]
    assert metadata["source_id"] == "core_macro"
    assert metadata["sample_start"] == "2000Q1"
    assert metadata["sample_end"] == "2000Q2"
    assert metadata["row_count"] == 2
    assert metadata["missing_counts"] == {"a": 0, "c": 0, "y": 0}
    assert metadata["sha256"] == sha256_file(paths.data)


def test_extra_metadata_cannot_replace_required_fields(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot replace.*source_id"):
        write_normalized_cache(
            core_macro_frame(),
            "core_macro",
            tmp_path,
            vintage="2026-08-18",
            retrieval_description="fixture",
            extra_metadata={"source_id": "wrong"},
        )


@pytest.mark.parametrize("suffix", [".csv", ".parquet", ".xlsx"])
def test_local_import_accepts_supported_types(tmp_path: Path, suffix: str):
    input_dir = tmp_path / "input"
    cache_dir = tmp_path / "normalized"
    input_dir.mkdir()
    path = input_dir / f"core_macro_quarterly{suffix}"
    frame = core_macro_frame()
    if suffix == ".csv":
        frame.to_csv(path, index=False)
    elif suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_excel(path, index=False)

    paths = import_local_source(
        "core_macro", input_dir, cache_dir, vintage="2026-08-18"
    )
    metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))

    assert paths.data.exists()
    assert metadata["local_input_filename"] == path.name


def test_local_import_rejects_ambiguous_files(tmp_path: Path):
    (tmp_path / "core_macro_quarterly.csv").touch()
    (tmp_path / "core_macro_quarterly.parquet").touch()

    with pytest.raises(ValueError, match="Ambiguous local inputs"):
        find_local_input("core_macro", tmp_path)


def test_local_import_rejects_unsupported_file(tmp_path: Path):
    (tmp_path / "core_macro_quarterly.json").touch()

    with pytest.raises(ValueError, match="Unsupported local input type"):
        find_local_input("core_macro", tmp_path)


def test_local_import_reports_expected_filename(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="core_macro_quarterly"):
        find_local_input("core_macro", tmp_path)
