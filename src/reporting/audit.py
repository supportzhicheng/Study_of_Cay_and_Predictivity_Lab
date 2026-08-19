"""Generated replication status summaries for text and LaTeX."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.table_r1 import (
    FAIL_REQUIRES_DIAGNOSIS,
    PASS_REVISED_VINTAGE,
    PASS_STRICT,
)


def write_replication_status(
    audit: pd.DataFrame, reports_dir: Path
) -> tuple[Path, Path]:
    """Write aggregate audit status and counts as plain text and TeX macros."""
    counts = audit["status"].value_counts()
    failures = int(counts.get(FAIL_REQUIRES_DIAGNOSIS, 0))
    revised = int(counts.get(PASS_REVISED_VINTAGE, 0))
    strict = int(counts.get(PASS_STRICT, 0))
    if failures:
        overall = FAIL_REQUIRES_DIAGNOSIS
    elif revised:
        overall = PASS_REVISED_VINTAGE
    else:
        overall = PASS_STRICT
    summary = f"{strict} strict, {revised} revised-vintage, {failures} failed checks"

    build_dir = reports_dir / "build"
    generated_dir = reports_dir / "paper" / "generated"
    build_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)
    text_path = build_dir / "replication_status.txt"
    tex_path = generated_dir / "replication_status.tex"
    text_path.write_text(f"{overall}\n{summary}\n", encoding="utf-8")
    escaped_overall = overall.replace("_", r"\_")
    tex_path.write_text(
        "\n".join(
            [
                rf"\newcommand{{\OverallReplicationStatus}}{{{escaped_overall}}}",
                rf"\newcommand{{\ReplicationAuditSummary}}{{{summary}}}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return text_path, tex_path
