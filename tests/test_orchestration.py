"""Tests for command and PyDoit orchestration surfaces."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_help_lists_all_commands():
    completed = subprocess.run(
        [sys.executable, "-m", "src.pipeline", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    for command in ("panel", "exhibits", "all", "report"):
        assert command in completed.stdout


def test_doit_lists_required_core_tasks():
    completed = subprocess.run(
        [sys.executable, "-m", "doit", "list"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    for task in (
        "config",
        "pull_author_data",
        "import_sources",
        "normalize_pulled_sources",
        "build_panel",
        "generate_exhibits",
        "run_notebook",
        "compile_report",
        "run_tests",
        "bootstrap_real_data",
    ):
        assert task in completed.stdout
