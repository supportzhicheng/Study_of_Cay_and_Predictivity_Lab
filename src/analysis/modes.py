"""Separate historical paper-input, current-vintage, and updated CAY modes."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.estimate_cay import CayEstimate, estimate_cay
from src.data.build_quarterly_panel import HISTORICAL_INDEX


@dataclass(frozen=True)
class AnalysisModes:
    paper_inputs: CayEstimate
    current_vintage_historical: CayEstimate
    updated: CayEstimate
    historical_comparison: pd.DataFrame


def estimate_analysis_modes(panel: pd.DataFrame, leads_lags: int = 8) -> AnalysisModes:
    """Estimate all three declared modes without mixing their source definitions."""
    historical = panel.reindex(HISTORICAL_INDEX)
    paper_columns = ["paper_c", "paper_a", "paper_y", "posted_cay"]
    current_columns = ["c", "a", "y"]
    for columns, mode in ((paper_columns, "paper"), (current_columns, "current")):
        missing = sorted(set(columns) - set(panel.columns))
        if missing:
            raise ValueError(f"The {mode} analysis mode is missing columns: {missing}")
        if historical[columns].isna().any().any():
            raise ValueError(f"The {mode} historical analysis mode is incomplete.")

    paper_frame = historical[["paper_c", "paper_a", "paper_y"]].rename(
        columns={"paper_c": "c", "paper_a": "a", "paper_y": "y"}
    )
    current_frame = historical[current_columns]
    updated_frame = panel[current_columns].dropna()
    if updated_frame.empty:
        raise ValueError(
            "The updated analysis mode has no complete macro observations."
        )

    paper_estimate = estimate_cay(paper_frame, leads_lags)
    current_estimate = estimate_cay(current_frame, leads_lags)
    updated_estimate = estimate_cay(updated_frame, leads_lags)
    comparison = pd.DataFrame(
        {
            "posted_cay": historical["posted_cay"],
            "cay_paper_inputs": paper_estimate.cay,
            "cay_current_vintage": current_estimate.cay,
        }
    )
    return AnalysisModes(
        paper_inputs=paper_estimate,
        current_vintage_historical=current_estimate,
        updated=updated_estimate,
        historical_comparison=comparison,
    )
