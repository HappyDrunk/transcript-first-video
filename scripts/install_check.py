#!/usr/bin/env python3
"""Check that an installed transcript-first-video skill is complete."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 12)  # Keep in sync with .github/workflows/gate.yml.

# These paths let the check work on a copied source directory that has no .git.
# In a checkout, git's tracked-file list also catches files added in later releases.
FALLBACK_FILES = (
    "pyproject.toml",
    "scripts/c04c_review.py",
    "scripts/claim_ground_check.py",
    "scripts/coverage_check.py",
    "scripts/extract_quote.py",
    "scripts/install_check.py",
    "scripts/knowledge_note.py",
    "scripts/quality_gate.py",
    "scripts/render_reading_note.py",
    "scripts/run_evidence.py",
    "scripts/screen_ocr.py",
    "scripts/setup.py",
    "scripts/smoke.sh",
    "scripts/test_claim_ground_check.py",
    "scripts/test_coverage_check.py",
    "scripts/test_gate.py",
    "scripts/test_no_overfit.py",
    "scripts/test_regressions.py",
    "scripts/verify_note.py",
    "scripts/verify_report.py",
    "scripts/verify_rules.py",
    "scripts/x_host.py",
    "scripts/youtube_host.py",
    "scripts/user_prefs.py",
    "references/delivery-format.md",
    "references/review-guide.md",
    "references/host-delivery.md",
    "references/note-examples.md",
    "references/pitfalls.md",
    "references/rules.md",
)


def required_files(root: Path) -> list[str]:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            return list(FALLBACK_FILES)
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "scripts", "references"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        tracked = [name for name in result.stdout.split("\0") if name]
        files = set(tracked)
        files.add("pyproject.toml")
        files.add("scripts/install_check.py")
        return sorted(files)
    except (OSError, subprocess.SubprocessError):
        return list(FALLBACK_FILES)


def skill_version(root: Path) -> str:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            raise subprocess.CalledProcessError(1, "git rev-parse --show-toplevel")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        commit = result.stdout.strip()
        if commit:
            return commit
    except (OSError, subprocess.SubprocessError):
        pass
    version_file = root / "VERSION"
    if version_file.is_file():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "unknown"


def files_check() -> int:
    print(f"skill_version: {skill_version(ROOT)}")
    missing = [name for name in required_files(ROOT) if not (ROOT / name).is_file()]
    if missing:
        print("Missing required installation files:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print("Installation check passed.")
    return 0


def venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def ffmpeg_fix() -> str:
    return {
        "win32": "winget install --id Gyan.FFmpeg -e",
        "darwin": "brew install ffmpeg",
    }.get(sys.platform, "sudo apt install -y ffmpeg")


def probe(python: Path, code: str) -> str:
    try:
        result = subprocess.run(
            [str(python), "-c", code], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def doctor() -> list[dict[str, str | None]]:
    checks: list[dict[str, str | None]] = []

    def add(name: str, found: bool, level: str, detail: str, fix: str) -> None:
        checks.append({"name": name, "level": "OK" if found else level, "detail": detail,
                       "fix": None if found else fix})

    file_errors = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(file_errors):
        files_ok = files_check() == 0
    add("files", files_ok, "FAIL", "installation complete" if files_ok else " ".join(
        line.strip() for line in file_errors.getvalue().splitlines()
    ), "git pull (or recopy the repository)")

    venv_dir = ROOT / ".venv"
    vpy = venv_python(venv_dir)
    has_venv = venv_dir.is_dir() and vpy.is_file()
    python = vpy if has_venv else Path(sys.executable)
    version = probe(python, 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    parts = version.split(".")
    version_ok = len(parts) == 3 and all(part.isascii() and part.isdecimal() for part in parts)
    minimum = ".".join(map(str, MIN_PYTHON))
    add("Python", version_ok and tuple(map(int, parts[:2])) >= MIN_PYTHON, "FAIL",
        f"{version if version_ok else 'version unavailable'} (need {minimum} or later)",
        f"Install Python {minimum} or later from https://www.python.org/downloads/")
    add(".venv", has_venv, "WARN", "using .venv Python" if has_venv else "using current Python",
        "python scripts/setup.py")

    for name, module, level, fix in (
        ("yt-dlp", "yt_dlp", "FAIL", "python scripts/setup.py --base-only"),
        ("rapidocr", "rapidocr", "WARN", "python scripts/setup.py"),
        ("onnxruntime", "onnxruntime", "WARN", "python scripts/setup.py"),
    ):
        found = probe(python, f"import importlib.util as u; print(u.find_spec({module!r}) is not None)") == "True"
        add(name, found, level, "found" if found else "module not found", fix)
    has_ffmpeg = shutil.which("ffmpeg") is not None
    add("ffmpeg", has_ffmpeg, "WARN", "found on PATH" if has_ffmpeg else "not found on PATH", ffmpeg_fix())
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor", action="store_true", help="Also check Python, dependencies, and FFmpeg")
    parser.add_argument("--json", action="store_true", help="Print doctor results as JSON")
    args = parser.parse_args(argv)
    if not (args.doctor or args.json):
        return files_check()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    checks = doctor()
    ok = all(check["level"] != "FAIL" for check in checks)
    if args.json:
        print(json.dumps({"ok": ok, "checks": checks}))
    else:
        for check in checks:
            line = f"[{check['level']}] {check['name']}: {check['detail']}"
            if check["fix"]:
                line += f" | Fix: {check['fix']}"
            print(line.encode("ascii", errors="backslashreplace").decode("ascii"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
