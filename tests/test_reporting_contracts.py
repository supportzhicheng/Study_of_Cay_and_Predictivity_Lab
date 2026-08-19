"""Tests for reporting metadata, captions, audit, manifests, and LaTeX logs."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.table_r1 import PASS_REVISED_VINTAGE, PASS_STRICT
from src.reporting.artifacts import write_artifact_manifest
from src.reporting.audit import write_replication_status
from src.reporting.captions import caption_macro_name, write_caption_macros
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
        "table_test:\n  title: S&P test table\n  label: tab:test\n  takeaway: sample_mean changed 5%\n",
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
    assert r"S\&P test table" in text
    assert r"sample\_mean changed 5\%" in text


@pytest.mark.parametrize(
    ("artifact_id", "expected"),
    [
        ("figure_1_replication", "FigureOneReplicationCaption"),
        ("table_s1_core_data_summary", "TableSOneCoreDataSummaryCaption"),
        ("table_r1_replication_audit", "TableROneReplicationAuditCaption"),
    ],
)
def test_caption_macro_names_use_only_control_word_letters(artifact_id, expected):
    assert caption_macro_name(artifact_id) == expected


def test_replication_status_uses_worst_check(tmp_path: Path):
    audit = pd.DataFrame({"status": [PASS_STRICT, PASS_REVISED_VINTAGE]})

    text_path, tex_path = write_replication_status(audit, tmp_path)

    assert text_path.read_text(encoding="utf-8").startswith(PASS_REVISED_VINTAGE)
    assert "1 strict, 1 revised-vintage" in tex_path.read_text(encoding="utf-8")


def test_artifact_manifest_hashes_dependencies_and_rejects_stale(tmp_path: Path):
    copy_schemas(tmp_path)
    dependencies = [
        tmp_path / "core_quarterly.parquet",
        tmp_path / "core_quarterly.metadata.json",
        tmp_path / "captions.yml",
    ]
    artifact = tmp_path / "table.csv"
    for dependency in dependencies:
        dependency.write_text("source", encoding="utf-8")
        os.utime(dependency, (1, 1))
    artifact.write_text("result", encoding="utf-8")
    os.utime(artifact, (2, 2))
    output = tmp_path / "manifest.json"

    write_artifact_manifest(
        {"table": artifact},
        {"table": dependencies},
        output,
        tmp_path / "schemas" / "artifact_manifest.schema.json",
        git_commit="abc123",
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert len(manifest["artifacts"][0]["sha256"]) == 64
    assert manifest["artifacts"][0]["source_dependencies"] == [
        str(path) for path in dependencies
    ]

    for dependency in dependencies:
        os.utime(dependency, (3, 3))
        with pytest.raises(ValueError, match="stale"):
            write_artifact_manifest(
                {"table": artifact},
                {"table": dependencies},
                output,
                tmp_path / "schemas" / "artifact_manifest.schema.json",
                git_commit="abc123",
            )
        os.utime(dependency, (1, 1))


def test_missing_latex_compiler_writes_actionable_log(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.reporting.latex.shutil.which", lambda _: None)

    with pytest.raises(RuntimeError, match="latexmk or install Tectonic"):
        compile_latex_report(tmp_path)

    assert (tmp_path / "build" / "latex_build.log").exists()


def test_compile_report_falls_back_to_tectonic(tmp_path: Path, monkeypatch):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    calls = []
    monkeypatch.setattr(
        "src.reporting.latex.shutil.which",
        lambda name: "/bin/tectonic" if name == "tectonic" else None,
    )
    monkeypatch.setattr(
        "src.reporting.latex.subprocess.run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or type("Result", (), {"stdout": "built", "stderr": "", "returncode": 0})(),
    )

    result = compile_latex_report(tmp_path)

    command, kwargs = calls[0]
    assert command == [
        "/bin/tectonic",
        "--keep-logs",
        "--print",
        "--outdir",
        str((tmp_path / "build").resolve()),
        "main.tex",
    ]
    assert kwargs["cwd"] == paper_dir
    assert result == tmp_path / "build" / "main.pdf"
