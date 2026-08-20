"""Load and validate the sole report exhibit registry."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from src.data.source_registry import SOURCE_REGISTRY


def load_report_contract(path: Path, project_root: Path) -> dict:
    """Validate exhibit labels, citations, source IDs, and explicit source notes."""
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    exhibits = contract.get("exhibits", {})
    if not exhibits:
        raise ValueError("Report contract must declare exhibits.")

    bibliography = (project_root / "reports" / "paper" / "references.bib").read_text(
        encoding="utf-8"
    )
    citation_keys = set(re.findall(r"@[A-Za-z]+\{([^,]+),", bibliography))
    extension_manifest = yaml.safe_load(
        (project_root / "config" / "extension_sources.yml").read_text(encoding="utf-8")
    )
    source_ids = set(SOURCE_REGISTRY) | set(extension_manifest["sources"])
    labels: set[str] = set()
    for artifact_id, entry in exhibits.items():
        required = {
            "kind",
            "number",
            "title",
            "label",
            "section",
            "role",
            "paths",
            "sample_rule",
            "benchmark_citations",
            "provider_citations",
            "source_ids",
            "source_note",
        }
        missing = sorted(required - set(entry))
        if missing:
            raise ValueError(f"Exhibit '{artifact_id}' is missing fields: {missing}")
        if entry["label"] in labels:
            raise ValueError(f"Duplicate exhibit label: {entry['label']}")
        labels.add(entry["label"])
        unknown_citations = sorted(
            (set(entry["benchmark_citations"]) | set(entry["provider_citations"]))
            - citation_keys
        )
        if unknown_citations:
            raise ValueError(
                f"Exhibit '{artifact_id}' has unknown citations: {unknown_citations}"
            )
        unknown_sources = sorted(set(entry["source_ids"]) - source_ids)
        if unknown_sources:
            raise ValueError(
                f"Exhibit '{artifact_id}' has unknown source IDs: {unknown_sources}"
            )
        if "default" in entry["source_note"].lower():
            raise ValueError(f"Exhibit '{artifact_id}' uses a default source note.")
    return contract
