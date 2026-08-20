"""Tests for command and PyDoit orchestration surfaces."""

import subprocess
import sys
from pathlib import Path

import dodo

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_actions_discard_library_return_values(monkeypatch):
    monkeypatch.setattr(dodo, "build_panel", lambda *args, **kwargs: dodo.PANEL_PATH)
    monkeypatch.setattr(dodo, "generate_exhibits", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        dodo, "compile_latex_report", lambda *args, **kwargs: dodo.REPORT_SOURCES[0]
    )

    for task_factory in (
        dodo.task_build_panel,
        dodo.task_generate_exhibits,
        dodo.task_compile_report,
    ):
        assert task_factory()["actions"][0]() is None


def test_run_tests_passes_junit_path_as_one_argument(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dodo.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    assert dodo.task_run_tests()["actions"][0]() is None

    command, kwargs = calls[0]
    assert command[-1] == f"--junitxml={dodo.SETTINGS.output_dir / 'pytest.xml'}"
    assert kwargs == {"check": True}


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
        "core_acquire",
        "core_prepare",
        "build_panel",
        "generate_exhibits",
        "run_notebook",
        "compile_report",
        "run_tests",
        "bootstrap_real_data",
        "extension_acquire",
        "extension_prepare",
        "extension_analyze",
        "extension_region_report",
        "extension_section9_chartbook",
    ):
        assert task in completed.stdout


def test_doit_targets_have_one_owner_and_required_edges():
    tasks = {
        "core_acquire": dodo.task_core_acquire(),
        "core_prepare": dodo.task_core_prepare(),
        "build_panel": dodo.task_build_panel(),
        "generate_exhibits": dodo.task_generate_exhibits(),
        "run_notebook": dodo.task_run_notebook(),
        "compile_report": dodo.task_compile_report(),
        "run_tests": dodo.task_run_tests(),
        "bootstrap_real_data": dodo.task_bootstrap_real_data(),
    }
    owners: dict[str, str] = {}
    for task_name, task in tasks.items():
        for target in task.get("targets", []):
            assert target not in owners, (
                f"{target} owned by {owners[target]} and {task_name}"
            )
            owners[target] = task_name

    assert len(tasks["build_panel"]["targets"]) == 2
    assert tasks["core_prepare"]["task_dep"] == ["core_acquire"]
    assert tasks["build_panel"]["task_dep"] == ["core_prepare"]
    assert set(tasks["generate_exhibits"]["targets"]) == {
        str(path) for path in (*dodo.GENERATED_ARTIFACTS, dodo.MANIFEST_PATH)
    }
    assert tasks["generate_exhibits"]["task_dep"] == ["build_panel"]
    assert tasks["run_notebook"]["task_dep"] == ["generate_exhibits"]
    assert tasks["compile_report"]["task_dep"] == [
        "generate_exhibits",
        "extension_region_report",
        "extension_section9_chartbook",
    ]
    assert not any(
        target.endswith("test_main.pdf")
        for target in tasks["compile_report"]["targets"]
    )
    assert tasks["compile_report"]["clean"] == [dodo._clean_generated]

    exhibit_dependencies = set(tasks["generate_exhibits"]["file_dep"])
    for path in (
        dodo.PANEL_PATH,
        dodo.PANEL_METADATA_PATH,
        dodo.TARGETS_PATH,
        dodo.SETTINGS.reports_dir / "report_config.yml",
        dodo.SETTINGS.reports_dir / "report_contract.yml",
    ):
        assert str(path) in exhibit_dependencies

    report_dependencies = set(tasks["compile_report"]["file_dep"])
    assert {str(path) for path in dodo.REPORT_SOURCES} <= report_dependencies
    assert {str(path) for path in dodo.GENERATED_ARTIFACTS} <= report_dependencies
    assert tasks["bootstrap_real_data"]["targets"] == [str(dodo.BOOTSTRAP_MARKER)]


def test_core_acquire_uses_complete_local_bundle_without_live_pull(
    monkeypatch, tmp_path
):
    marker = tmp_path / "core.complete"
    monkeypatch.setattr(dodo, "CORE_ACQUIRE_MARKER", marker)
    monkeypatch.setattr(
        dodo,
        "_local_core_sources",
        lambda: {
            source_id: [tmp_path / f"{source_id}.parquet"]
            for source_id in dodo.CORE_LIVE_SOURCE_IDS
        },
    )
    monkeypatch.setattr(
        dodo,
        "acquire_core_data",
        lambda settings: (_ for _ in ()).throw(AssertionError("live pull called")),
    )

    dodo._acquire_core()

    assert marker.read_text(encoding="utf-8") == (
        "completed via verified local normalized bundle\n"
    )


def test_core_acquire_freshness_requires_marker_and_complete_inputs(
    monkeypatch, tmp_path
):
    marker = tmp_path / "core.complete"
    monkeypatch.setattr(dodo, "CORE_ACQUIRE_MARKER", marker)
    monkeypatch.setattr(
        dodo,
        "_local_core_sources",
        lambda: {
            source_id: [tmp_path / f"{source_id}.parquet"]
            for source_id in dodo.CORE_LIVE_SOURCE_IDS
        },
    )

    assert not dodo._core_acquisition_current()
    marker.touch()
    assert dodo._core_acquisition_current()
