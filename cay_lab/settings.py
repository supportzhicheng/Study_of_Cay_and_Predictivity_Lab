"""Settings for the CAY extension (cay_lab) pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAY_DATA_DIR = PROJECT_ROOT / "cay_data"
EXTENSION_OUTPUT_ROOT = PROJECT_ROOT / "cay_lab" / "output"


@dataclass(frozen=True)
class ExtensionSettings:
    """Paths and parameters for the extension pipeline."""

    project_root: Path
    cay_data_dir: Path
    output_dir: Path
    reports_dir: Path

    # Pipeline parameters with sensible defaults
    train_periods: int = 40
    prediction_window: int = 1
    target_component: str = "financial"
    min_history_periods: int = 8
    include_extension: bool = True

    def create_directories(self) -> None:
        for path in (self.output_dir, self.reports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def public_summary(self) -> dict[str, object]:
        return {
            "PROJECT_ROOT": str(self.project_root),
            "CAY_DATA_DIR": str(self.cay_data_dir),
            "OUTPUT_DIR": str(self.output_dir),
            "REPORTS_DIR": str(self.reports_dir),
            "train_periods": self.train_periods,
            "prediction_window": self.prediction_window,
            "target_component": self.target_component,
            "include_extension": self.include_extension,
        }


def load_extension_settings(
    output_dir: Path | None = None,
    reports_dir: Path | None = None,
    **overrides: object,
) -> ExtensionSettings:
    """Return :class:`ExtensionSettings` resolved from defaults and overrides."""
    resolved_output = output_dir or EXTENSION_OUTPUT_ROOT
    resolved_reports = reports_dir or (resolved_output / "reports")
    return ExtensionSettings(
        project_root=PROJECT_ROOT,
        cay_data_dir=CAY_DATA_DIR,
        output_dir=Path(resolved_output),
        reports_dir=Path(resolved_reports),
        train_periods=int(overrides.get("train_periods", 40)),
        prediction_window=int(overrides.get("prediction_window", 1)),
        target_component=str(overrides.get("target_component", "financial")),
        min_history_periods=int(overrides.get("min_history_periods", 8)),
        include_extension=bool(overrides.get("include_extension", True)),
    )
