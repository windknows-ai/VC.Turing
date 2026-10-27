"""Personas: saved sets of custom instructions for the AI (role, answer style, rules),
so the user can switch how Turing behaves in one click. Kept in personas.json next to
config.toml."""

import json
import threading

from .paths import CONFIG_DIR, write_text_safely

FILE = CONFIG_DIR / "personas.json"
_lock = threading.Lock()

DEFAULTS = {
    "active": "默认",
    "presets": [
        {"name": "默认", "role": "", "style": "", "rules": ""},
        {"name": "简洁", "role": "",
         "style": "能一句话说完就一句话，不寒暄，不解释原因，只说结果。", "rules": ""},
        {"name": "耐心讲解", "role": "一位耐心的老师",
         "style": "解释时先说结论，再用一两个生活中的例子讲明白。", "rules": "遇到专业名词要顺带解释。"},
        {"name": "英语陪练", "role": "an English speaking partner",
         "style": "Reply in simple, natural English even if the user speaks Chinese.",
         "rules": "If the user makes an English mistake, gently give the correct sentence first."},
    ],
}


def load() -> dict:
    with _lock:
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
            if isinstance(data.get("presets"), list) and data["presets"]:
                return data
        except (OSError, ValueError):
            pass
        return json.loads(json.dumps(DEFAULTS))


def save(data: dict) -> None:
    presets = [p for p in data.get("presets", []) if str(p.get("name", "")).strip()]
    if not presets:
        presets = DEFAULTS["presets"][:1]
    names = [p["name"] for p in presets]
    active = data.get("active") if data.get("active") in names else names[0]
    clean = {"active": active, "presets": [
        {k: str(p.get(k, "")).strip() for k in ("name", "role", "style", "rules")} for p in presets]}
    with _lock:
        write_text_safely(FILE, json.dumps(clean, ensure_ascii=False, indent=1))


def instructions(data: dict | None = None) -> str:
    """The active persona as text for the system prompt ('' when it adds nothing)."""
    data = data or load()
    preset = next((p for p in data["presets"] if p["name"] == data["active"]), None)
    if not preset:
        return ""
    parts = []
    if preset.get("role"):
        parts.append(f"Your role: {preset['role']}")
    if preset.get("style"):
        parts.append(f"How to answer: {preset['style']}")
    if preset.get("rules"):
        parts.append(f"Also: {preset['rules']}")
    if not parts:
        return ""
    return ("The user set these instructions for you (persona \"" + preset["name"] + "\"). "
            "Follow them, but keep replies short and speakable, and don't break the rules above.\n"
            + "\n".join(parts))


def mtime() -> float:
    try:
        return FILE.stat().st_mtime
    except OSError:
        return 0.0
