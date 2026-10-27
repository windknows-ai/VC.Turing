"""A short text record of the recent conversation, kept apart from the AI's working
history.

The working history (with tool calls and screenshots) is cleared often to keep requests
small and fast. This recap survives that, and restarts and crashes too (it's saved to
disk), so "继续刚才那个任务" still makes sense to the AI later on.
"""

import json
import threading
import time

from .paths import DATA_DIR, write_text_safely

FILE = DATA_DIR / "memory.json"
KEEP = 8                 # exchanges remembered
MAX_AGE = 2 * 3600       # older than this is no longer "recent"
MAX_CHARS = 300          # per message, so the recap stays small


class Memory:
    def __init__(self, path=FILE):
        self._path = path
        self._lock = threading.Lock()
        self._items: list[dict] = []
        try:
            self._items = json.loads(path.read_text(encoding="utf-8"))[-KEEP:]
        except (OSError, ValueError):
            pass

    def add(self, user: str, assistant: str):
        with self._lock:
            self._items.append({"t": time.time(), "user": user[:MAX_CHARS], "assistant": assistant[:MAX_CHARS]})
            self._items = self._items[-KEEP:]
            items = list(self._items)
        try:
            write_text_safely(self._path, json.dumps(items, ensure_ascii=False))
        except OSError:
            pass

    def recap(self) -> str:
        """The recent exchanges as text to start a fresh AI conversation with ('' if none)."""
        now = time.time()
        with self._lock:
            recent = [i for i in self._items if now - i["t"] < MAX_AGE]
        if not recent:
            return ""
        lines = []
        for item in recent:
            ago = int((now - item["t"]) / 60)
            when = "just now" if ago < 1 else f"{ago} min ago"
            lines.append(f"- ({when}) User: {item['user']}\n  You: {item['assistant']}")
        return ("Recent conversation with the user, oldest first (for context: they may refer "
                "back to it, e.g. \"continue that task\"):\n" + "\n".join(lines))

    def clear(self):
        with self._lock:
            self._items = []
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
