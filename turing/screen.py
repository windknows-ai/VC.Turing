"""Screenshots of what the user is looking at, sized for an AI to read."""

import ctypes
import io

import win32api
import win32con
import win32gui
from PIL import Image, ImageGrab

# Long edge in pixels. Vision models downscale anything bigger anyway, and text on a
# typical screen stays legible at this size.
MAX_SIDE = 1568


def _dpi_aware():
    # Without this, window and monitor coordinates are scaled and the grab is cropped.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def active_monitor() -> tuple[int, int, int, int]:
    """Bounds of the monitor showing the window the user is working in."""
    _dpi_aware()
    hwnd = win32gui.GetForegroundWindow()
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(monitor)["Monitor"]


def active_window_title() -> str:
    return win32gui.GetWindowText(win32gui.GetForegroundWindow())


def shrink(img: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    scale = max_side / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img


def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=88)
    return buf.getvalue()


def capture() -> tuple[bytes, str]:
    """(JPEG bytes, active window title) for the screen the user is looking at."""
    img = ImageGrab.grab(bbox=active_monitor(), all_screens=True)
    return to_jpeg(shrink(img)), active_window_title()
