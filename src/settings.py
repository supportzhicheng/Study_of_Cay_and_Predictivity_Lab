"""Repository-relative settings for the core CAY replication."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


@dataclass(frozen=True)
class Settings:
    """Resolved paths, sample dates, and optional service credentials."""

    project_root: Path
    data_dir: Path
    output_dir: Path
    reports_dir: Path
    p10_input_dir: Path
    p10_reference_dir: Path
    start_date: str
    end_date: str
    historical_start: str
    historical_end: str
    wrds_username: str | None
    wrds_password: str | None
    bea_api_key: str | None

    def create_directories(self) -> None:
        """Create generated-data directories without touching source inputs."""
        for path in (self.data_dir, self.output_dir, self.reports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def public_summary(self) -> dict[str, str | None]:
        """Return settings safe to print without exposing credential values."""
        return {
            "PROJECT_ROOT": str(self.project_root),
            "DATA_DIR": str(self.data_dir),
            "OUTPUT_DIR": str(self.output_dir),
            "REPORTS_DIR": str(self.reports_dir),
            "P10_INPUT_DIR": str(self.p10_input_dir),
            "P10_REFERENCE_DIR": str(self.p10_reference_dir),
            "START_DATE": self.start_date,
            "END_DATE": self.end_date,
            "HISTORICAL_START": self.historical_start,
            "HISTORICAL_END": self.historical_end,
            "WRDS_USERNAME": "configured" if self.wrds_username else None,
            "WRDS_PASSWORD": "configured" if self.wrds_password else None,
            "BEA_API_KEY": "configured" if self.bea_api_key else None,
        }


def load_settings(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> Settings:
    """Resolve CLI overrides, environment values, then repository defaults."""
    root = (project_root or PROJECT_ROOT).resolve()
    env = dict(os.environ if environ is None else environ)
    dotenv = _read_dotenv(root / ".env")

    defaults = {
        "DATA_DIR": "_data",
        "OUTPUT_DIR": "_output",
        "REPORTS_DIR": "reports",
        "P10_INPUT_DIR": "_data/input",
        "P10_REFERENCE_DIR": "asset",
        "START_DATE": "1952-10-01",
        "END_DATE": date.today().isoformat(),
        "HISTORICAL_START": "1952Q4",
        "HISTORICAL_END": "1998Q3",
        "WRDS_USERNAME": None,
        "WRDS_PASSWORD": None,
        "BEA_API_KEY": None,
    }

    parser = argparse.ArgumentParser(description=__doc__)
    for name in defaults:
        parser.add_argument(f"--{name}")
    cli = vars(parser.parse_args(argv))

    def value(name: str) -> str | None:
        return cli[name] or env.get(name) or dotenv.get(name) or defaults[name]

    return Settings(
        project_root=root,
        data_dir=_resolve_path(str(value("DATA_DIR")), root),
        output_dir=_resolve_path(str(value("OUTPUT_DIR")), root),
        reports_dir=_resolve_path(str(value("REPORTS_DIR")), root),
        p10_input_dir=_resolve_path(str(value("P10_INPUT_DIR")), root),
        p10_reference_dir=_resolve_path(str(value("P10_REFERENCE_DIR")), root),
        start_date=str(value("START_DATE")),
        end_date=str(value("END_DATE")),
        historical_start=str(value("HISTORICAL_START")),
        historical_end=str(value("HISTORICAL_END")),
        wrds_username=value("WRDS_USERNAME"),
        wrds_password=value("WRDS_PASSWORD"),
        bea_api_key=value("BEA_API_KEY"),
    )


def main(argv: Sequence[str] | None = None) -> None:
    for name, value in load_settings(argv).public_summary().items():
        print(f"{name}={value or ''}")


if __name__ == "__main__":
    main()
