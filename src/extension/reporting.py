"""Generate extension report artifacts (chartbook PDF + tables + combined section).

Provides the same artifact-generation contract as ``src/reporting/generate.py``
but for the ``cay_components_region`` extension analysis.  Replication artifacts
are never modified; this module only *adds* extension outputs.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.conventions import select_panel_conventions
from src.analysis.estimate_cay import estimate_cay
from src.analysis.figure_1 import plot_figure_1, prepare_figure_1
from src.analysis.modes import estimate_analysis_modes
from src.analysis.table_ii import TableIIResult, build_table_ii
from src.analysis.table_iii import build_table_iii
from src.analysis.table_r1 import load_paper_targets
from src.analysis.table_vi import build_table_vi
from src.data.build_quarterly_panel import HISTORICAL_INDEX, latest_common_quarter
from src.extension.chartbook import write_predictivity_chartbook
from src.extension.predictivity import rolling_predictivity

if TYPE_CHECKING:
    from src.settings import Settings


# ---------------------------------------------------------------------------
# Main exhibit-generation entry point
# ---------------------------------------------------------------------------

EXTENSION_ARTIFACT_STEMS = (
    "extension_prepared",
    "extension_rolling",
    "extension_chartbook",
    "extension_qa",
)

REGION_PROXY_COMPONENT_COLUMNS = (
    "housing_proxy_scaled_million_usd",
    "financial_proxy_scaled_million_usd",
    "liquid_proxy_scaled_million_usd",
)


def generate_extension_report_artifacts(
    panel: pd.DataFrame,
    settings: "Settings",
) -> list[Path]:
    """Generate all extension report artifacts from the prepared panel.

    Produces:
    - ``extension_prepared.csv`` – model-ready panel (CSV mirror)
    - ``extension_rolling.csv``  – rolling forecast results
    - ``extension_chartbook.pdf`` – per-segment chartbook
    - ``extension_qa.json``      – QA / provenance metadata

    Returns a list of all written paths.
    """
    out_dir = settings.extension_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    predictor_cols = [c for c in panel.columns if c.startswith("sub_cay_")]
    if not predictor_cols:
        raise RuntimeError(
            "No sub_cay_* predictor columns found in the extension panel. "
            "Ensure the 'panel' stage completed successfully."
        )

    # 1. Prepared CSV
    prepared_csv = out_dir / "extension_prepared.csv"
    panel_save = panel.copy()
    panel_save.index = panel_save.index.astype(str)
    panel_save.index.name = "quarter"
    panel_save.to_csv(prepared_csv)

    # 2. Rolling predictivity
    rolling_df = rolling_predictivity(
        panel,
        predictor_cols=predictor_cols,
        target_col="target_future_growth",
        train_periods=settings.extension_train_periods,
    )
    rolling_csv = out_dir / "extension_rolling.csv"
    rolling_df.to_csv(rolling_csv, index=False)

    # 3. Chartbook PDF
    pdf_path = out_dir / "extension_chartbook.pdf"
    write_predictivity_chartbook(
        prepared_df=panel,
        rolling_df=rolling_df,
        predictor_cols=predictor_cols,
        pdf_path=pdf_path,
        sub_category="region",
        dataset=settings.extension_output_dir.name,
        train_periods=settings.extension_train_periods,
        prediction_window=settings.extension_prediction_window,
        target_component=settings.extension_target_component,
        target_label="Future growth",
        start=str(panel.index.min()),
        end=str(panel.index.max()),
        risky_tickers=None,
        title="Sub-CAY Predictivity Chartbook — Extension (Region Proxy)",
    )

    # 4. QA metadata
    status_counts: dict[str, int] = {}
    if not rolling_df.empty and "status" in rolling_df.columns:
        status_counts = rolling_df["status"].value_counts().to_dict()

    qa: dict[str, object] = {
        "dataset": "region_proxy",
        "segments": sorted(panel["segment"].unique().tolist())
        if "segment" in panel.columns
        else [],
        "predictors": predictor_cols,
        "train_periods": settings.extension_train_periods,
        "prediction_window": settings.extension_prediction_window,
        "target_component": settings.extension_target_component,
        "prepared_rows": len(panel),
        "rolling_rows": len(rolling_df),
        "status_counts": status_counts,
    }
    qa_path = out_dir / "extension_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")

    return [prepared_csv, rolling_csv, pdf_path, qa_path]


# ---------------------------------------------------------------------------
# Combined report section writer
# ---------------------------------------------------------------------------


def _apply_selected_conventions(
    panel: pd.DataFrame, targets_path: Path
) -> pd.DataFrame:
    targets = load_paper_targets(targets_path)
    modes = estimate_analysis_modes(panel, leads_lags=8)
    selection_panel = panel.reindex(HISTORICAL_INDEX).copy()
    selection_panel["cay"] = modes.paper_inputs.cay
    selections = select_panel_conventions(selection_panel, targets)
    result = panel.copy()
    bill_column, relative_column = {
        "bill_30d": ("bill_30d_return", "relative_bill_rate_30d"),
        "bill_3m": ("bill_3m_return", "relative_bill_rate_3m"),
    }[selections.risk_free.selected]
    term_column = {
        "term_10y_3m": "term_spread_10y_3m",
        "term_10y_1y": "term_spread_10y_1y",
    }[selections.term_spread.selected]
    result["relative_bill_rate"] = result[relative_column]
    result["term_spread"] = result[term_column]
    result["sp_excess_return"] = result["sp_real_return"] - result[bill_column]
    result["crsp_vw_excess_return"] = (
        result["crsp_vw_real_return"] - result[bill_column]
    )
    return result


def _table_ii_frame(result: TableIIResult) -> pd.DataFrame:
    correlations = result.correlations.reset_index(names="variable")
    correlations.insert(0, "panel", "correlations")
    summary = result.summary.reset_index(names="variable")
    summary.insert(0, "panel", "summary")
    return pd.concat([correlations, summary], ignore_index=True, sort=False)


def _build_cay_r_series(core_panel: pd.DataFrame, region_csv_path: Path) -> pd.Series:
    region_raw = pd.read_csv(region_csv_path)
    required = {"quarter", *REGION_PROXY_COMPONENT_COLUMNS}
    missing = sorted(required - set(region_raw.columns))
    if missing:
        raise ValueError(
            f"Regional proxy CSV is missing required columns for cay_R: {missing}"
        )
    region_raw["quarter"] = pd.PeriodIndex(region_raw["quarter"].astype(str), freq="Q")
    region_panel = (
        region_raw.groupby("quarter")[list(REGION_PROXY_COMPONENT_COLUMNS)]
        .sum(min_count=1)
        .sort_index()
    )
    total_wealth_proxy = region_panel.sum(axis=1, min_count=1)
    if (total_wealth_proxy <= 0).any():
        raise ValueError("Regional wealth proxy contains non-positive values.")
    proxy_frame = pd.DataFrame(index=core_panel.index)
    proxy_frame["c"] = core_panel["c"]
    proxy_frame["y"] = core_panel["y"]
    proxy_frame["a"] = np.log(total_wealth_proxy).reindex(core_panel.index)
    proxy_frame = proxy_frame.dropna(subset=["c", "a", "y"])
    if proxy_frame.empty:
        raise ValueError("No overlapping quarterly sample to estimate cay_R.")
    return estimate_cay(proxy_frame, leads_lags=8).cay.rename("cay_R")


def _write_extension_replication_artifacts(
    ext_reports_dir: Path,
    core_panel_path: Path,
    region_csv_path: Path,
    targets_path: Path,
) -> dict[str, object]:
    panel = pd.read_parquet(core_panel_path)
    if not isinstance(panel.index, pd.PeriodIndex):
        panel.index = pd.PeriodIndex(panel.index, freq="Q")
    canonical = _apply_selected_conventions(panel, targets_path)
    cay_r = _build_cay_r_series(canonical, region_csv_path)
    extension_panel = canonical.copy()
    extension_panel["cay"] = cay_r.reindex(extension_panel.index)
    extension_panel = extension_panel.loc[
        : latest_common_quarter(
            extension_panel,
            ["cay", "sp_excess_return", "dividend_yield", "relative_bill_rate"],
        )
    ]

    table_ii = build_table_ii(extension_panel)
    table_iii = build_table_iii(extension_panel)
    table_vi = build_table_vi(extension_panel)
    figure_1 = prepare_figure_1(extension_panel)

    tables_dir = ext_reports_dir / "tables"
    figures_dir = ext_reports_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    table_ii_csv = tables_dir / "table_ii_extension_cay_r.csv"
    table_ii_tex = tables_dir / "table_ii_extension_cay_r.tex"
    table_iii_csv = tables_dir / "table_iii_extension_cay_r.csv"
    table_iii_tex = tables_dir / "table_iii_extension_cay_r.tex"
    table_vi_csv = tables_dir / "table_vi_extension_cay_r.csv"
    table_vi_tex = tables_dir / "table_vi_extension_cay_r.tex"

    _table_ii_frame(table_ii).to_csv(table_ii_csv, index=False)
    _table_ii_frame(table_ii).to_latex(table_ii_tex, index=False, escape=True)
    table_iii.to_csv(table_iii_csv, index=False)
    table_iii.to_latex(table_iii_tex, index=False, escape=True)
    table_vi.to_csv(table_vi_csv, index=False)
    table_vi.to_latex(table_vi_tex, index=False, escape=True)

    figure = plot_figure_1(figure_1)
    figure_pdf = figures_dir / "figure_1_extension_cay_r.pdf"
    figure_png = figures_dir / "figure_1_extension_cay_r.png"
    figure_tex = figures_dir / "figure_1_extension_cay_r.tex"
    figure.savefig(figure_pdf, bbox_inches="tight")
    figure.savefig(figure_png, dpi=180, bbox_inches="tight")
    plt.close(figure)
    figure_tex.write_text(
        "\n".join(
            [
                r"\begin{figure}[htbp]",
                r"\centering",
                r"\includegraphics[width=\linewidth]{generated/figures/figure_1_extension_cay_r.pdf}",
                r"\caption{Standardized $cay_R$ and excess S\&P returns.}",
                r"\label{fig:figure_1_extension_cay_r}",
                r"\end{figure}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "sample_start": str(figure_1.index.min()),
        "sample_end": str(figure_1.index.max()),
        "table_ii_tex": table_ii_tex,
        "figure_1_tex": figure_tex,
        "table_iii_tex": table_iii_tex,
        "table_vi_tex": table_vi_tex,
    }


def write_extension_report_section(
    ext_reports_dir: Path,
    replication_reports_dir: Path,
    settings: "Settings",
) -> Path:
    """Write extension-only LaTeX content for the main report section 08."""
    ext_reports_dir.mkdir(parents=True, exist_ok=True)

    qa_path = settings.extension_output_dir / "extension_qa.json"
    qa: dict = {}
    if qa_path.exists():
        qa = json.loads(qa_path.read_text(encoding="utf-8"))

    segments_list = qa.get("segments", [])
    segments_str = ", ".join(str(s) for s in segments_list) if segments_list else "N/A"
    status_counts = qa.get("status_counts", {})
    status_str = "; ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))

    core_panel_path = settings.data_dir / "processed" / "core_quarterly.parquet"
    if not core_panel_path.exists():
        raise FileNotFoundError(
            f"Regional report requires the core quarterly panel: {core_panel_path}"
        )
    region_csv_path = (
        settings.extension_data_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
    )
    targets_path = settings.project_root / "config" / "paper_targets.yml"

    extension_outputs = _write_extension_replication_artifacts(
        ext_reports_dir,
        core_panel_path,
        region_csv_path,
        targets_path,
    )
    sample_window = (
        f"{extension_outputs['sample_start']}--{extension_outputs['sample_end']}"
    )
    extension_exhibit_inputs = textwrap.dedent(
        r"""
            \subsection{Replication-Style Results with $cay_R$}
            \input{generated/tables/table_ii_extension_cay_r.tex}
            \input{generated/figures/figure_1_extension_cay_r.tex}
            \input{generated/tables/table_iii_extension_cay_r.tex}
            \input{generated/tables/table_vi_extension_cay_r.tex}
            """
    ).strip()

    tex = (
        textwrap.dedent(
            rf"""
        % ============================================================
        %  Combined Replication + Extension Results Section
        %  Auto-generated by src.extension.reporting
        % ============================================================

        \subsection{{Overview}}

        This extension constructs a Regional Replication predictor, denoted $cay_R$,
        from \texttt{{cay\_components\_region\_ca\_il\_tx\_q\_proxy.csv}} and
        reruns the replication-style forecasting pipeline with the
        \textit{{same model specifications}} used in the main report,
        replacing only the $cay$ construction.

        \subsection{{Data and Methodology}}

        Regional wealth proxies are derived by scaling national Households and
        Nonprofit Organisations (HNPO) quarterly components by within-state
        shares for California, Illinois, and Texas. We aggregate the regional
        proxy wealth levels by quarter, map them to the asset-wealth term in
        the DLS cointegrating regression, and estimate $cay_R$ with the same
        lead/lag settings as the baseline pipeline.

        \subsection{{Coverage}}

        Regions included: \textit{{{segments_str}}}.  Estimated $cay_R$ sample:
        \textit{{{sample_window}}}. Rolling extension QA summary:
        {status_str if status_str else "no rolling results produced"}.

        {extension_exhibit_inputs}

        \subsection{{How to Read the Extension Figure}}

        Figure \ref{{fig:figure_1_extension_cay_r}} follows the same display
        convention as the replication figure.  Both lines are standardized in
        displayed-sample units, so crossings indicate relative (not level)
        comovement.  Gray recession shading marks NBER downturn quarters.
        Sustained periods where $cay_R$ leads excess-return reversals are the
        visual counterpart to the predictive-regression coefficients reported in
        Tables III and VI; statistical significance should be assessed from those
        tables rather than from line overlap alone.

        Full rolling chartbook outputs remain available in
        \texttt{{extension\_chartbook.pdf}}
        and \texttt{{extension\_rolling.csv}}.

        \subsection{{Comparison with National Results}}

        Relative to baseline exhibits, this section isolates the impact of
        replacing $cay$ with $cay_R$ while preserving the same downstream
        regressions, horizons, and plotting conventions.
        """
        ).strip()
        + "\n"
    )

    out_path = ext_reports_dir / "extension_report.tex"
    out_path.write_text(tex, encoding="utf-8")
    return out_path
