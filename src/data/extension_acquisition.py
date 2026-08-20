"""Acquire or import declared extension source caches."""

from __future__ import annotations

import hashlib
import io
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import yaml

from src.data.build_extension_sources import (
    FRED_HPI_IDS,
    FRED_PCPI_IDS,
    FRED_POP_IDS,
    _ensure_dfa_detail_csv,
    _fetch_fred_series,
)
from src.settings import Settings

Z1_CSV_PACKAGE_URL = (
    "https://www.federalreserve.gov/releases/z1/current/z1_csv_files.zip"
)


def sha256(path: Path) -> str:
    """Return the SHA-256 digest for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(settings: Settings) -> dict:
    path = settings.project_root / "config" / "extension_sources.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _declared_sources(settings: Settings) -> list[tuple[Path, str]]:
    manifest = _manifest(settings)
    paths: list[tuple[Path, str]] = []
    for source_id in ("z1_s14_b", "z1_s1m_b", "dfa_zip", "qqq_market"):
        spec = manifest["sources"][source_id]
        paths.append((Path(spec["cache_path"]), str(spec["sha256"])))
    for spec in manifest["sources"]["fred"]["series"].values():
        paths.append((Path(spec["cache_path"]), str(spec["sha256"])))
    return paths


def _copy_available_bundle(settings: Settings) -> None:
    for relative, _ in _declared_sources(settings):
        destination = settings.project_root / relative
        source_candidates = (
            settings.extension_input_dir / relative.name,
            settings.extension_input_dir / relative,
        )
        source = next((path for path in source_candidates if path.exists()), None)
        if source is not None and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def _acquire_latest_qqq(path: Path) -> None:
    if path.exists():
        return
    import yfinance as yf

    raw = yf.download(
        "QQQ",
        start="2023-01-03",
        end="2026-04-02",
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if raw.empty:
        raise RuntimeError("Latest QQQ acquisition returned no observations.")
    if isinstance(raw.columns, pd.MultiIndex):
        price = raw["Adj Close"].iloc[:, 0]
    else:
        price = raw["Adj Close"]
    output = pd.DataFrame({"date": price.index.strftime("%Y-%m-%d"), "price": price})
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)


def _acquire_latest_z1(raw_dir: Path) -> None:
    destinations = {
        "csv/S14_b.csv": raw_dir / "FRB_Z1_S14_b_Q.csv",
        "csv/S1M_b.csv": raw_dir / "FRB_Z1_S1M_b_Q.csv",
    }
    if all(path.exists() for path in destinations.values()):
        return
    request = urllib.request.Request(
        Z1_CSV_PACKAGE_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    raw_dir.mkdir(parents=True, exist_ok=True)
    for member, destination in destinations.items():
        destination.write_bytes(archive.read(member))


def acquire_extension_sources(settings: Settings) -> list[Path]:
    """Populate declared raw caches for baseline or latest acquisition mode."""
    mode = settings.extension_acquisition_mode
    if mode not in {"baseline", "latest"}:
        raise ValueError("EXTENSION_ACQUISITION_MODE must be baseline or latest.")
    _copy_available_bundle(settings)

    if mode == "latest":
        _acquire_latest_z1(settings.extension_raw_dir)
        _ensure_dfa_detail_csv(settings.extension_raw_dir, allow_network=True)
        for series_id in {
            *FRED_HPI_IDS.values(),
            *FRED_PCPI_IDS.values(),
            *FRED_POP_IDS.values(),
        }:
            _fetch_fred_series(
                series_id, settings.extension_raw_dir, allow_network=True
            )
        _acquire_latest_qqq(settings.extension_raw_dir / "market" / "QQQ.csv")

    missing: list[str] = []
    mismatched: list[str] = []
    resolved: list[Path] = []
    for relative, expected_hash in _declared_sources(settings):
        path = settings.project_root / relative
        if not path.exists():
            missing.append(str(path))
            continue
        if mode == "baseline" and sha256(path) != expected_hash:
            mismatched.append(str(path))
        resolved.append(path)

    if missing:
        raise FileNotFoundError(
            "Missing extension source bundle files: "
            + ", ".join(missing)
            + f". Supply them under EXTENSION_INPUT_DIR={settings.extension_input_dir}."
        )
    if mismatched:
        raise ValueError(
            "Baseline extension source hash mismatch: " + ", ".join(mismatched)
        )
    return resolved


def extension_sources_current(settings: Settings) -> bool:
    """Return whether declared caches satisfy the selected acquisition mode."""
    for relative, expected_hash in _declared_sources(settings):
        path = settings.project_root / relative
        if not path.exists():
            return False
        if (
            settings.extension_acquisition_mode == "baseline"
            and sha256(path) != expected_hash
        ):
            return False
    return True
