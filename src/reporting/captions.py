"""Generate complete data-driven caption macros from the caption registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import yaml

DIGIT_NAMES = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}
LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _escape_latex(value: str) -> str:
    return "".join(LATEX_ESCAPES.get(character, character) for character in value)


def caption_macro_name(artifact_id: str) -> str:
    """Convert an artifact ID to its generated caption macro name."""
    name = "".join(part.capitalize() for part in artifact_id.split("_"))
    name = re.sub(r"\d", lambda match: DIGIT_NAMES[match.group()], name)
    return name + "Caption"


def write_caption_macros(
    captions_path: Path,
    output_path: Path,
    *,
    sample_dates: Mapping[str, tuple[str, str] | str],
    data_vintage: str,
    calculated_takeaways: Mapping[str, str],
) -> Path:
    """Validate caption fields and write one macro per registered exhibit."""
    contract = yaml.safe_load(captions_path.read_text(encoding="utf-8"))
    entries = contract.get("exhibits", {})
    lines = []
    for artifact_id in sample_dates:
        entry = entries.get(artifact_id, {})
        title = entry.get("title")
        label = entry.get("label")
        takeaway = calculated_takeaways.get(artifact_id)
        if not title or not label or not takeaway:
            raise ValueError(
                f"Caption '{artifact_id}' lacks title, label, or takeaway."
            )
        if artifact_id not in sample_dates:
            raise ValueError(f"Caption '{artifact_id}' lacks generated sample dates.")
        sample = sample_dates[artifact_id]
        sample_text = sample if isinstance(sample, str) else "--".join(sample)
        source = entry.get("source_note")
        if not source:
            raise ValueError(f"Caption '{artifact_id}' lacks an explicit source note.")
        caption = (
            f"{title}. Sample: {sample_text}. "
            f"Data vintage: {data_vintage}. Source: {source}. {takeaway}"
        )
        caption = _escape_latex(re.sub(r"\s+", " ", caption))
        lines.append(rf"\newcommand{{\{caption_macro_name(artifact_id)}}}{{{caption}}}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
