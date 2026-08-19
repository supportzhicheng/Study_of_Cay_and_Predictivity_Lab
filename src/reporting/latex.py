"""LaTeX report compilation with persistent success or failure logs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def compile_latex_report(reports_dir: Path) -> Path:
    """Compile the single report and always write the latexmk output log."""
    build_dir = reports_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    log_path = build_dir / "latex_build.log"
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        message = "latexmk is not installed. Install a TeX distribution with latexmk.\n"
        log_path.write_text(message, encoding="utf-8")
        raise RuntimeError(message.strip())
    command = [
        latexmk,
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-outdir={build_dir.resolve()}",
        "main.tex",
    ]
    completed = subprocess.run(
        command,
        cwd=reports_dir / "paper",
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"LaTeX compilation failed; see {log_path}")
    return build_dir / "main.pdf"
