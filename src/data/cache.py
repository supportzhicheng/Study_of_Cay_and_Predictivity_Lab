"""Normalized source cache and metadata writers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.contracts import normalize_quarterly_source
from src.data.source_registry import get_source_spec


@dataclass(frozen=True)
class CachePaths:
    """Paths written for one normalized source cache."""

    data: Path
    metadata: Path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_normalized_cache(
    frame: pd.DataFrame,
    source_id: str,
    cache_dir: Path,
    *,
    vintage: str,
    retrieval_description: str,
    extra_metadata: dict[str, Any] | None = None,
) -> CachePaths:
    """Validate and write a source Parquet cache with auditable metadata."""
    spec = get_source_spec(source_id)
    normalized = normalize_quarterly_source(frame, source_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    data_path = cache_dir / f"{spec.filename_stem}.parquet"
    metadata_path = cache_dir / f"{spec.filename_stem}.metadata.json"
    normalized.to_parquet(data_path)

    metadata: dict[str, Any] = {
        "source_id": source_id,
        "provider": spec.provider,
        "access_class": spec.access_class,
        "vintage": vintage,
        "retrieval_description": retrieval_description,
        "sample_start": str(normalized.index.min()),
        "sample_end": str(normalized.index.max()),
        "columns": normalized.columns.tolist(),
        "row_count": len(normalized),
        "missing_counts": {
            column: int(count) for column, count in normalized.isna().sum().items()
        },
        "sha256": sha256_file(data_path),
    }
    if extra_metadata:
        protected = set(metadata) & set(extra_metadata)
        if protected:
            names = ", ".join(sorted(protected))
            raise ValueError(f"Extra metadata cannot replace required fields: {names}")
        metadata.update(extra_metadata)

    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return CachePaths(data=data_path, metadata=metadata_path)
