"""Generate complete data-driven caption macros from the caption registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import yaml


def caption_macro_name(artifact_id: str) -> str:
    """Convert an artifact ID to its generated caption macro name."""
    return "".join(part.capitalize() for part in artifact_id.split("_")) + "Caption"


def write_caption_macros(
    captions_path: Path,
    output_path: Path,
    *,
    sample_dates: Mapping[str, tuple[str, str] | str],
    data_vintage: str,
    calculated_takeaways: Mapping[str, str],
) -> Path:
    """Validate caption fields and write one macro per registered exhibit."""
    entries = yaml.safe_load(captions_path.read_text(encoding="utf-8"))
    lines = []
    for artifact_id, entry in entries.items():
        title = entry.get("title")
        label = entry.get("label")
        takeaway = calculated_takeaways.get(artifact_id) or entry.get("takeaway")
        if not title or not label or not takeaway:
            raise ValueError(
                f"Caption '{artifact_id}' lacks title, label, or takeaway."
            )
        if artifact_id not in sample_dates:
            raise ValueError(f"Caption '{artifact_id}' lacks generated sample dates.")
        sample = sample_dates[artifact_id]
        sample_text = sample if isinstance(sample, str) else "--".join(sample)
        source = entry.get(
            "source", "Generated from the normalized core quarterly panel"
        )
        notes = "; ".join(entry.get("notes_required", []))
        caption = (
            f"{title}. Sample: {sample_text}. {notes}. "
            f"Data vintage: {data_vintage}. Source: {source}. {takeaway}"
        )
        caption = re.sub(r"\s+", " ", caption).replace("%", r"\%").replace("_", r"\_")
        lines.append(rf"\newcommand{{\{caption_macro_name(artifact_id)}}}{{{caption}}}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
