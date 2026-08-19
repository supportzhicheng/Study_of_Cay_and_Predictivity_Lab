"""Dependency-aware artifact manifest generation and validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from src.data.cache import sha256_file
from src.reporting.metadata import validate_json


def write_artifact_manifest(
    artifacts: Mapping[str, Path],
    dependencies: Mapping[str, Sequence[Path]],
    output_path: Path,
    schema_path: Path,
    *,
    git_commit: str,
) -> Path:
    """Hash artifacts and reject missing or stale source dependencies."""
    entries = []
    for artifact_id, path in artifacts.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing generated artifact: {path}")
        source_dependencies = list(dependencies.get(artifact_id, ()))
        missing = [
            dependency for dependency in source_dependencies if not dependency.exists()
        ]
        if missing:
            raise FileNotFoundError(f"Missing artifact dependencies: {missing}")
        stale = [
            dependency
            for dependency in source_dependencies
            if dependency.stat().st_mtime > path.stat().st_mtime
        ]
        if stale:
            raise ValueError(f"Artifact '{artifact_id}' is stale relative to: {stale}")
        entries.append(
            {
                "id": artifact_id,
                "path": str(path),
                "sha256": sha256_file(path),
                "source_dependencies": [
                    str(dependency) for dependency in source_dependencies
                ],
            }
        )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "artifacts": entries,
    }
    validate_json(manifest, schema_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_path
