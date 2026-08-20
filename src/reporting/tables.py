"""Adapt machine-readable analysis results into compact publication tables."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.table_ii import TABLE_II_VARIABLES, TableIIResult
from src.analysis.table_s1 import TableS1Result

HORIZONS = (1, 2, 3, 4, 8, 12, 16, 24)


@dataclass(frozen=True)
class PublicationTable:
    """Main-report frame plus optional full-detail appendix frame."""

    frame: pd.DataFrame
    appendix: pd.DataFrame | None = None


def _number(value: object, digits: int = 3) -> str:
    return "" if pd.isna(value) else f"{float(value):.{digits}f}"


def _estimate_cell(row: object) -> str:
    if isinstance(row, pd.Series):
        coefficient = row["coefficient"]
        t_statistic = row["t_statistic"]
    else:
        coefficient = getattr(row, "coefficient")
        t_statistic = getattr(row, "t_statistic")
    return f"{_number(coefficient)} ({_number(t_statistic, 2)})"


def table_1(result: TableIIResult) -> PublicationTable:
    rows: list[dict[str, str]] = []
    for variable in TABLE_II_VARIABLES:
        summary = result.summary.loc[variable]
        rows.append(
            {
                "Panel": "A. Moments",
                "Variable": variable,
                "Mean": _number(summary["mean"]),
                "Std. dev.": _number(summary["standard_deviation"]),
                "AR(1)": _number(summary["ar1"]),
                "Correlation": "",
            }
        )
    for row_index, left in enumerate(TABLE_II_VARIABLES):
        for right in TABLE_II_VARIABLES[: row_index + 1]:
            rows.append(
                {
                    "Panel": "B. Correlations",
                    "Variable": f"{left} / {right}",
                    "Mean": "",
                    "Std. dev.": "",
                    "AR(1)": "",
                    "Correlation": _number(result.correlations.loc[left, right]),
                }
            )
    return PublicationTable(pd.DataFrame(rows))


def table_2(result: pd.DataFrame) -> PublicationTable:
    rows = []
    for model_id, model in result.groupby("row", sort=True):
        first = model.iloc[0]
        estimates = "; ".join(
            f"{row.term}: {_estimate_cell(row)}"
            for row in model.itertuples(index=False)
            if row.term != "const"
        )
        rows.append(
            {
                "Model": int(model_id),
                "Outcome": first["outcome"],
                "Predictor estimates (HAC t-stat.)": estimates,
                "Adj. R2": _number(first["adjusted_r_squared"]),
                "N": int(first["observations"]),
            }
        )
    return PublicationTable(pd.DataFrame(rows), appendix=result.copy())


def _long_horizon_panel(result: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for specification, label in ((1, "Consumption growth"), (2, "Excess returns")):
        for horizon in HORIZONS:
            model = result.loc[
                (result["specification"] == specification)
                & (result["horizon"] == horizon)
                & (result["term"] == "cay")
            ].iloc[0]
            rows.append(
                {
                    "Panel": label,
                    "Horizon": horizon,
                    "CAY coefficient (HAC t-stat.)": _estimate_cell(model),
                    "Adj. R2": _number(model["adjusted_r_squared"]),
                    "N": int(model["observations"]),
                }
            )
    return pd.DataFrame(rows)


def table_3(result: pd.DataFrame) -> PublicationTable:
    return PublicationTable(_long_horizon_panel(result), appendix=result.copy())


def table_4(historical: TableIIResult, updated: TableIIResult) -> PublicationTable:
    rows = []
    for variable in TABLE_II_VARIABLES:
        old = historical.summary.loc[variable]
        new = updated.summary.loc[variable]
        rows.append(
            {
                "Variable": variable,
                "Historical std.": _number(old["standard_deviation"]),
                "Updated std.": _number(new["standard_deviation"]),
                "Historical AR(1)": _number(old["ar1"]),
                "Updated AR(1)": _number(new["ar1"]),
                "Historical corr. with CAY": _number(
                    historical.correlations.loc[variable, "cay"]
                ),
                "Updated corr. with CAY": _number(
                    updated.correlations.loc[variable, "cay"]
                ),
            }
        )
    return PublicationTable(pd.DataFrame(rows))


def table_5(historical: pd.DataFrame, updated: pd.DataFrame) -> PublicationTable:
    rows = []
    for model_id in (2, 4, 6, 8, 13):
        old = historical.loc[
            (historical["row"] == model_id) & (historical["term"] == "cay")
        ].iloc[0]
        new = updated.loc[
            (updated["row"] == model_id) & (updated["term"] == "cay")
        ].iloc[0]
        rows.append(
            {
                "Model": model_id,
                "Outcome": old["outcome"],
                "Historical CAY (t)": _estimate_cell(old),
                "Updated CAY (t)": _estimate_cell(new),
                "Historical adj. R2": _number(old["adjusted_r_squared"]),
                "Updated adj. R2": _number(new["adjusted_r_squared"]),
            }
        )
    return PublicationTable(pd.DataFrame(rows), appendix=updated.copy())


def table_6(historical: pd.DataFrame, updated: pd.DataFrame) -> PublicationTable:
    old = _long_horizon_panel(historical)
    new = _long_horizon_panel(updated)
    rows = old[["Panel", "Horizon"]].copy()
    rows["Historical CAY (t)"] = old["CAY coefficient (HAC t-stat.)"]
    rows["Updated CAY (t)"] = new["CAY coefficient (HAC t-stat.)"]
    rows["Historical adj. R2"] = old["Adj. R2"]
    rows["Updated adj. R2"] = new["Adj. R2"]
    return PublicationTable(rows, appendix=updated.copy())


def table_7(result: TableS1Result) -> PublicationTable:
    rows: list[dict[str, object]] = []
    for row in result.coverage.itertuples(index=False):
        rows.append(
            {
                "Panel": "A. Coverage",
                "Variable": row.variable,
                "Sample": f"{row.first_quarter}--{row.last_quarter}",
                "N": "",
                "Mean": "",
                "Std. dev.": "",
                "AR(1)": "",
            }
        )
    for sample_name, panel_name in (
        ("historical", "B. Historical summary"),
        ("updated", "C. Updated summary"),
    ):
        for row in result.summary.loc[
            result.summary["sample"] == sample_name
        ].itertuples(index=False):
            rows.append(
                {
                    "Panel": panel_name,
                    "Variable": row.variable,
                    "Sample": "",
                    "N": int(row.observations),
                    "Mean": _number(row.mean),
                    "Std. dev.": _number(row.standard_deviation),
                    "AR(1)": _number(row.ar1),
                }
            )
    return PublicationTable(pd.DataFrame(rows))


def table_8(audit: pd.DataFrame) -> PublicationTable:
    counts = audit["status"].value_counts()
    rows = [
        {
            "Panel": "A. Status totals",
            "Check": status,
            "Actual": "",
            "Target": "",
            "Status": str(int(count)),
        }
        for status, count in counts.items()
    ]
    for row in audit.loc[audit["status"] != "PASS_STRICT"].itertuples(index=False):
        rows.append(
            {
                "Panel": "B. Non-strict checks",
                "Check": row.metric,
                "Actual": _number(row.actual, 4),
                "Target": _number(row.target, 4),
                "Status": row.status,
            }
        )
    return PublicationTable(pd.DataFrame(rows), appendix=audit.copy())


def validate_publication_table(table: PublicationTable) -> None:
    """Reject accidental missing values before report serialization."""
    if table.frame.isna().any().any():
        raise ValueError("Publication tables must use explicit blank display cells.")
