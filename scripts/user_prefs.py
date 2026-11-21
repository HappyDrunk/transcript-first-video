"""Store explicitly saved delivery preferences outside the workspace."""

import json
import os
import sys
import tempfile
from pathlib import Path

import knowledge_note


VALID_LANGUAGES = ("中文", "英文", "中英文对照")
VALID_READING_LEVELS = knowledge_note.READING_LEVELS


def prefs_path(env=None) -> Path:
    env = os.environ if env is None else env
    if sys.platform == "win32" or os.name == "nt":
        root = Path(appdata) if (appdata := env.get("APPDATA")) else Path.home() / "AppData" / "Roaming"
    else:
        root = Path(config) if (config := env.get("XDG_CONFIG_HOME")) else Path.home() / ".config"
    return root / "transcript-first-video" / "prefs.json"


def _valid_preferences(language: object, reading_level: object) -> bool:
    return (type(language) is str and language in VALID_LANGUAGES
            and type(reading_level) is str and reading_level in VALID_READING_LEVELS)


def load_prefs(path: Path | None = None) -> dict[str, str]:
    target = prefs_path() if path is None else path
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    if (isinstance(data, dict) and data.keys() == {"language", "reading_level"}
            and _valid_preferences(data["language"], data["reading_level"])):
        return data
    return {}


def save_prefs(language: str, reading_level: str, path: Path | None = None) -> Path:
    if not _valid_preferences(language, reading_level):
        raise ValueError("invalid language or reading_level preference")
    target = prefs_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
            temp = Path(staged.name)
            data = {"language": language, "reading_level": reading_level}
            staged.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        temp.replace(target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return target


def resolve_reading_level(requested: str | None, previous: dict) -> tuple[str, str]:
    if requested is not None:
        knowledge_note.closing_heading_for_level(requested)
        return requested, "request"
    try:
        existing = knowledge_note.read_reading_level(previous)
    except ValueError:
        existing = None
    if existing is not None:
        return existing, previous["reading_level_source"]
    if saved := load_prefs():
        return saved["reading_level"], "saved"
    return "plain", "default"
