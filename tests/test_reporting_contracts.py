"""Tests for reporting metadata, captions, audit, manifests, and LaTeX logs."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.table_r1 import PASS_REVISED_VINTAGE, PASS_STRICT
from src.reporting.artifacts import write_artifact_manifest
from src.reporting.audit import write_replication_status
from src.reporting.captions import write_caption_macros
from src.reporting.latex import compile_latex_report
from src.reporting.metadata import write_report_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def copy_schemas(destination: Path) -> None:
    schema_dir = destination / "schemas"
    schema_dir.mkdir(parents=True)
    for name in ("report_metadata.schema.json", "artifact_manifest.schema.json"):
        source = PROJECT_ROOT / "reports" / "schemas" / name
        (schema_dir / name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )


def test_report_metadata_writes_schema_valid_json_and_tex(tmp_path: Path):
    copy_schemas(tmp_path)
    metadata = {
        "historical_sample_start": "1952Q4",
        "historical_sample_end": "1998Q3",
        "updated_latest_common_quarter": "2025Q4",
        "data_vintage": "2026-08-18",
        "cay_historical_primary": "estimated_dls",
        "cay_updated_primary": "estimated_dls",
        "risk_free_primary": "bill_30d",
        "term_spread_primary": "term_10y_3m",
        "git_commit": "abc123",
    }

    json_path, tex_path = write_report_metadata(metadata, tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8")) == metadata
    assert r"\UpdatedSampleEnd" in tex_path.read_text(encoding="utf-8")


def test_caption_generation_requires_dates_and_calculated_takeaway(tmp_path: Path):
    captions = tmp_path / "captions.yml"
    captions.write_text(
        "table_test:\n  title: Test table\n  label: tab:test\n  takeaway: Calculated result\n",
        encoding="utf-8",
    )
    output = tmp_path / "generated_captions.tex"

    write_caption_macros(
        captions,
        output,
        sample_dates={"table_test": ("1952Q4", "1998Q3")},
        data_vintage="2026-08-18",
        calculated_takeaways={},
    )

    text = output.read_text(encoding="utf-8")
    assert "1952Q4--1998Q3" in text
    assert "Data vintage: 2026-08-18" in text
    assert "Calculated result" in text


def test_replication_status_uses_worst_check(tmp_path: Path):
    audit = pd.DataFrame({"status": [PASS_STRICT, PASS_REVISED_VINTAGE]})

    text_path, tex_path = write_replication_status(audit, tmp_path)

    assert text_path.read_text(encoding="utf-8").startswith(PASS_REVISED_VINTAGE)
    assert "1 strict, 1 revised-vintage" in tex_path.read_text(encoding="utf-8")


def test_artifact_manifest_hashes_dependencies_and_rejects_stale(tmp_path: Path):
    copy_schemas(tmp_path)
    dependency = tmp_path / "source.txt"
    artifact = tmp_path / "table.csv"
    dependency.write_text("source", encoding="utf-8")
    artifact.write_text("result", encoding="utf-8")
    os.utime(dependency, (1, 1))
    os.utime(artifact, (2, 2))
    output = tmp_path / "manifest.json"

    write_artifact_manifest(
        {"table": artifact},
        {"table": [dependency]},
        output,
        tmp_path / "schemas" / "artifact_manifest.schema.json",
        git_commit="abc123",
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert len(manifest["artifacts"][0]["sha256"]) == 64

    os.utime(dependency, (3, 3))
    with pytest.raises(ValueError, match="stale"):
        write_artifact_manifest(
            {"table": artifact},
            {"table": [dependency]},
            output,
            tmp_path / "schemas" / "artifact_manifest.schema.json",
            git_commit="abc123",
        )


def test_missing_latexmk_writes_actionable_log(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.reporting.latex.shutil.which", lambda _: None)

    with pytest.raises(RuntimeError, match="Install a TeX distribution"):
        compile_latex_report(tmp_path)

    assert (tmp_path / "build" / "latex_build.log").exists()
