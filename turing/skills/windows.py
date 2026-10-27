"""Windows and browser tabs: minimize, maximize, restore, snap left/right, show the
desktop, switch to an app's window; new / close / refresh tabs in the browser.

Every action works on a real window found first, and is checked afterwards (is it
minimized? where is it? is it in front?), so the reply says what really happened.
"""

import ctypes
import os
import re
import time

import psutil
import win32api
import win32con
import win32gui
import win32process

from .. import keyboard
from . import Context, Fallback, Skill, Tool, schema

_user32 = ctypes.windll.user32
_SHELL = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"}
BROWSERS = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
            "brave.exe": "Brave", "opera.exe": "Opera"}
# What people call an app -> its process (for windows whose title doesn't say).
PROCESS_NAMES = {"chrome": "chrome.exe", "谷歌浏览器": "chrome.exe", "谷歌": "chrome.exe",
                 "edge": "msedge.exe", "火狐": "firefox.exe", "firefox": "firefox.exe",
                 "微信": "weixin.exe", "wechat": "weixin.exe", "qq": "qq.exe", "记事本": "notepad.exe",
                 "notepad": "notepad.exe", "文件管理器": "explorer.exe", "资源管理器": "explorer.exe",
                 "file explorer": "explorer.exe", "vscode": "code.exe", "vs code": "code.exe",
                 "word": "winword.exe", "excel": "excel.exe", "ppt": "powerpnt.exe",
                 "powerpoint": "powerpnt.exe", "抖音": "douyin.exe", "discord": "discord.exe",
                 "steam": "steam.exe", "spotify": "spotify.exe", "qq音乐": "qqmusic.exe",
                 "网易云音乐": "cloudmusic.exe", "网易云": "cloudmusic.exe", "终端": "windowsterminal.exe"}


# --- finding windows --------------------------------------------------------------

def _cloaked(hwnd: int) -> bool:
    """Windows on another virtual desktop (and some hidden UWP frames) are 'cloaked'."""
    value = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(value), ctypes.sizeof(value))
    return bool(value.value)


def _is_app_window(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd) or _cloaked(hwnd):
        return False
    if win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid():
        return False  # Turing's own windows
    if not keyboard.window_title(hwnd) or win32gui.GetClassName(hwnd) in _SHELL:
        return False
    ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    return not ex & win32con.WS_EX_TOOLWINDOW and win32gui.GetWindow(hwnd, win32con.GW_OWNER) == 0


def app_windows() -> list[int]:
    """The user's app windows on this desktop, front to back."""
    found = []
    hwnd = win32gui.GetTopWindow(0)
    while hwnd:
        if _is_app_window(hwnd):
            found.append(hwnd)
        hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
    return found


def process_name(hwnd: int) -> str:
    try:
        return psutil.Process(win32process.GetWindowThreadProcessId(hwnd)[1]).name().lower()
    except psutil.Error:
        return ""


def current_window() -> int | None:
    """The window the user means by "this window": the front one, or, when Turing's own
    window is in front (they typed into it), the one right behind it."""
    windows = app_windows()
    front = win32gui.GetForegroundWindow()
    if front in windows:
        return front
    return windows[0] if windows else None


_THIS = re.compile(r"^(?:当前|这个|这|此|目前的?|现在的?)?(?:窗口|页面|程序|软件|应用)?$|^(?:the |this |current )?(?:window|app)?$", re.I)


def find(name: str) -> int | None:
    """The front-most window of the app the user named ('' or 这个窗口 = current)."""
    name = name.strip().lower()
    if _THIS.match(name):
        return current_window()
    exe = PROCESS_NAMES.get(name, name if name.endswith(".exe") else name + ".exe")
    windows = app_windows()
    for hwnd in windows:
        if process_name(hwnd) == exe:
            return hwnd
    for hwnd in windows:
        if name in keyboard.window_title(hwnd).lower():
            return hwnd
    return None


def label(hwnd: int) -> str:
    exe = process_name(hwnd)
    if exe in BROWSERS:
        return BROWSERS[exe]
    title = keyboard.window_title(hwnd)
    return title.rsplit(" - ", 1)[-1] if " - " in title else title


# --- acting on them (each checked) --------------------------------------------------

def _wait(check, timeout: float = 1.5) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.1)
    return check()


def minimize(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    return _wait(lambda: win32gui.IsIconic(hwnd))


def maximize(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    return _wait(lambda: _user32.IsZoomed(hwnd))


def restore(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    return _wait(lambda: not win32gui.IsIconic(hwnd) and not _user32.IsZoomed(hwnd))


def snap(hwnd: int, side: str) -> bool:
    """Put the window on the left or right half of its screen."""
    if win32gui.IsIconic(hwnd) or _user32.IsZoomed(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    half = (right - left) // 2
    x = left if side == "left" else left + half
    win32gui.SetWindowPos(hwnd, 0, x, top, half, bottom - top,
                          win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)

    def placed():
        l, _, r, _ = win32gui.GetWindowRect(hwnd)
        return abs((l + r) // 2 - (x + half // 2)) < half // 4
    return _wait(placed)


def close(hwnd: int) -> bool:
    """Ask it to close like its × does; True once it's gone (False: still there, e.g. asking to save)."""
    keyboard.close(hwnd)
    return _wait(lambda: not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd), 2.0)


def show_desktop() -> bool:
    import win32com.client

    win32com.client.Dispatch("Shell.Application").MinimizeAll()
    return _wait(lambda: not [h for h in app_windows() if not win32gui.IsIconic(h)], 2.0)


def bring_back_all() -> bool:
    import win32com.client

    win32com.client.Dispatch("Shell.Application").UndoMinimizeALL()
    return _wait(lambda: bool([h for h in app_windows() if not win32gui.IsIconic(h)]), 2.0)


def focus(hwnd: int) -> bool:
    return keyboard.focus(hwnd)


# --- browser tabs -------------------------------------------------------------------

TAB_KEYS = {"new": "ctrl+t", "close": "ctrl+w", "refresh": "f5", "back": "alt+left",
            "forward": "alt+right", "reopen": "ctrl+shift+t"}


def browser_window() -> int | None:
    """The browser window the user was last in."""
    return next((h for h in app_windows() if process_name(h) in BROWSERS), None)


def tab(action: str) -> tuple[bool, str]:
    """(done, browser name). Keys go only to a browser window that is really in front."""
    hwnd = browser_window()
    if hwnd is None:
        return False, ""
    name = BROWSERS[process_name(hwnd)]
    if win32gui.GetForegroundWindow() != hwnd and not keyboard.focus(hwnd):
        return False, name
    before = keyboard.window_title(hwnd)
    keyboard.press(TAB_KEYS[action])
    if action == "new":  # a new tab shows up as the window's title
        return _wait(lambda: keyboard.window_title(hwnd) != before or not win32gui.IsWindow(hwnd)), name
    return True, name


# --- the skill ----------------------------------------------------------------------

_NAME = r"(?:把|将|帮我把)?\s*(.*?)\s*(?:的)?(?:窗口)?\s*"
_MIN = re.compile(rf"^{_NAME}(?:最小化|缩到任务栏|收起来)$|^最小化\s*(.*?)(?:窗口)?$|^minimi[sz]e\s*(.*?)(?:\s*window)?$", re.I)
_MAX = re.compile(rf"^{_NAME}(?:最大化|放大|铺满屏幕)$|^最大化\s*(.*?)(?:窗口)?$|^maximi[sz]e\s*(.*?)(?:\s*window)?$", re.I)
_RESTORE = re.compile(rf"^{_NAME}(?:还原|恢复原来大小)$|^还原\s*(.*?)(?:窗口)?$|^restore\s*(.*?)(?:\s*window)?$", re.I)
_CLOSE = re.compile(r"^(?:关闭|关掉|关上)(?:当前|这个|这)(?:窗口|页面|程序|软件)$|^close (?:this|the current) window$", re.I)
_SNAP = re.compile(rf"^{_NAME}(?:放|移|挪|贴)到?(?:屏幕)?(左|右)(?:边|侧|半边|半屏)?$"
                   r"|^(?:snap|move|put)\s*(.*?)\s*(?:window\s*)?to\s*the\s*(left|right)(?:\s*half)?$", re.I)
_DESKTOP = re.compile(r"^(?:显示桌面|回到桌面|最小化所有窗口|把(?:所有|全部)?窗口都?最小化|全部最小化|"
                      r"minimi[sz]e (?:all|everything)(?: windows)?|show (?:the )?desktop)$", re.I)
_UNDESKTOP = re.compile(r"^(?:恢复所有窗口|把窗口都?恢复|还原所有窗口|restore all windows)$", re.I)
_SWITCH = re.compile(r"^(?:切换到|切到|转到|回到|跳到)\s*(.+?)\s*(?:窗口)?$|^switch to\s+(.+?)(?:\s+window)?$", re.I)
_TABS = [
    ("new", re.compile(r"^(?:在浏览器里)?(?:新建|新开|打开|开)(?:一个)?(?:新的?)?(?:标签页?|网页标签|tab)$|^(?:open )?(?:a )?new tab$", re.I)),
    ("close", re.compile(r"^(?:关掉|关闭|关上)(?:这个|当前)?(?:标签页?|网页|tab)$|^close (?:this |the )?tab$", re.I)),
    ("refresh", re.compile(r"^刷新(?:一下)?(?:页面|网页|浏览器)?$|^(?:refresh|reload)(?: the)?(?: page)?$", re.I)),
    ("back", re.compile(r"^(?:网页)?(?:后退|返回上一页|回到上一页)$|^go back(?: a page)?$", re.I)),
    ("forward", re.compile(r"^(?:网页)?前进(?:一页)?$|^go forward$", re.I)),
    ("reopen", re.compile(r"^(?:恢复|重新打开)(?:刚才)?关(?:掉|闭)的标签页?$|^reopen (?:the )?closed tab$", re.I)),
]

_DONE = {"minimize": ("已把{}最小化", "Minimized {}"), "maximize": ("已把{}最大化", "Maximized {}"),
         "restore": ("已还原{}", "Restored {}"), "snap_left": ("已把{}放到屏幕左半边", "Put {} on the left half"),
         "snap_right": ("已把{}放到屏幕右半边", "Put {} on the right half"), "focus": ("已切换到{}", "Switched to {}")}
_ACTIONS = {"minimize": minimize, "maximize": maximize, "restore": restore, "focus": focus,
            "snap_left": lambda h: snap(h, "left"), "snap_right": lambda h: snap(h, "right")}
_TAB_DONE = {"new": ("已在{}里新建标签页", "Opened a new tab in {}"), "close": ("已关闭{}当前的标签页", "Closed the tab in {}"),
             "refresh": ("已刷新{}里的页面", "Refreshed the page in {}"), "back": ("{}已后退一页", "Went back in {}"),
             "forward": ("{}已前进一页", "Went forward in {}"), "reopen": ("已在{}里恢复刚关的标签页", "Reopened the tab in {}")}


class Windows(Skill):
    name = "windows"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _DESKTOP.match(text):
            return self.desktop(ctx)
        if _UNDESKTOP.match(text):
            return ctx.reply("已恢复所有窗口", "Restored all windows") if bring_back_all() \
                else ctx.reply("没能恢复窗口。", "Couldn't bring the windows back.")
        for action, pattern in _TABS:
            if pattern.match(text):
                return self.tab(action, ctx)
        if _CLOSE.match(text):
            return self.close_current(ctx)
        for action, pattern in (("minimize", _MIN), ("maximize", _MAX), ("restore", _RESTORE)):
            if m := pattern.match(text):
                return self.act(action, next((g for g in m.groups() if g is not None), ""), ctx)
        if m := _SNAP.match(text):
            groups = [g for g in m.groups() if g is not None]
            side = "left" if groups[-1] in ("左", "left") else "right"
            return self.act(f"snap_{side}", groups[0] if len(groups) > 1 else "", ctx)
        if (m := _SWITCH.match(text)) and not text.endswith("桌面") and "desktop" not in text:
            name = next(g for g in m.groups() if g)
            if find(name) is None:
                return None  # not open: the AI can open it instead
            return self.act("focus", name, ctx)
        return None

    def act(self, action: str, name: str, ctx: Context) -> str:
        hwnd = find(name)
        if hwnd is None:
            what = name or ctx.reply("窗口", "window")
            return Fallback(ctx.reply(f"没找到打开着的{what}。", f"I can't find an open {what} window."))
        who = label(hwnd)
        if _ACTIONS[action](hwnd):
            zh, en = _DONE[action]
            return ctx.reply(zh.format(who), en.format(who))
        return ctx.reply(f"没能对{who}完成这个操作。", f"That didn't work on {who}.")

    def close_current(self, ctx: Context) -> str:
        hwnd = current_window()
        if hwnd is None:
            return ctx.reply("没有可以关闭的窗口。", "There's no window to close.")
        who = label(hwnd)
        if close(hwnd):
            return ctx.reply(f"已关闭{who}", f"Closed {who}")
        return ctx.reply(f"{who}还开着，可能在问你要不要保存。", f"{who} is still open; it may be asking you to save.")

    def desktop(self, ctx: Context) -> str:
        if show_desktop():
            return ctx.reply("已最小化所有窗口，显示桌面", "Minimized everything; here's the desktop")
        return ctx.reply("有的窗口没能最小化。", "Some windows didn't minimize.")

    def tab(self, action: str, ctx: Context) -> str:
        done, browser = tab(action)
        if not browser:
            return ctx.reply("没有找到打开着的浏览器窗口。", "There's no browser window open.")
        if not done:
            return ctx.reply(f"没能切到{browser}窗口，操作没有完成。", f"Couldn't bring {browser} to the front, so nothing was done.")
        zh, en = _TAB_DONE[action]
        return ctx.reply(zh.format(browser), en.format(browser))

    def tools(self) -> list[Tool]:
        return [
            Tool("window",
                 "Act on an app's window and check it worked: minimize, maximize, restore, "
                 "snap_left, snap_right (half the screen), focus (bring to front). `app` is the "
                 "app the user named, or empty for the current window.",
                 schema({"action": {"type": "string", "enum": list(_ACTIONS)}, "app": {"type": "string"}},
                        ["action"]),
                 lambda args, ctx: self.act(args["action"], args.get("app") or "", ctx)),
            Tool("show_desktop", "Minimize all windows to show the desktop.", schema(),
                 lambda args, ctx: self.desktop(ctx)),
            Tool("browser_tab",
                 "In the browser the user is using: new tab, close the current tab, refresh, "
                 "back, forward, or reopen the last closed tab.",
                 schema({"action": {"type": "string", "enum": list(TAB_KEYS)}}, ["action"]),
                 lambda args, ctx: self.tab(args["action"], ctx)),
        ]
