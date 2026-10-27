"""Where Turing keeps its config and downloaded models on the user's machine."""

import os
from pathlib import Path


def _base(env: str, fallback: Path) -> Path:
    return Path(os.environ.get(env) or fallback)


# Config lives in %APPDATA%\Turing, models (large, re-downloadable) in %LOCALAPPDATA%\Turing.
CONFIG_DIR = Path(os.environ.get("TURING_CONFIG_DIR") or _base("APPDATA", Path.home()) / "Turing")
DATA_DIR = Path(os.environ.get("TURING_DATA_DIR") or _base("LOCALAPPDATA", Path.home()) / "Turing")
MODELS_DIR = DATA_DIR / "models"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def write_text_safely(path: Path, text: str):
    """Write a file without ever leaving it half-written: write a copy, then swap it in.

    Some setups refuse the swap ("can't move the file to a different drive"): Windows
    app-package virtualization keeps a private copy of AppData for apps started from a
    packaged app. Then the file is written directly instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        path.write_text(text, encoding="utf-8")
        tmp.unlink(missing_ok=True)
