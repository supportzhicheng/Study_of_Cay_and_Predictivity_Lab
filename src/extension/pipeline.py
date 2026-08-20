"""Staged pipeline for the CAY extension (cay_components_region).

Mirrors the stage structure of ``src/pipeline.py``:
  1. import   – validate and load raw region CSV → normalised parquet
  2. panel    – build predictivity panel from normalised data
  3. exhibits – run analysis and produce chartbook + table artifacts
  4. report   – write combined replication + extension report section

Run individual stages or all at once with ``python -m src.extension.pipeline``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from src.extension.loader import COMPONENTS, load_cay_decomposition
from src.settings import Settings, load_settings

# ---------------------------------------------------------------------------
# Stage 1 – Import / normalise
# ---------------------------------------------------------------------------

REGION_DATASET = "region_proxy"
REGION_NORMALIZED_STEM = "region_proxy_normalised"


def import_region_data(settings: Settings) -> Path:
    """Validate and persist the region-proxy CSV as a normalised parquet.

    Loads ``cay_components_region_ca_il_tx_q_proxy.csv`` from ``cay_data/``,
    validates required columns, and writes a parquet cache plus a JSON sidecar
    with basic provenance metadata.

    Returns the path to the written parquet file.
    """
    settings.create_directories()

    raw_df = load_cay_decomposition(
        dataset=REGION_DATASET,
        cay_data_dir=settings.extension_data_dir,
        dropna_components=False,
    )

    required_cols = {
        "region",
        "housing_proxy_scaled_million_usd",
        "financial_proxy_scaled_million_usd",
        "liquid_proxy_scaled_million_usd",
    }
    missing = required_cols - set(raw_df.columns)
    if missing:
        raise ValueError(f"Region proxy CSV is missing required columns: {missing}")

    out_parquet = (
        settings.extension_normalized_dir / f"{REGION_NORMALIZED_STEM}.parquet"
    )
    raw_df.to_parquet(out_parquet)

    metadata = {
        "source": REGION_DATASET,
        "rows": len(raw_df),
        "quarters": f"{raw_df.index.min()} – {raw_df.index.max()}",
        "regions": sorted(raw_df["region"].dropna().unique().tolist()),
        "columns": list(raw_df.columns),
    }
    meta_path = (
        settings.extension_normalized_dir / f"{REGION_NORMALIZED_STEM}.metadata.json"
    )
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return out_parquet


# ---------------------------------------------------------------------------
# Stage 2 – Build extension panel
# ---------------------------------------------------------------------------

PANEL_STEM = "extension_panel"


def _apply_predictivity_transforms(
    panel: pd.DataFrame,
    *,
    components: tuple[str, ...] = COMPONENTS,
    target_component: str = "financial",
    prediction_window: int = 1,
    min_history_periods: int = 8,
    train_periods: int = 40,
) -> pd.DataFrame:
    """Apply sub-cay and target transforms to a raw component DataFrame.

    Mirrors the transform logic inside ``prepare_predictivity_dataset`` but
    operates on an already-loaded DataFrame rather than re-reading from disk.
    """
    if target_component not in components:
        raise ValueError("target_component must be included in components.")

    panel = panel.copy()
    if "wealth_group" in panel.columns:
        panel["segment"] = panel["wealth_group"].astype(str)
    elif "region" in panel.columns:
        panel["segment"] = panel["region"].astype(str)
    else:
        panel["segment"] = "all"

    component_col_map: dict[str, str] = {}
    for comp in components:
        candidates = [
            f"{comp}_wealth_million_usd",
            f"{comp}_assets_million_usd",
            f"{comp}_proxy_scaled_million_usd",
        ]
        if comp == "liquid":
            candidates = [
                "liquid_assets_million_usd",
                "liquid_proxy_scaled_million_usd",
            ] + candidates
        found = next((col for col in candidates if col in panel.columns), None)
        if found is None:
            raise ValueError(f"Could not find component column for '{comp}'.")
        component_col_map[comp] = found

    keep_cols = ["segment"] + list(component_col_map.values())
    out = panel[keep_cols].sort_index()

    rows: list[pd.DataFrame] = []
    for segment, seg_df in out.groupby("segment", sort=True):
        seg_df = seg_df.sort_index().copy()
        for comp in components:
            raw_col = component_col_map[comp]
            log_col = np.log(seg_df[raw_col])
            hist_mean = log_col.expanding(min_periods=min_history_periods).mean()
            seg_df[f"sub_cay_{comp}"] = log_col - hist_mean
        target_raw = component_col_map[target_component]
        seg_df["target_future_growth"] = np.log(seg_df[target_raw]).shift(
            -prediction_window
        ) - np.log(seg_df[target_raw])
        rows.append(seg_df)

    final_df = pd.concat(rows).sort_index()
    predictor_cols = [f"sub_cay_{c}" for c in components]
    final_df = final_df.dropna(subset=predictor_cols + ["target_future_growth"])

    final_df.attrs["train_periods"] = train_periods
    final_df.attrs["prediction_window"] = prediction_window
    final_df.attrs["target_component"] = target_component
    final_df.attrs["dataset"] = REGION_DATASET
    final_df.attrs["component_columns"] = component_col_map
    return final_df


def build_extension_panel(settings: Settings) -> Path:
    """Prepare the predictivity panel from the normalised parquet (Stage 1 output).

    Loads the parquet written by :func:`import_region_data`, applies sub-cay
    log-level deviation transforms, and saves the model-ready panel.
    """
    normalised_path = (
        settings.extension_normalized_dir / f"{REGION_NORMALIZED_STEM}.parquet"
    )
    if not normalised_path.exists():
        raise FileNotFoundError(
            f"Normalised region data not found: {normalised_path}. "
            "Run the 'import' stage first."
        )

    raw_df = pd.read_parquet(normalised_path)
    if not isinstance(raw_df.index, pd.PeriodIndex):
        raw_df.index = pd.PeriodIndex(raw_df.index, freq="Q")

    panel = _apply_predictivity_transforms(
        raw_df,
        target_component=settings.extension_target_component,
        prediction_window=settings.extension_prediction_window,
        min_history_periods=settings.extension_min_history_periods,
        train_periods=settings.extension_train_periods,
    )

    out_path = settings.extension_processed_dir / f"{PANEL_STEM}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    panel_to_save = panel.copy()
    panel_to_save.index = panel_to_save.index.astype(str)
    panel_to_save.to_parquet(out_path)

    meta = {
        "dataset": REGION_DATASET,
        "train_periods": settings.extension_train_periods,
        "prediction_window": settings.extension_prediction_window,
        "target_component": settings.extension_target_component,
        "rows": len(panel),
        "segments": sorted(panel["segment"].unique().tolist()),
    }
    (settings.extension_processed_dir / f"{PANEL_STEM}.metadata.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return out_path


# ---------------------------------------------------------------------------
# Stage 3 – Generate exhibits
# ---------------------------------------------------------------------------


def generate_extension_exhibits(settings: Settings) -> list[Path]:
    """Run predictive-regression analysis and produce all extension artifacts.

    Produces the same kinds of outputs as ``src/pipeline.generate_exhibits``:
    - prepared dataset CSV
    - rolling forecast results CSV
    - chartbook PDF (one page per region segment)
    - QA/metadata JSON

    Returns paths of all generated files.
    """
    from src.extension.reporting import generate_extension_report_artifacts

    panel_path = settings.extension_processed_dir / f"{PANEL_STEM}.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(
            f"Extension panel not found: {panel_path}. Run the 'panel' stage first."
        )

    raw_panel = pd.read_parquet(panel_path)
    raw_panel.index = pd.PeriodIndex(raw_panel.index, freq="Q")

    return generate_extension_report_artifacts(
        panel=raw_panel,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Stage 4 – Combined report section
# ---------------------------------------------------------------------------


def generate_combined_report(
    settings: Settings,
    replication_reports_dir: Path | None = None,
) -> Path:
    """Write the combined replication + extension LaTeX section.

    This stage is additive: it reads existing replication artifacts (if
    available) and appends extension results.  The replication content is
    never modified.
    """
    from src.extension.reporting import write_extension_report_section

    ext_reports_dir = settings.extension_reports_dir
    ext_reports_dir.mkdir(parents=True, exist_ok=True)

    repl_dir = replication_reports_dir or (settings.project_root / "reports")
    return write_extension_report_section(
        ext_reports_dir=ext_reports_dir,
        replication_reports_dir=repl_dir,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the extension pipeline.",
    )
    parser.add_argument(
        "command",
        choices=("import", "panel", "exhibits", "report", "all"),
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--train-periods", type=int, default=40)
    parser.add_argument("--prediction-window", type=int, default=1)
    parser.add_argument("--target-component", default="financial")
    args = parser.parse_args(argv)

    setting_args = [
        "--EXTENSION_TRAIN_PERIODS",
        str(args.train_periods),
        "--EXTENSION_PREDICTION_WINDOW",
        str(args.prediction_window),
        "--EXTENSION_TARGET_COMPONENT",
        args.target_component,
    ]
    if args.output_dir:
        setting_args.extend(["--EXTENSION_OUTPUT_DIR", args.output_dir])
    settings = load_settings(setting_args)

    if args.command in {"import", "all"}:
        p = import_region_data(settings)
        print(f"Normalised region data: {p}")
    if args.command in {"panel", "all"}:
        p = build_extension_panel(settings)
        print(f"Extension panel: {p}")
    if args.command in {"exhibits", "all"}:
        for p in generate_extension_exhibits(settings):
            print(p)
    if args.command in {"report", "all"}:
        p = generate_combined_report(settings)
        print(f"Combined report section: {p}")


if __name__ == "__main__":
    main()
