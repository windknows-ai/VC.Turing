"""Load the user's config.toml, falling back to the bundled defaults."""

import shutil
import tomllib
from pathlib import Path

from .paths import CONFIG_FILE

DEFAULT_FILE = Path(__file__).with_name("default_config.toml")


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


OLD_WAKE_WORDS = ["嗨图灵", "嘿图灵", "Hey Turing"]
OLD_THRESHOLDS = {0.35: 1, 0.28: 2, 0.2: 3, 0.15: 4, 0.1: 5}


def _upgrade(path: Path, user: dict) -> dict:
    """Bring settings saved by older versions up to date, keeping the user's choices."""
    import tomlkit

    wake = user.get("wake", {})
    changes = {}
    if wake.get("keywords") == OLD_WAKE_WORDS:
        # Still the old default list: switch to the new one (adds "图灵", "Hi 图灵", ...).
        changes["keywords"] = None
    if "sensitivity" not in wake and "threshold" in wake:
        level = OLD_THRESHOLDS.get(round(float(wake["threshold"]), 2), 4)
        changes["sensitivity"] = max(level, 4 if level == 3 else level)
    if not changes:
        return user
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            doc["wake"].pop(key, None)
        else:
            doc["wake"][key] = value
    for old in ("threshold", "boost"):
        doc["wake"].pop(old, None)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load(path: Path = CONFIG_FILE) -> dict:
    """Return the merged config, creating the user's config file on first run."""
    defaults = tomllib.loads(DEFAULT_FILE.read_text(encoding="utf-8"))
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_FILE, path)
        return defaults
    user = _upgrade(path, tomllib.loads(path.read_text(encoding="utf-8")))
    return _merge(defaults, user)


def ui_language(cfg: dict | None = None) -> str:
    """'zh' or 'en' for Turing's windows: the setting, or Windows' own display language."""
    choice = (cfg or load()).get("app", {}).get("language", "auto")
    if choice in ("zh", "en"):
        return choice
    import ctypes

    primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    return "zh" if primary == 0x04 else "en"  # 0x04: Chinese (any region)


def save_section(section: str, values: dict, path: Path = CONFIG_FILE) -> None:
    """Update one [section] of the user's config, keeping their comments and layout."""
    import tomlkit

    load(path)  # make sure the file exists
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    if section not in doc:
        doc[section] = tomlkit.table()
    for key, value in values.items():
        doc[section][key] = value
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
