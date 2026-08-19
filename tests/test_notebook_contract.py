"""Tests for the inspection-only replication tour notebook."""

import json
import shutil
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "01_cay_replication_tour.ipynb"


def test_notebook_alternates_cells_and_executes_from_generated_artifacts(
    tmp_path: Path,
):
    notebook = nbformat.read(NOTEBOOK_PATH, as_version=4)
    assert len(notebook.cells) == 12
    assert [cell.cell_type for cell in notebook.cells] == ["markdown", "code"] * 6

    reports_dir = tmp_path / "reports"
    (reports_dir / "tables").mkdir(parents=True)
    (reports_dir / "build").mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "reports" / "report_contract.yml", reports_dir)
    index = pd.period_range("2000Q1", periods=20, freq="Q")
    values = np.linspace(1.0, 2.0, len(index))
    panel = pd.DataFrame(
        {
            "c": values,
            "a": 1.2 * values,
            "y": 0.8 * values,
            "cay": np.sin(values),
            "sp_excess_return": np.cos(values),
            "crsp_vw_excess_return": np.cos(values) + 0.01,
        },
        index=index,
    )
    processed_dir = tmp_path / "_data" / "processed"
    processed_dir.mkdir(parents=True)
    panel.to_parquet(processed_dir / "core_quarterly.parquet")
    pd.DataFrame({"metric": ["fixture"], "status": ["PASS_STRICT"]}).to_csv(
        reports_dir / "tables" / "table_r1_replication_audit.csv", index=False
    )
    (reports_dir / "build" / "report_metadata.json").write_text(
        json.dumps({"updated_latest_common_quarter": "2004Q4"}), encoding="utf-8"
    )

    client = NotebookClient(
        notebook,
        timeout=90,
        kernel_name="python3",
        resources={"metadata": {"path": str(tmp_path)}},
    )
    executed = client.execute()

    assert all(
        cell.get("execution_count")
        for cell in executed.cells
        if cell.cell_type == "code"
    )
    source = "\n".join("".join(cell.source) for cell in notebook.cells)
    assert "WRDS_USERNAME" not in source
    assert "pull_" not in source
