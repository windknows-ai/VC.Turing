"""The Turing desktop app: a floating orb that listens, plus a window to connect an AI
and test the microphone and voice.

    python -m turing.desktop          (or double-click the 图灵 shortcut)
    python -m turing --setup          opens it on the AI page
"""

import ctypes
from pathlib import Path

WEB = Path(__file__).with_name("web")
_MUTEX_NAME = "Local\\TuringVoiceAssistantApp"


def _already_running() -> bool:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def run(tab: str = "home") -> None:
    """Run the app until the user quits it from the orb's menu.

    Closing the main window only hides it: Turing keeps listening in the orb.
    """
    if _already_running():
        from .. import config

        en = config.ui_language() == "en"
        ctypes.windll.user32.MessageBoxW(
            None, "Turing is already running. Click the blue orb in the bottom-right corner to open it."
            if en else "图灵已经在运行了。点屏幕右下角的蓝色小圆球就能打开它。",
            "Turing" if en else "图灵", 0x40)
        return

    import webview

    from .. import config
    from ..engine import Engine
    from .api import ControlCenterApi
    from .floating import Floating

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    engine = Engine()
    api = ControlCenterApi(engine)
    floating = Floating(engine)
    api._floating = floating

    # The window opens on first run (to pick an AI) or when a page was asked for;
    # otherwise Turing starts as just the orb.
    show_main = tab != "home" or not config.load()["ai"]["provider"]
    main = webview.create_window(
        "图灵",
        url=(WEB / "index.html").as_uri() + f"#{tab}",
        js_api=api,
        width=1120,
        height=780,
        min_size=(900, 640),
        hidden=not show_main,
    )
    floating.main_visible = show_main
    floating.create(webview, WEB, api, main)

    engine.start()
    webview.start(floating.started)
    engine.stop()
    if not config.load()["ai"]["provider"]:
        # Quit without choosing: remember that, so we don't keep asking.
        config.save_section("ai", {"provider": "none"})
