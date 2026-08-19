"""Replication tolerance audit against immutable paper targets."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from src.analysis.estimate_cay import CayEstimate
from src.analysis.table_ii import TableIIResult

PASS_STRICT = "PASS_STRICT"
PASS_REVISED_VINTAGE = "PASS_REVISED_VINTAGE"
FAIL_REQUIRES_DIAGNOSIS = "FAIL_REQUIRES_DIAGNOSIS"


def load_paper_targets(path: Path) -> dict[str, Any]:
    """Load immutable paper anchors and fail on a missing tolerance section."""
    with path.open("r", encoding="utf-8") as handle:
        targets = yaml.safe_load(handle)
    if not isinstance(targets, dict) or "tolerances" not in targets:
        raise ValueError("Paper target configuration must contain tolerances.")
    return targets


def classify_replication_error(
    actual: float, target: float, *, strict: float, revised: float
) -> str:
    """Classify an absolute target error using fixed nested tolerances."""
    if strict < 0 or revised < strict:
        raise ValueError("Tolerances must be nonnegative and revised >= strict.")
    error = abs(actual - target)
    if error <= strict or math.isclose(error, strict, rel_tol=1e-12, abs_tol=1e-12):
        return PASS_STRICT
    if error <= revised or math.isclose(error, revised, rel_tol=1e-12, abs_tol=1e-12):
        return PASS_REVISED_VINTAGE
    return FAIL_REQUIRES_DIAGNOSIS


def _audit_row(
    metric: str,
    actual: float,
    target: float,
    tolerance_name: str,
    tolerances: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    tolerance = tolerances[tolerance_name]
    return {
        "metric": metric,
        "actual": actual,
        "target": target,
        "absolute_error": abs(actual - target),
        "strict_tolerance": tolerance["strict"],
        "revised_tolerance": tolerance["revised"],
        "status": classify_replication_error(actual, target, **tolerance),
    }


def build_table_r1(
    estimate: CayEstimate,
    historical_comparison: pd.DataFrame,
    table_ii: TableIIResult,
    table_iii: pd.DataFrame,
    table_vi: pd.DataFrame,
    targets: Mapping[str, Any],
) -> pd.DataFrame:
    """Build the complete historical replication audit table."""
    tolerances = targets["tolerances"]
    rows = [
        _audit_row(
            "dls.beta_asset",
            estimate.beta_a,
            targets["dls"]["beta_asset"],
            "dls_coefficient",
            tolerances,
        ),
        _audit_row(
            "dls.beta_income",
            estimate.beta_y,
            targets["dls"]["beta_income"],
            "dls_coefficient",
            tolerances,
        ),
        _audit_row(
            "posted_cay.correlation",
            historical_comparison["posted_cay"].corr(
                historical_comparison["cay_paper_inputs"]
            ),
            1.0,
            "posted_cay_correlation",
            tolerances,
        ),
    ]

    table_ii_actuals = {
        "cay_ar1": table_ii.summary.loc["cay", "ar1"],
        "excess_return_cay_correlation": table_ii.correlations.loc[
            "sp_excess_return", "cay"
        ],
        "dividend_yield_cay_correlation": table_ii.correlations.loc[
            "dividend_yield", "cay"
        ],
        "relative_bill_rate_cay_correlation": table_ii.correlations.loc[
            "relative_bill_rate", "cay"
        ],
    }
    for name, actual in table_ii_actuals.items():
        rows.append(
            _audit_row(
                f"table_ii.{name}",
                actual,
                targets["table_ii"][name],
                "table_ii",
                tolerances,
            )
        )

    for row_name, target_metrics in targets["table_iii"].items():
        row_number = int(row_name.removeprefix("row_"))
        model = table_iii[table_iii["row"] == row_number]
        for metric_name, target in target_metrics.items():
            if metric_name == "adjusted_r_squared":
                actual = float(model["adjusted_r_squared"].iloc[0])
                tolerance_name = "table_iii_adjusted_r_squared"
            else:
                term, statistic = metric_name.rsplit("_", 1)
                if statistic == "coefficient":
                    column = "coefficient"
                    tolerance_name = "table_iii_coefficient"
                elif metric_name.endswith("_t_statistic"):
                    term = metric_name.removesuffix("_t_statistic")
                    column = "t_statistic"
                    tolerance_name = "table_iii_t_statistic"
                else:
                    raise ValueError(f"Unsupported Table III target: {metric_name}")
                actual = float(model.loc[model["term"] == term, column].iloc[0])
            rows.append(
                _audit_row(
                    f"table_iii.{row_name}.{metric_name}",
                    actual,
                    target,
                    tolerance_name,
                    tolerances,
                )
            )

    for horizon, target_metrics in targets["table_vi"]["excess_returns_cay"].items():
        model = table_vi[
            (table_vi["specification"] == 2)
            & (table_vi["horizon"] == int(horizon))
            & (table_vi["term"] == "cay")
        ].iloc[0]
        for metric_name, tolerance_name in (
            ("t_statistic", "table_vi_t_statistic"),
            ("adjusted_r_squared", "table_vi_adjusted_r_squared"),
        ):
            rows.append(
                _audit_row(
                    f"table_vi.h{horizon}.{metric_name}",
                    float(model[metric_name]),
                    target_metrics[metric_name],
                    tolerance_name,
                    tolerances,
                )
            )
    return pd.DataFrame(rows)
