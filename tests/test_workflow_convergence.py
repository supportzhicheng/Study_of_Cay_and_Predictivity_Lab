"""Tests for workflow convergence scaffolding and guardrails."""

from __future__ import annotations

import ast
import hashlib
import json
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "migration_baseline.json"
EXTENSION_SOURCES_PATH = PROJECT_ROOT / "config" / "extension_sources.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pyproject_declares_stage_one_packaging_metadata():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    assert pyproject["build-system"]["requires"] == ["setuptools>=68"]
    assert pyproject["project"] == {
        "name": "cay-lab",
        "version": "0.1.0",
        "requires-python": ">=3.11",
    }
    assert pyproject["tool"]["setuptools"]["packages"]["find"] == {
        "where": ["src"],
        "include": ["cay_lab*"],
    }


def test_migration_baseline_fixture_matches_documented_expectations():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert baseline["core"]["processed_panel_sha256"] == (
        "f625964a6492c73c0ae31d76f71692823259fec3f930d9364103a9610cf77e2e"
    )
    assert baseline["core"]["generated_table_files"] == 16
    assert baseline["core"]["generated_figure_files"] == 9
    assert baseline["core"]["pre_pdf_artifacts"] == 32
    assert baseline["core"]["pytest_failed"] == 0
    assert (
        baseline["core"]["pytest_passed"]
        + baseline["core"]["pytest_failed"]
        + baseline["core"]["pytest_blocked"]
        == baseline["core"]["pytest_collected"]
    )
    assert baseline["core"]["audit_status_counts"] == {
        "PASS_STRICT": 25,
        "PASS_REVISED_VINTAGE": 11,
        "FAIL_REQUIRES_DIAGNOSIS": 3,
    }
    assert baseline["regional"]["prepared_rows"] == 414
    assert baseline["regional"]["rolling_rows"] == 294
    assert baseline["regional"]["segments"] == [
        "California",
        "Illinois",
        "Texas",
    ]
    assert baseline["regional"]["status_counts"] == {
        "ACTIVE": 207,
        "WEAKENED": 46,
        "LOST": 41,
    }
    assert baseline["section9"]["prepared_rows"] == 30
    assert baseline["section9"]["rolling_rows"] == 6
    assert baseline["section9"]["segments"] == ["bottom50", "middle40", "top10"]
    assert baseline["tracked_data"] == {
        "cay_data_files": 29,
        "cay_data_bytes": 1688055,
    }


def test_extension_source_manifest_pins_tracked_hashes():
    manifest = yaml.safe_load(EXTENSION_SOURCES_PATH.read_text(encoding="utf-8"))

    assert manifest["tracked_raw_root"] == "cay_data/raw"
    assert manifest["sources"]["fdic_state_deposits"]["enabled"] is False

    z1_s14 = manifest["sources"]["z1_s14_b"]
    z1_s1m = manifest["sources"]["z1_s1m_b"]
    dfa = manifest["sources"]["dfa_zip"]

    assert _sha256(PROJECT_ROOT / z1_s14["tracked_file"]) == z1_s14["sha256"]
    assert _sha256(PROJECT_ROOT / z1_s1m["tracked_file"]) == z1_s1m["sha256"]
    assert _sha256(PROJECT_ROOT / dfa["tracked_file"]) == dfa["sha256"]

    fred_series = manifest["sources"]["fred"]["series"]
    assert len(fred_series) == 10
    for spec in fred_series.values():
        assert _sha256(PROJECT_ROOT / spec["tracked_file"]) == spec["sha256"]

    supplemental = manifest["supplemental_tracked_snapshots"]
    for spec in supplemental:
        assert _sha256(PROJECT_ROOT / spec["tracked_file"]) == spec["sha256"]

    raw_root = PROJECT_ROOT / "cay_data" / "raw"
    assert sorted(path.name for path in raw_root.glob("fred_*.csv")) == [
        "fred_CAPCPI.csv",
        "fred_CAPOP.csv",
        "fred_CASTHPI.csv",
        "fred_ILPCPI.csv",
        "fred_ILPOP.csv",
        "fred_ILSTHPI.csv",
        "fred_TXPCPI.csv",
        "fred_TXPOP.csv",
        "fred_TXSTHPI.csv",
        "fred_USSTHPI.csv",
    ]


def test_shared_modules_do_not_import_cay_lab_extension():
    shared_paths = [
        PROJECT_ROOT / "dodo.py",
        PROJECT_ROOT / "settings.py",
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]

    for path in shared_paths:
        assert path.exists(), path

    for path in shared_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert "cay_lab.extension" not in {
                    alias.name for alias in node.names
                }, path
            elif isinstance(node, ast.ImportFrom):
                if node.module == "cay_lab.extension":
                    raise AssertionError(path)
                if node.module == "cay_lab":
                    assert "extension" not in {alias.name for alias in node.names}, path
