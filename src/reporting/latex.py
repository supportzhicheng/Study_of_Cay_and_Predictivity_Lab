"""LaTeX report compilation with persistent success or failure logs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def compile_latex_report(reports_dir: Path) -> Path:
    """Compile the single report and always write the compiler output log."""
    build_dir = reports_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    log_path = build_dir / "latex_build.log"
    environment_bin = Path(sys.executable).resolve().parent
    latexmk = shutil.which("latexmk")
    tectonic = shutil.which("tectonic")
    if latexmk is None and (environment_bin / "latexmk").exists():
        latexmk = str(environment_bin / "latexmk")
    if tectonic is None and (environment_bin / "tectonic").exists():
        tectonic = str(environment_bin / "tectonic")
    if latexmk is None and tectonic is None:
        message = (
            "No LaTeX compiler is installed. Install a TeX distribution with "
            "latexmk or install Tectonic.\n"
        )
        log_path.write_text(message, encoding="utf-8")
        raise RuntimeError(message.strip())
    if latexmk is not None:
        command = [
            latexmk,
            "-pdf",
            "-g",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-outdir={build_dir.resolve()}",
            "main.tex",
        ]
    else:
        command = [
            tectonic,
            "--keep-logs",
            "--print",
            "--outdir",
            str(build_dir.resolve()),
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
