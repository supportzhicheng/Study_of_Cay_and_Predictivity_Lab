"""Import a validated local substitute for a normalized source."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.data.cache import CachePaths, write_normalized_cache
from src.data.source_registry import get_source_spec
from src.settings import load_settings

SUPPORTED_EXTENSIONS = (".csv", ".parquet", ".xlsx", ".xls")


def find_local_input(source_id: str, input_dir: Path) -> Path:
    """Find the single supported file matching a source's registered stem."""
    spec = get_source_spec(source_id)
    candidates = sorted(input_dir.glob(f"{spec.filename_stem}.*"))
    supported = [
        path for path in candidates if path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if len(supported) > 1:
        names = ", ".join(path.name for path in supported)
        raise ValueError(f"Ambiguous local inputs for '{source_id}': {names}")
    if len(supported) == 1:
        return supported[0]
    if candidates:
        suffixes = ", ".join(sorted({path.suffix or "<none>" for path in candidates}))
        raise ValueError(
            f"Unsupported local input type for '{source_id}': {suffixes}. "
            f"Supported types: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    raise FileNotFoundError(
        f"No local input found for '{source_id}'. Expected "
        f"{spec.filename_stem} with one of: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def read_local_input(path: Path) -> pd.DataFrame:
    """Read one supported local tabular input."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported local input type: {suffix}")


def import_local_source(
    source_id: str,
    input_dir: Path,
    cache_dir: Path,
    *,
    vintage: str | None = None,
) -> CachePaths:
    """Validate one local source and write the normalized cache contract."""
    input_path = find_local_input(source_id, input_dir)
    frame = read_local_input(input_path)
    return write_normalized_cache(
        frame,
        source_id,
        cache_dir,
        vintage=vintage or date.today().isoformat(),
        retrieval_description=f"Validated local import from {input_path.name}",
        extra_metadata={"local_input_filename": input_path.name},
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--vintage")
    args = parser.parse_args(argv)

    settings = load_settings(argv=[])
    paths = import_local_source(
        args.source_id,
        args.input_dir or settings.p10_input_dir,
        args.cache_dir or settings.data_dir / "normalized",
        vintage=args.vintage,
    )
    print(paths.data)
    print(paths.metadata)


if __name__ == "__main__":
    main()
