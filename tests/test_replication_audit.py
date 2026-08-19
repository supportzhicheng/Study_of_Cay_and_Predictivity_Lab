"""Tests for immutable targets and strict/revised/failure audit statuses."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analysis.table_ii import TableIIResult
from src.analysis.table_r1 import (
    FAIL_REQUIRES_DIAGNOSIS,
    PASS_REVISED_VINTAGE,
    PASS_STRICT,
    build_table_r1,
    classify_replication_error,
    load_paper_targets,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_replication_statuses_use_fixed_nested_tolerances():
    assert (
        classify_replication_error(1.01, 1.0, strict=0.01, revised=0.04) == PASS_STRICT
    )
    assert (
        classify_replication_error(1.03, 1.0, strict=0.01, revised=0.04)
        == PASS_REVISED_VINTAGE
    )
    assert (
        classify_replication_error(1.05, 1.0, strict=0.01, revised=0.04)
        == FAIL_REQUIRES_DIAGNOSIS
    )


def test_invalid_tolerance_order_is_rejected():
    with pytest.raises(ValueError, match="revised >= strict"):
        classify_replication_error(1.0, 1.0, strict=0.05, revised=0.01)


def test_attached_target_file_contains_all_required_horizons_and_fixed_tolerances():
    targets = load_paper_targets(PROJECT_ROOT / "config" / "paper_targets.yml")

    assert set(targets["table_vi"]["excess_returns_cay"]) == {
        1,
        2,
        3,
        4,
        8,
        12,
        16,
        24,
    }
    assert targets["tolerances"]["dls_coefficient"] == {
        "strict": 0.01,
        "revised": 0.04,
    }


def test_complete_audit_mapper_accepts_exact_target_outputs():
    targets = load_paper_targets(PROJECT_ROOT / "config" / "paper_targets.yml")
    comparison = pd.DataFrame(
        {"posted_cay": [1.0, 2.0, 3.0], "cay_paper_inputs": [1.0, 2.0, 3.0]}
    )
    variables = [
        "sp_excess_return",
        "dividend_yield",
        "relative_bill_rate",
        "cay",
    ]
    correlations = pd.DataFrame(0.0, index=variables, columns=variables)
    correlations.loc["sp_excess_return", "cay"] = targets["table_ii"][
        "excess_return_cay_correlation"
    ]
    correlations.loc["dividend_yield", "cay"] = targets["table_ii"][
        "dividend_yield_cay_correlation"
    ]
    correlations.loc["relative_bill_rate", "cay"] = targets["table_ii"][
        "relative_bill_rate_cay_correlation"
    ]
    summary = pd.DataFrame({"ar1": [targets["table_ii"]["cay_ar1"]]}, index=["cay"])
    table_ii = TableIIResult(
        correlations=correlations,
        summary=summary,
        sample_start=pd.Period("1952Q4"),
        sample_end=pd.Period("1998Q3"),
    )

    table_iii_rows = []
    for row_name, metrics in targets["table_iii"].items():
        row = int(row_name.removeprefix("row_"))
        for term in ("cay", "term_spread"):
            coefficient_key = f"{term}_coefficient"
            statistic_key = f"{term}_t_statistic"
            if coefficient_key in metrics or statistic_key in metrics:
                table_iii_rows.append(
                    {
                        "row": row,
                        "term": term,
                        "coefficient": metrics.get(coefficient_key, 0.0),
                        "t_statistic": metrics.get(statistic_key, 0.0),
                        "adjusted_r_squared": metrics["adjusted_r_squared"],
                    }
                )
    table_vi = pd.DataFrame(
        [
            {
                "specification": 2,
                "horizon": int(horizon),
                "term": "cay",
                **metrics,
            }
            for horizon, metrics in targets["table_vi"]["excess_returns_cay"].items()
        ]
    )
    estimate = SimpleNamespace(
        beta_a=targets["dls"]["beta_asset"], beta_y=targets["dls"]["beta_income"]
    )

    result = build_table_r1(
        estimate, comparison, table_ii, pd.DataFrame(table_iii_rows), table_vi, targets
    )

    assert result["status"].eq(PASS_STRICT).all()
