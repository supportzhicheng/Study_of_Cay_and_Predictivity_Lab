"""Generate concise empirical finding paragraphs from report results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.table_ii import TableIIResult
from src.analysis.table_s1 import TableS1Result


def _macro(name: str, text: str) -> str:
    escaped = text.replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")
    return rf"\newcommand{{\{name}}}{{{escaped}}}"


def _cay_row(frame: pd.DataFrame, row: int = 6) -> pd.Series:
    return frame.loc[(frame["row"] == row) & (frame["term"] == "cay")].iloc[0]


def _best_horizon(frame: pd.DataFrame) -> pd.Series:
    rows = frame.loc[(frame["specification"] == 2) & (frame["term"] == "cay")]
    return rows.loc[rows["adjusted_r_squared"].idxmax()]


def write_empirical_findings(
    output_path: Path,
    *,
    historical_summary: TableIIResult,
    updated_summary: TableIIResult,
    historical_table_iii: pd.DataFrame,
    updated_table_iii: pd.DataFrame,
    historical_table_vi: pd.DataFrame,
    updated_table_vi: pd.DataFrame,
    historical_figure: pd.DataFrame,
    updated_figure: pd.DataFrame,
    data_summary: TableS1Result,
) -> Path:
    """Write the ten report finding macros required by Sections 3--5."""
    old_short = _cay_row(historical_table_iii)
    new_short = _cay_row(updated_table_iii)
    old_long = _best_horizon(historical_table_vi)
    new_long = _best_horizon(updated_table_vi)
    old_corr = historical_figure["cay"].corr(historical_figure["sp_excess_return"])
    new_corr = updated_figure["cay"].corr(updated_figure["sp_excess_return"])
    lines = [
        _macro(
            "HistoricalSummaryFinding",
            f"Historical CAY has AR(1) {historical_summary.summary.loc['cay', 'ar1']:.3f}; its persistence and correlations establish the paper-window benchmark for forecasting tests.",
        ),
        _macro(
            "HistoricalFigureFinding",
            f"Historical standardized CAY and excess returns have contemporaneous correlation {old_corr:.3f}; lead-lag regressions, rather than line overlap, test predictivity.",
        ),
        _macro(
            "HistoricalShortHorizonFinding",
            f"In the historical univariate excess-return model, CAY is {_fmt(old_short.coefficient)} with HAC t-statistic {old_short.t_statistic:.2f} and adjusted R-squared {old_short.adjusted_r_squared:.3f}.",
        ),
        _macro(
            "HistoricalLongHorizonFinding",
            f"Historical CAY has its largest excess-return adjusted R-squared at {int(old_long.horizon)} quarters ({old_long.adjusted_r_squared:.3f}), showing where the present-value return channel is strongest.",
        ),
        _macro(
            "UpdatedSummaryFinding",
            f"Updated CAY has AR(1) {updated_summary.summary.loc['cay', 'ar1']:.3f} and standard deviation {updated_summary.summary.loc['cay', 'standard_deviation']:.3f}, documenting how revised data alter persistence and scale.",
        ),
        _macro(
            "UpdatedFigureFinding",
            f"The updated displayed-sample CAY-return correlation is {new_corr:.3f}, so visual co-movement is weaker evidence than the generated forecasting estimates.",
        ),
        _macro(
            "UpdatedShortHorizonFinding",
            f"The updated univariate CAY coefficient is {_fmt(new_short.coefficient)} with HAC t-statistic {new_short.t_statistic:.2f}, compared with the stronger historical estimate.",
        ),
        _macro(
            "UpdatedLongHorizonFinding",
            f"Updated CAY has its largest excess-return adjusted R-squared at {int(new_long.horizon)} quarters ({new_long.adjusted_r_squared:.3f}), identifying the most informative updated horizon.",
        ),
        _macro(
            "DataCoverageFinding",
            f"The coverage audit separates variable-specific samples and transformations; {data_summary.takeaway}",
        ),
        _macro(
            "DataAnatomyFinding",
            "Indexed consumption, labor income, and wealth share a long-run movement while their growth rates diverge at business-cycle frequencies, motivating a relative-level cointegrating residual.",
        ),
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _fmt(value: float) -> str:
    return f"{float(value):.3f}"
