"""The floating orb: Turing as a small always-on-top dot on the desktop, with a speech
bubble beside it for what you said and what it answered.

Two small frameless, transparent, always-on-top windows that never take the keyboard
focus (so typing into other apps keeps working): the orb, and the bubble, which only
exists on screen while there's something to show.
"""

import ctypes
import threading

import win32api
import win32con

from .. import config

ORB = 96                  # orb window size (logical px); the orb itself is 64 px in the middle
BUBBLE_W, BUBBLE_H = 360, 240
MARGIN = 24               # from the screen edge for the default spot


def _scale() -> float:
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
    except (AttributeError, OSError):
        return 1.0


def default_position() -> tuple[int, int]:
    """Bottom-right of the main screen, just above the taskbar (logical px)."""
    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    s = _scale()
    return int(right / s) - ORB - MARGIN, int(bottom / s) - ORB - MARGIN


def as_tool_window(window):
    """pywebview `before_show` handler: give the window the tool-window style, so it gets
    no taskbar button and stays out of Alt+Tab, like a desktop pet.

    It must happen before the window is first shown. Restyling afterwards leaves a
    taskbar button behind, and re-showing a never-focused window makes it flash there.
    Runs on the UI thread; ctypes (unlike pywin32) also lets go of Python's lock.

    Also makes the background really see-through. pywebview's transparency only works
    if WebView2 happens to paint over the window in time; often it doesn't, and the orb
    sits on a grey square. A black background under DWM "glass" (the frame extended over
    the whole window) is drawn as clear by Windows, whatever WebView2 does, and unlike a
    colour key it still takes the clicks.
    """
    from System.Drawing import Color  # pythonnet, as pywebview uses; UI thread only

    window.native.BackColor = Color.Black
    set_tool_style(window.native.Handle.ToInt32())


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


def set_tool_style(hwnd: int):
    """No taskbar button, not in Alt+Tab, and glass behind the page (see as_tool_window)."""
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, win32con.GWL_EXSTYLE)
    wanted = (style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
    if wanted != style:
        user32.SetWindowLongW(hwnd, win32con.GWL_EXSTYLE, wanted)
    ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_Margins(-1, -1, -1, -1)))


def reading_seconds(text: str) -> float:
    """How long to leave a reply up: long enough to read it."""
    return min(30.0, 5.0 + len(text) / 8)


class Floating:
    ORB_TITLE, BUBBLE_TITLE = "图灵浮窗", "图灵气泡"

    def __init__(self, engine):
        self.engine = engine
        self.main = self.orb = self.bubble = None
        self.main_visible = True
        self._quitting = False
        self._hover = False
        self._you = ""
        self._bubble_shown = False
        self._hide_timer: threading.Timer | None = None
        engine.watchers.append(self._on_event)

    # --- windows ---------------------------------------------------------------

    def create(self, webview, web_dir, api, main):
        self.main = main
        saved = config.load().get("orb", {})
        x, y = saved.get("x"), saved.get("y")
        if x is None or y is None:
            x, y = default_position()
        common = dict(js_api=api, frameless=True, transparent=True, on_top=True, focus=False,
                      resizable=False, shadow=False)
        # min_size too: pywebview's default minimum (200x100) would widen the orb.
        self.orb = webview.create_window(self.ORB_TITLE, url=(web_dir / "orb.html").as_uri(),
                                         width=ORB, height=ORB, min_size=(ORB, ORB),
                                         x=int(x), y=int(y), easy_drag=True, **common)
        self.bubble = webview.create_window(self.BUBBLE_TITLE, url=(web_dir / "bubble.html").as_uri(),
                                            width=BUBBLE_W, height=BUBBLE_H,
                                            min_size=(BUBBLE_W, BUBBLE_H), hidden=True, **common)
        self.orb.events.before_show += as_tool_window
        self.bubble.events.before_show += as_tool_window
        main.events.closing += self._on_main_closing

    def started(self):
        """Put the bubble away once it has loaded: transparent windows ignore `hidden`
        and show themselves when their page loads. (An invisible window would still
        catch clicks meant for whatever is under it.)"""
        self.bubble.events.loaded.wait(15)
        if not self._bubble_shown:
            self.bubble.hide()
        # The main page polls for news only while it can be seen.
        if not self.main_visible and self.main.events.loaded.wait(15):
            self.main.evaluate_js("setVisible(false)")

    # --- main window -------------------------------------------------------------

    def _on_main_closing(self):
        if self._quitting:
            return True
        if not config.load().get("app", {}).get("close_to_orb", True):
            # The user chose "closing the window quits Turing".
            threading.Thread(target=self.quit, daemon=True).start()
            return False
        # Closing the main window just tucks it away; Turing keeps listening in the orb.
        self._set_main_visible(False)
        return False

    def apply_language(self):
        """The language setting changed: tell the orb and bubble (in the background, since
        evaluate_js waits for the window thread)."""
        lang = config.ui_language()

        def tell():
            for window in (self.orb, self.bubble):
                try:
                    window.evaluate_js(f"setLang('{lang}')")
                except Exception:
                    pass

        threading.Thread(target=tell, daemon=True).start()

    def _set_main_visible(self, visible: bool):
        """Show or hide the main window, and tell its page so it only polls while seen."""
        if visible:
            self.main.show()
            self.main.restore()
        else:
            self.main.hide()
        self.main_visible = visible
        # Don't wait for the page: closing the main window runs this on the window
        # thread, and evaluate_js waits for that very thread (Turing would hang).
        threading.Thread(target=self._tell_page, args=(visible,), daemon=True).start()

    def _tell_page(self, visible: bool):
        try:
            self.main.evaluate_js(f"setVisible({str(visible).lower()})")
        except Exception:
            pass

    def open_main(self, page: str | None = None):
        self._set_main_visible(True)
        if page:
            self.main.evaluate_js(f"show('{page}')")

    def toggle_main(self):
        if self.main_visible:
            self._set_main_visible(False)
        else:
            self.open_main()

    def quit(self):
        self._quitting = True
        if self._hide_timer:
            self._hide_timer.cancel()  # it would touch the bubble after it's gone
        self.engine.stop()
        for window in (self.bubble, self.orb, self.main):
            try:
                window.destroy()
            except Exception:
                pass

    # --- orb --------------------------------------------------------------------

    def save_position(self):
        """The orb was dragged: remember where, and keep the bubble beside it."""
        config.save_section("orb", {"x": int(self.orb.x), "y": int(self.orb.y)})
        if self._bubble_shown:
            self._place_bubble()

    def show_menu(self):
        self._show({"menu": {"running": self.engine.state != "stopped"}}, seconds=8)

    # --- bubble -----------------------------------------------------------------

    def _place_bubble(self) -> str:
        """Put the bubble beside the orb, on whichever side has room. Returns the side."""
        ox, oy = int(self.orb.x), int(self.orb.y)
        side = "left" if ox >= BUBBLE_W else "right"
        x = ox - BUBBLE_W + 18 if side == "left" else ox + ORB - 18
        y = max(0, oy + ORB // 2 + 30 - BUBBLE_H)
        self.bubble.move(x, y)
        return side

    def _show(self, view: dict, seconds: float):
        if self._quitting:
            return
        view["side"] = self._place_bubble()
        self.bubble.evaluate_js(f"render({_json(view)})")
        # pywebview rebuilds hidden windows, which drops the style set before the first
        # show; set it again while hidden so no taskbar button ever appears.
        hwnd = ctypes.windll.user32.FindWindowW(None, self.BUBBLE_TITLE)
        if hwnd:
            set_tool_style(hwnd)
        self.bubble.show()
        self._bubble_shown = True
        self._schedule_hide(seconds)

    def _schedule_hide(self, seconds: float):
        if self._hide_timer:
            self._hide_timer.cancel()
        self._hide_timer = threading.Timer(seconds, self._auto_hide)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def _auto_hide(self):
        if self._quitting:
            return
        if self._hover or self.engine.state == "listening":
            self._schedule_hide(2.0)  # still being read, or the user is still talking
        else:
            self.close_bubble()

    def close_bubble(self):
        if self._hide_timer:
            self._hide_timer.cancel()
        self.bubble.hide()
        self._bubble_shown = False

    def hover(self, inside: bool):
        self._hover = bool(inside)

    def _on_event(self, kind: str, text: str):
        if self._quitting or self.bubble is None:
            return
        if kind == "open_page":
            threading.Thread(target=self.open_main, args=(text,), daemon=True).start()
            return
        if kind == "state" and text == "listening" and not self._you:
            self._show({"status": "在听…", "live": True}, seconds=8)
        elif kind == "you":
            self._you = _strip(text)
            self._show({"you": self._you, "status": "想一想…"}, seconds=20)
        elif kind in ("turing", "error"):
            reply = _strip(text)
            self._show({"you": self._you, "reply": reply}, seconds=reading_seconds(reply))
        elif kind == "state" and text == "waiting":
            self._you = ""


def _strip(text: str) -> str:
    for prefix in ("你 / You: ", "图灵 / Turing: "):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _json(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
