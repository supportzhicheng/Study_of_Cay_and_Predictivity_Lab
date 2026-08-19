"""Schema-validated report metadata and generated LaTeX macros."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema

METADATA_MACROS = {
    "historical_sample_start": "HistoricalSampleStart",
    "historical_sample_end": "HistoricalSampleEnd",
    "updated_latest_common_quarter": "UpdatedSampleEnd",
    "data_vintage": "DataVintageDate",
    "git_commit": "GitCommitHash",
    "cay_historical_primary": "CayHistoricalDefinition",
    "cay_updated_primary": "CayUpdatedDefinition",
    "risk_free_primary": "RiskFreePrimary",
    "term_spread_primary": "TermSpreadPrimary",
}


def validate_json(document: Mapping[str, Any], schema_path: Path) -> None:
    """Validate a generated JSON document against a repository schema."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(dict(document), schema)


def _tex_escape(value: object) -> str:
    return str(value).replace("_", r"\_").replace("%", r"\%")


def write_report_metadata(
    metadata: Mapping[str, Any], reports_dir: Path
) -> tuple[Path, Path]:
    """Validate and write report metadata JSON and generated TeX macros."""
    schema_path = reports_dir / "schemas" / "report_metadata.schema.json"
    validate_json(metadata, schema_path)
    build_dir = reports_dir / "build"
    generated_dir = reports_dir / "paper" / "generated"
    build_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)
    json_path = build_dir / "report_metadata.json"
    tex_path = generated_dir / "report_metadata.tex"
    json_path.write_text(
        json.dumps(dict(metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        rf"\newcommand{{\{macro}}}{{{_tex_escape(metadata.get(key, ''))}}}"
        for key, macro in METADATA_MACROS.items()
    ]
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, tex_path
