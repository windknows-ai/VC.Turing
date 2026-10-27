"""Type text and press keys in other apps, and bring their windows to the front."""

import ctypes
import os
import time

import psutil
import win32clipboard
import win32con
import win32gui
import win32process

_user32 = ctypes.windll.user32
KEYUP = 0x0002

KEYS = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "plus": 0xBB, "equals": 0xBB, "minus": 0xBD,  # zoom in/out: Ctrl + / Ctrl -
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def _vk(name: str) -> int:
    name = name.strip().lower()
    if name in KEYS:
        return KEYS[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    raise ValueError(f"unknown key: {name}")


def press(combo: str):
    """Press a key or combination such as "enter", "ctrl+f" or "ctrl+shift+t"."""
    codes = [_vk(k) for k in combo.split("+")]
    for code in codes:
        _user32.keybd_event(code, 0, 0, 0)
    for code in reversed(codes):
        _user32.keybd_event(code, 0, KEYUP, 0)
    time.sleep(0.05)


def _get_clipboard() -> str | None:
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def _set_clipboard(text: str):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):  # only here so the union has Windows' size
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


_UNICODE, _INPUT_KEYBOARD = 0x0004, 1


def type_text(text: str):
    """Type into the focused field as Unicode keystrokes (Chinese and emoji included).

    No clipboard: pasting would replace whatever the user had copied (images and files
    couldn't be put back) and makes clipboard-watching apps like WeChat react. A line
    break is typed as Shift+Enter, so a chat app doesn't send half a message.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if i:
            press("shift+enter")
        units = line.encode("utf-16-le")
        codes = [int.from_bytes(units[j:j + 2], "little") for j in range(0, len(units), 2)]
        events = []
        for code in codes:  # emoji are two UTF-16 units; each is sent as it is
            for flags in (_UNICODE, _UNICODE | KEYUP):
                ev = _INPUT(type=_INPUT_KEYBOARD)
                ev.ki = _KEYBDINPUT(0, code, flags, 0, 0)
                events.append(ev)
        for start in range(0, len(events), 200):  # in batches, so slow apps keep up
            batch = events[start:start + 200]
            _user32.SendInput(len(batch), (_INPUT * len(batch))(*batch), ctypes.sizeof(_INPUT))
            time.sleep(0.02)
    time.sleep(0.05)


_NOT_MAIN = {"IME", "MSCTFIME UI"}


def window_title(hwnd: int) -> str:
    """A window's title without sending it a message (unlike GetWindowText), so a hung
    app, or one of our own windows busy on the UI thread, can't block us."""
    buf = ctypes.create_unicode_buffer(512)
    _user32.InternalGetWindowText(hwnd, buf, 512)
    return buf.value


def _app_windows(match_process) -> list[tuple[bool, int, int]]:
    """(visible, area, hwnd) for top-level windows with a title whose process matches.
    Turing's own windows are never included."""
    found = []
    own_pid = os.getpid()

    def check(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == own_pid:
            return
        if not window_title(hwnd) or win32gui.GetClassName(hwnd) in _NOT_MAIN:
            return
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return
        try:
            if not match_process(psutil.Process(pid)):
                return
        except psutil.Error:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        found.append((bool(win32gui.IsWindowVisible(hwnd)), (right - left) * (bottom - top), hwnd))

    win32gui.EnumWindows(check, None)
    return found


def find_window(process_names: tuple[str, ...], title: str | None = None) -> int | None:
    """Main window of one of these processes, even if it's hidden in the tray.

    Visible windows are preferred; a hidden one is only taken if `title` matches, so we
    never pop up some random internal window of the app.
    """
    names = {n.lower() for n in process_names}
    windows = _app_windows(lambda p: p.name().lower() in names)
    visible = [w for w in windows if w[0] and (title is None or window_title(w[2]) == title)]
    if visible:
        return max(visible, key=lambda w: w[1])[2]
    hidden = [w for w in windows if title is not None and window_title(w[2]) == title]
    return max(hidden, key=lambda w: w[1])[2] if hidden else None


_SHARED_DIRS = {"windows", "system32", "syswow64", "program files", "program files (x86)",
                "programdata", "appdata", "local", "roaming", "programs", "users"}


def same_program(exe_path: str):
    """A matcher for processes of the program installed at `exe_path`.

    Many apps (鎶栭煶, 寰俊) are started by a small launcher, and their windows belong to
    another .exe in a versioned subfolder, so anything under the app's own install
    folder counts. Never for shared folders like System32, which hold unrelated programs.
    """
    target = os.path.normcase(exe_path)
    folder = os.path.dirname(target)
    parts = [p for p in folder.split(os.sep)[1:] if p]
    own_folder = len(parts) >= 2 and parts[-1] not in _SHARED_DIRS

    def match(p) -> bool:
        try:
            exe = os.path.normcase(p.exe())
        except psutil.Error:
            return False
        return exe == target or (own_folder and exe.startswith(folder + os.sep))

    return match


def window_of_exe(exe_path: str, title: str | None = None) -> int | None:
    """Main window of a running program, by its .exe path; None if it isn't running."""
    windows = _app_windows(same_program(exe_path))
    visible = [w for w in windows if w[0]]
    if visible:
        return max(visible, key=lambda w: w[1])[2]
    hidden = [w for w in windows if title and window_title(w[2]) == title]
    return max(hidden, key=lambda w: w[1])[2] if hidden else None


def windows_of_exe(exe_path: str) -> list[int]:
    """All visible titled windows of a running program."""
    return [hwnd for visible, _, hwnd in _app_windows(same_program(exe_path)) if visible]


def windows_titled(title: str) -> list[int]:
    """Visible windows titled exactly `title` (case-insensitive). Exact on purpose: a
    browser tab called "寰俊鍏紬骞冲彴" must not count as WeChat."""
    title = title.strip().lower()
    return [hwnd for visible, _, hwnd in _app_windows(lambda p: True)
            if visible and window_title(hwnd).strip().lower() == title]


def close(hwnd: int):
    """Ask a window to close, as its 脳 button does (it may ask to save first)."""
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def focus(hwnd: int) -> bool:
    """Bring a visible window to the front and give it the keyboard.

    A window hidden in the tray is never shown from outside: WeChat (and other Qt apps)
    then show a window they still think is hidden, which draws but ignores every click.
    Such apps must show themselves (see apps.show_from_tray). A minimized window is asked
    to restore itself, as clicking its taskbar button does.
    """
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if win32gui.IsIconic(hwnd):
        _user32.PostMessageW(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
        end = time.monotonic() + 1.5
        while win32gui.IsIconic(hwnd) and time.monotonic() < end:
            time.sleep(0.05)
    # Windows only lets the app in front hand over focus. Joining our input to the front
    # window's thread for a moment counts as being it. (Not a tap of Alt, the usual trick:
    # releasing Alt puts the new window in menu mode, so the next keys went to its menu,
    # the first typed character was lost, and WeChat seemed not to take any input.)
    front = _user32.GetForegroundWindow()
    ours = ctypes.windll.kernel32.GetCurrentThreadId()
    theirs = _user32.GetWindowThreadProcessId(front, None) if front else 0
    joined = bool(theirs and theirs != ours and _user32.AttachThreadInput(ours, theirs, True))
    try:
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
    finally:
        if joined:
            _user32.AttachThreadInput(ours, theirs, False)
    time.sleep(0.3)
    return win32gui.GetForegroundWindow() == hwnd
