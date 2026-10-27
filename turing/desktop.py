"""Entry point for the desktop app: `pythonw -m turing.desktop [page] [--after PID]`."""

import faulthandler
import sys
import threading
import traceback

from .paths import DATA_DIR

_LOG_LIMIT = 2_000_000  # bytes; console.log starts over beyond this

if sys.stdout is None or sys.stderr is None:
    # Under pythonw there is no console: sys.stdout/stderr are None, and code that writes
    # to them (ours or a library's) fails, often silently in a background thread. Send
    # it all to a file instead, which also keeps any crash traceback for debugging.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "console.log"
    big = log_path.exists() and log_path.stat().st_size > _LOG_LIMIT
    _console = open(log_path, "w" if big else "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _console
    sys.stderr = sys.stderr or _console

# Native crashes and errors in background threads end up in the log too.
faulthandler.enable(file=sys.stderr)
threading.excepthook = lambda a: traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback,
                                                           file=sys.stderr)

from . import lifecycle  # noqa: E402  (after the redirect above)
from .control_center import run  # noqa: E402


def main(argv: list[str]):
    page = "home"
    after = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--after" and args:
            after = int(args.pop(0))
        else:
            page = arg
    if after:
        lifecycle.wait_for_exit(after)  # a restart: let the old Turing finish quitting
    try:
        run(page)
    except Exception:
        traceback.print_exc()
        # Settings and the conversation recap are already on disk; start again unless
        # Turing keeps crashing.
        if lifecycle.note_crash():
            lifecycle.launch_again()
        raise


if __name__ == "__main__":
    main(sys.argv[1:])
