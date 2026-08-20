"""Tests for required table and figure artifact formats."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.analysis.exhibit_io import write_figure_artifacts, write_table_artifacts


def test_table_writer_creates_csv_and_latex(tmp_path: Path):
    table = pd.DataFrame({"metric_name": ["sample_mean"], "value": [1.25]})

    artifacts = write_table_artifacts(table, tmp_path, "table_test")

    assert artifacts.csv.exists()
    assert artifacts.tex.exists()
    assert "1.25" in artifacts.csv.read_text(encoding="utf-8")
    latex = artifacts.tex.read_text(encoding="utf-8")
    assert "tabular" in latex
    assert r"metric\_name" in latex
    assert r"sample\_mean" in latex


def test_figure_writer_creates_pdf_png_and_wrapper(tmp_path: Path):
    figure, axis = plt.subplots()
    axis.plot([0, 1], [0, 1])

    artifacts = write_figure_artifacts(
        figure,
        tmp_path,
        "figure_test",
        caption_macro="FigureTestCaption",
        label="fig:figure_test",
    )
    plt.close(figure)

    assert artifacts.pdf.exists() and artifacts.pdf.stat().st_size > 0
    assert artifacts.png.exists() and artifacts.png.stat().st_size > 0
    wrapper = artifacts.tex.read_text(encoding="utf-8")
    assert "figure_test.pdf" in wrapper
    assert r"\FigureTestCaption" in wrapper
    assert "fig:figure_test" in wrapper


def test_table_writer_escapes_latex_special_characters(tmp_path: Path):
    table = pd.DataFrame({"sp_excess_return": [0.01]})

    artifacts = write_table_artifacts(table, tmp_path, "table_escape_test")

    tex = artifacts.tex.read_text(encoding="utf-8")
    assert "sp\\_excess\\_return" in tex
