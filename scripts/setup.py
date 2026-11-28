#!/usr/bin/env python3
"""Install transcript-first-video dependencies in a virtual environment."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from install_check import MIN_PYTHON, ffmpeg_fix, probe, venv_python

ROOT = Path(__file__).resolve().parents[1]
DependencyGroups = dict[str, list[str | dict[str, str]]]

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


# Python 3.10 only needs the dependency-group subset of TOML: arrays of
# quoted strings or include-group tables, with comments and trailing commas.
_TABLE = re.compile(r"^[ \t]*(?:\[([^\[\]\r\n]+)\]|\[\[[^\[\]\r\n]+\]\])[ \t]*(?:#[^\r\n]*)?$",
                    re.MULTILINE)
_GAP = re.compile(r"(?:\s|#[^\n]*)*")
_STRING = r"""(?:"(?:[^"\\\r\n]|\\[^\r\n])*"|'[^'\r\n]*')"""
_GROUP = re.compile(rf"({_STRING}|[\w-]+)[ \t]*=[ \t]*\[")
_ITEM = re.compile(rf'(?P<package>{_STRING})|'
                   rf"""\{{[ \t]*(?:include-group|"include-group"|'include-group')[ \t]*=[ \t]*"""
                   rf'(?P<include>{_STRING})[ \t]*\}}')


def _string(token: str) -> str:
    return token[1:-1] if token.startswith("'") else json.loads(token)


def parse_dependency_groups_fallback(text: str) -> DependencyGroups:
    tables = list(_TABLE.finditer(text))
    sections = [i for i, match in enumerate(tables)
                if (match[1] or "").strip() in {"dependency-groups", '"dependency-groups"', "'dependency-groups'"}]
    if len(sections) != 1:
        raise ValueError("expected one [dependency-groups] table")
    section = sections[0]
    end = tables[section + 1].start() if section + 1 < len(tables) else len(text)
    body = text[tables[section].end():end]
    groups: DependencyGroups = {}
    pos = _GAP.match(body).end()
    while pos < len(body):
        group = _GROUP.match(body, pos)
        if group is None:
            raise ValueError("expected a dependency group array")
        name = _string(group[1]) if group[1][0] in "\"'" else group[1]
        if name in groups:
            raise ValueError(f"duplicate dependency group: {name}")
        entries: list[str | dict[str, str]] = []
        pos = _GAP.match(body, group.end()).end()
        while body[pos:pos + 1] != "]":
            item = _ITEM.match(body, pos)
            if item is None:
                raise ValueError(f"invalid entry in dependency group: {name}")
            if item["include"] is not None:
                entries.append({"include-group": _string(item["include"])})
            else:
                entries.append(_string(item["package"]))
            pos = _GAP.match(body, item.end()).end()
            if body[pos:pos + 1] == ",":
                pos = _GAP.match(body, pos + 1).end()
            elif body[pos:pos + 1] != "]":
                raise ValueError(f"expected a comma or closing bracket in dependency group: {name}")
        groups[name] = entries
        pos = _GAP.match(body, pos + 1).end()
    return groups


def load_dependency_groups(path: Path) -> DependencyGroups:
    text = path.read_text(encoding="utf-8")
    if tomllib is None:
        return parse_dependency_groups_fallback(text)
    groups = tomllib.loads(text).get("dependency-groups")
    if not isinstance(groups, dict):
        raise ValueError("expected a [dependency-groups] table")
    return groups


def expand_groups(groups: DependencyGroups, selected: list[str]) -> list[str]:
    packages: dict[str, None] = {}
    expanded: set[str] = set()

    def visit(name: str, parents: tuple[str, ...]) -> None:
        if name in parents:
            raise ValueError("dependency group cycle: " + " -> ".join((*parents, name)))
        if name in expanded:
            return
        entries = groups.get(name)
        if not isinstance(entries, list):
            raise ValueError(f"missing or invalid dependency group: {name}")
        for entry in entries:
            if isinstance(entry, str) and entry.strip() and not entry.lstrip().startswith("-"):
                packages.setdefault(entry, None)
            elif (isinstance(entry, dict) and entry.keys() == {"include-group"}
                  and isinstance(entry["include-group"], str)):
                visit(entry["include-group"], (*parents, name))
            else:
                raise ValueError(f"invalid entry in dependency group: {name}")
        expanded.add(name)

    for name in selected:
        visit(name, ())
    return list(packages)


def shell_command(args: list[str]) -> str:
    if sys.platform == "win32":
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
    return shlex.join(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv", help="Virtual environment directory (default: .venv in the skill)")
    parser.add_argument("--base-only", action="store_true", help="Install caption dependencies only")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without creating a venv or installing packages")
    parser.add_argument("--json", action="store_true", help="Print a JSON installation report")
    args = parser.parse_args(argv)

    directory = args.venv.expanduser().absolute()
    python = venv_python(directory)
    reuse = python.is_file()
    groups = ["base"] if args.base_only else ["base", "screen"]
    packages: list[str] = []
    commands: list[list[str]] = []
    has_ffmpeg = shutil.which("ffmpeg") is not None
    fix = None if has_ffmpeg else ffmpeg_fix()
    next_args = [str(python), str(ROOT / "scripts/install_check.py"), "--doctor"]
    if directory != ROOT / ".venv":
        next_args.extend(["--venv", str(directory)])
    next_command = shell_command(next_args)

    code = 0
    minimum = ".".join(map(str, MIN_PYTHON))
    if reuse:
        version = probe(python, 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        match = re.fullmatch(r"([0-9]+)\.([0-9]+)", version)
        if not match or tuple(map(int, match.groups())) < MIN_PYTHON:
            detail = f"found Python {version}" if match else "could not determine the Python version"
            print(f"Cannot reuse {directory}: {detail}. Delete this venv and rerun setup with "
                  f"Python {minimum} or later.", file=sys.stderr)
            code = 1
    elif sys.version_info[:2] < MIN_PYTHON:
        version = ".".join(map(str, sys.version_info[:2]))
        print(f"Cannot create a venv with Python {version}. Upgrade to Python {minimum} or later and rerun setup.",
              file=sys.stderr)
        code = 1

    if code == 0:
        try:
            packages = expand_groups(load_dependency_groups(ROOT / "pyproject.toml"), groups)
        except (OSError, ValueError, RecursionError) as exc:
            print(f"Could not parse pyproject.toml: {exc}", file=sys.stderr)
            code = 2

    if code == 0:
        if not reuse:
            commands.append([sys.executable, "-m", "venv", str(directory)])
        commands.append([str(python), "-m", "pip", "install", *packages])
        try:
            for command in commands:
                if not args.json:
                    print(shell_command(command), flush=True)
                if not args.dry_run:
                    subprocess.run(command, check=True, stdout=sys.stderr if args.json else None)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"Installation failed: {exc}", file=sys.stderr)
            code = 1

    if fix:
        print(f"[WARN] ffmpeg not found on PATH. Fix: {fix}", file=sys.stderr)
    if args.json:
        print(json.dumps({
            "ok": code == 0, "venv": str(directory), "python": str(python),
            "groups": groups, "packages": packages, "commands": commands,
            "ffmpeg": {"found": has_ffmpeg, "fix": fix}, "next": next_command,
        }))
    elif code == 0:
        print(f"Next: {next_command}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
