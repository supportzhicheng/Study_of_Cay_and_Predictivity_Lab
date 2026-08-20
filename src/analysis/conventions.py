"""Predeclared scoring for ambiguous rate and spread conventions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from src.analysis.forecasting import run_hac_regression
from src.analysis.table_iii import TABLE_III_SPECS, prepare_table_iii_model


@dataclass(frozen=True)
class ConventionSelection:
    selected: str
    scores: dict[str, float]
    candidate_metrics: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class PanelConventions:
    panel: pd.DataFrame
    risk_free: ConventionSelection
    term_spread: ConventionSelection


def select_convention(
    candidate_metrics: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, float],
    tolerances: Mapping[str, float],
    tie_break_order: Sequence[str],
) -> ConventionSelection:
    """Select the lowest mean scaled anchor error with a fixed tie-break."""
    if set(anchors) != set(tolerances):
        raise ValueError("Anchors and tolerances must contain the same metrics.")
    if not anchors or any(value <= 0 for value in tolerances.values()):
        raise ValueError("Convention scoring requires positive metric tolerances.")
    if set(candidate_metrics) != set(tie_break_order):
        raise ValueError("Tie-break order must list every candidate exactly once.")

    scores: dict[str, float] = {}
    for candidate, metrics in candidate_metrics.items():
        missing = sorted(set(anchors) - set(metrics))
        if missing:
            raise ValueError(f"Candidate '{candidate}' is missing metrics: {missing}")
        scores[candidate] = sum(
            abs(metrics[name] - target) / tolerances[name]
            for name, target in anchors.items()
        ) / len(anchors)

    best_score = min(scores.values())
    tied = {
        candidate
        for candidate, score in scores.items()
        if math.isclose(score, best_score, rel_tol=1e-12, abs_tol=1e-12)
    }
    selected = next(candidate for candidate in tie_break_order if candidate in tied)
    return ConventionSelection(selected=selected, scores=scores)


def _table_iii_metrics(panel: pd.DataFrame, row: int) -> dict[str, float]:
    spec = TABLE_III_SPECS[row - 1]
    outcome, predictors = prepare_table_iii_model(panel, spec)
    result = run_hac_regression(outcome, predictors, horizon=1)
    metrics = {
        "cay_coefficient": result.coefficients["cay"],
        "adjusted_r_squared": result.adjusted_r_squared,
    }
    if "term_spread" in result.coefficients:
        metrics["term_spread_coefficient"] = result.coefficients["term_spread"]
    return metrics


def select_panel_conventions(
    panel: pd.DataFrame, targets: Mapping[str, Any]
) -> PanelConventions:
    """Apply source-defined primary conventions and retain robustness metrics."""
    _ = targets
    risk_panels: dict[str, pd.DataFrame] = {}
    risk_metrics: dict[str, dict[str, float]] = {}
    risk_definitions = {
        "bill_30d": ("bill_30d_return", "relative_bill_rate_30d"),
        "bill_3m": ("bill_3m_return", "relative_bill_rate_3m"),
    }
    for name, (bill_column, relative_column) in risk_definitions.items():
        candidate = panel.copy()
        candidate["relative_bill_rate"] = candidate[relative_column]
        candidate["sp_excess_return"] = (
            candidate["sp_real_return"] - candidate[bill_column]
        )
        candidate["crsp_vw_excess_return"] = (
            candidate["crsp_vw_real_return"] - candidate[bill_column]
        )
        risk_panels[name] = candidate
        risk_metrics[name] = _table_iii_metrics(candidate, 6)

    risk_selection = ConventionSelection(
        selected="bill_30d",
        scores={},
        candidate_metrics=risk_metrics,
    )
    selected_panel = risk_panels[risk_selection.selected]

    term_metrics: dict[str, dict[str, float]] = {}
    term_panels: dict[str, pd.DataFrame] = {}
    for name, column in (
        ("term_10y_3m", "term_spread_10y_3m"),
        ("term_10y_1y", "term_spread_10y_1y"),
    ):
        candidate = selected_panel.copy()
        candidate["term_spread"] = candidate[column]
        term_panels[name] = candidate
        term_metrics[name] = _table_iii_metrics(candidate, 13)

    term_selection = ConventionSelection(
        selected="term_10y_3m",
        scores={},
        candidate_metrics=term_metrics,
    )
    return PanelConventions(
        panel=term_panels[term_selection.selected],
        risk_free=risk_selection,
        term_spread=term_selection,
    )
