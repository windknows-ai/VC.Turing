"""Starting with Windows, restarting, and coming back after a crash."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .paths import DATA_DIR

ROOT = Path(__file__).resolve().parent.parent
CRASHES = DATA_DIR / "crashes.json"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    return exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe


def startup_shortcut() -> Path:
    import win32com.client

    folder = win32com.client.Dispatch("WScript.Shell").SpecialFolders("Startup")
    return Path(folder) / "图灵.lnk"


def autostart_enabled() -> bool:
    try:
        return startup_shortcut().exists()
    except Exception:
        return False


def set_autostart(enabled: bool):
    """Start Turing (as just the orb) when Windows starts."""
    import win32com.client

    path = startup_shortcut()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(path))
    link.TargetPath = str(_pythonw())
    link.Arguments = "-m turing.desktop"
    link.WorkingDirectory = str(ROOT)
    link.IconLocation = str(ROOT / "turing" / "assets" / "turing.ico")
    link.Description = "图灵语音助手"
    link.Save()


def launch_again(after_pid: int | None = None, page: str = "home"):
    """Start a new Turing that waits for this one (`after_pid`) to exit first."""
    args = [str(_pythonw()), "-m", "turing.desktop", page]
    if after_pid:
        args += ["--after", str(after_pid)]
    subprocess.Popen(args, cwd=str(ROOT), creationflags=subprocess.DETACHED_PROCESS)


def wait_for_exit(pid: int, timeout: float = 20):
    import psutil

    try:
        psutil.Process(pid).wait(timeout)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
        pass


def note_crash() -> bool:
    """Record a crash; returns True if it's OK to restart (not crashing in a loop)."""
    now = time.time()
    try:
        recent = [t for t in json.loads(CRASHES.read_text()) if now - t < 600]
    except (OSError, ValueError):
        recent = []
    recent.append(now)
    try:
        CRASHES.parent.mkdir(parents=True, exist_ok=True)
        CRASHES.write_text(json.dumps(recent))
    except OSError:
        pass
    return len(recent) <= 3  # more than 3 crashes in 10 minutes: stop and let the user look


def own_pid() -> int:
    return os.getpid()
