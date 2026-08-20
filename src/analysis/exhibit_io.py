"""Writers for required table and figure artifact formats."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure


@dataclass(frozen=True)
class TableArtifacts:
    csv: Path
    tex: Path


@dataclass(frozen=True)
class FigureArtifacts:
    pdf: Path
    png: Path
    tex: Path


def write_table_artifacts(
    table: pd.DataFrame,
    output_dir: Path,
    artifact_id: str,
    *,
    caption_macro: str | None = None,
    label: str | None = None,
) -> TableArtifacts:
    """Write one numerical table in CSV and LaTeX formats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{artifact_id}.csv"
    tex_path = output_dir / f"{artifact_id}.tex"
    table.to_csv(csv_path, index=False)
    tabular = table.to_latex(index=False, escape=True, na_rep="")
    if caption_macro and label:
        tabular = "\n".join(
            [
                r"\begin{table}[htbp]",
                r"\centering",
                rf"\caption{{\{caption_macro}}}",
                rf"\label{{{label}}}",
                r"\small",
                r"\resizebox{\textwidth}{!}{%",
                tabular,
                r"}",
                r"\end{table}",
                "",
            ]
        )
    tex_path.write_text(tabular, encoding="utf-8")
    return TableArtifacts(csv=csv_path, tex=tex_path)


def write_figure_artifacts(
    figure: Figure,
    output_dir: Path,
    artifact_id: str,
    *,
    caption_macro: str,
    label: str,
) -> FigureArtifacts:
    """Write one figure in PDF, PNG, and LaTeX-wrapper formats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{artifact_id}.pdf"
    png_path = output_dir / f"{artifact_id}.png"
    tex_path = output_dir / f"{artifact_id}.tex"
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=180, bbox_inches="tight")
    wrapper = "\n".join(
        [
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\includegraphics[width=\linewidth]{{../figures/{artifact_id}.pdf}}",
            rf"\caption{{\{caption_macro}}}",
            rf"\label{{{label}}}",
            r"\end{figure}",
            "",
        ]
    )
    tex_path.write_text(wrapper, encoding="utf-8")
    return FigureArtifacts(pdf=pdf_path, png=png_path, tex=tex_path)
