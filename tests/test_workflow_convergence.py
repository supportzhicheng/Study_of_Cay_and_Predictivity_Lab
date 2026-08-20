"""Tests for workflow convergence scaffolding and guardrails."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "migration_baseline.json"
EXTENSION_SOURCES_PATH = PROJECT_ROOT / "config" / "extension_sources.yml"


def test_repository_uses_environment_manifest_without_packaging_metadata():
    assert (PROJECT_ROOT / "environment.yml").exists()
    assert not (PROJECT_ROOT / "pyproject.toml").exists()
    assert not (PROJECT_ROOT / "cay_lab").exists()


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


def test_extension_source_manifest_declares_ignored_cache_contracts():
    manifest = yaml.safe_load(EXTENSION_SOURCES_PATH.read_text(encoding="utf-8"))

    assert manifest["tracked_raw_root"] == "_data/raw/extension"
    assert manifest["acquisition_modes"] == ["baseline", "latest"]
    fdic = manifest["sources"]["fdic_state_deposits"]
    assert fdic == {
        "provider": "FDIC Summary of Deposits",
        "enabled": False,
        "current_query_endpoint": "https://banks.data.fdic.gov/api/sod",
        "required_source_file": False,
        "method": "income_share_fallback",
    }
    fred_series = manifest["sources"]["fred"]["series"]
    assert len(fred_series) == 10
    assert all(
        spec["cache_path"].startswith("_data/raw/extension/")
        for spec in fred_series.values()
    )
    qqq = manifest["sources"]["qqq_market"]
    assert qqq["rows"] == 814
    assert (
        qqq["sha256"]
        == "ecbcf48746b1167b502d06fd07022f3f2ff7eff69fb89c4d4b08a8853c802bbb"
    )
    assert qqq["cache_path"] == "_data/raw/extension/market/QQQ.csv"


def test_no_provider_or_generated_data_is_tracked():
    assert not (PROJECT_ROOT / "cay_data").exists()


def test_python_modules_do_not_import_cay_lab():
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
                assert not any(
                    alias.name == "cay_lab" or alias.name.startswith("cay_lab.")
                    for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("cay_lab"), path
