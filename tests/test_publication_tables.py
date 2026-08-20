"""Tests for compact publication-table adapters."""

from __future__ import annotations

import pandas as pd

from src.analysis.table_ii import build_table_ii
from src.analysis.table_iii import build_table_iii
from src.analysis.table_r1 import PASS_REVISED_VINTAGE, PASS_STRICT
from src.analysis.table_s1 import build_table_s1
from src.analysis.table_vi import build_table_vi
from src.reporting.tables import (
    table_1,
    table_2,
    table_3,
    table_4,
    table_5,
    table_6,
    table_7,
    table_8,
    validate_publication_table,
)
from tests.test_forecasting_exhibits import forecasting_panel
from tests.test_modes_diagnostics import diagnostic_panel


def test_main_publication_tables_have_explicit_cells_and_compact_models():
    panel = diagnostic_panel()
    forecast = forecasting_panel(periods=len(panel))
    panel = panel.join(forecast.drop(columns=["c", "cay"]), rsuffix="_forecast")
    panel["sp_real_return"] = forecast["sp_real_return"]
    panel["crsp_vw_real_return"] = forecast["crsp_vw_real_return"]
    panel["sp_excess_return"] = forecast["sp_excess_return"]
    panel["crsp_vw_excess_return"] = forecast["crsp_vw_excess_return"]
    panel["relative_bill_rate"] = forecast["relative_bill_rate"]
    panel["term_spread"] = forecast["term_spread"]
    panel["default_spread"] = forecast["default_spread"]
    historical = panel.iloc[:184]
    table_ii_h = build_table_ii(historical)
    table_ii_u = build_table_ii(panel)
    table_iii_h = build_table_iii(historical)
    table_iii_u = build_table_iii(panel)
    table_vi_h = build_table_vi(historical)
    table_vi_u = build_table_vi(panel)
    table_s1 = build_table_s1(panel)
    audit = pd.DataFrame(
        {
            "metric": ["strict", "revised"],
            "actual": [1.0, 1.1],
            "target": [1.0, 1.0],
            "status": [PASS_STRICT, PASS_REVISED_VINTAGE],
        }
    )
    publications = [
        table_1(table_ii_h),
        table_2(table_iii_h),
        table_3(table_vi_h),
        table_4(table_ii_h, table_ii_u),
        table_5(table_iii_h, table_iii_u),
        table_6(table_vi_h, table_vi_u),
        table_7(table_s1),
        table_8(audit),
    ]
    for publication in publications:
        validate_publication_table(publication)
        assert (
            not publication.frame.astype(str)
            .apply(lambda column: column.str.contains("NaN", case=False).any())
            .any()
        )

    assert table_2(table_iii_h).frame["Model"].tolist() == list(range(1, 14))
    assert table_5(table_iii_h, table_iii_u).frame["Model"].tolist() == [2, 4, 6, 8, 13]
    assert len(table_3(table_vi_h).frame) == 16
    assert len(table_6(table_vi_h, table_vi_u).frame) == 16
