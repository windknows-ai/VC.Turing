"""The PC itself: screen brightness, dark mode, battery, screenshots, sleep / shutdown /
restart, the recycle bin, the clipboard, and Settings pages for what can't be switched
directly (Bluetooth, Wi-Fi, Do Not Disturb).

Each change is read back before Turing says it's done. Anything hard to undo asks first.
"""

import ctypes
import datetime
import os
import re
import subprocess
import threading
import winreg

import psutil

from .. import keyboard
from ..numbers import parse_number
from . import Context, Skill, Tool, schema

_NO_WINDOW = subprocess.CREATE_NO_WINDOW


# --- brightness (built-in screens) -------------------------------------------------

def _powershell(command: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True,
                          text=True, timeout=15, creationflags=_NO_WINDOW).stdout.strip()


def get_brightness() -> int | None:
    out = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
                      "-ErrorAction SilentlyContinue | Select-Object -First 1).CurrentBrightness")
    return int(out) if out.isdigit() else None


def set_brightness(percent: int) -> int | None:
    """Set it and return what the screen reports afterwards (None: not adjustable)."""
    percent = max(0, min(100, percent))
    _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
                f"-ErrorAction SilentlyContinue | Invoke-CimMethod -MethodName WmiSetBrightness "
                f"-Arguments @{{Timeout=0; Brightness={percent}}} | Out-Null")
    return get_brightness()


# --- dark mode ----------------------------------------------------------------------

_THEME = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def dark_mode() -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME) as k:
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0


def set_dark_mode(dark: bool) -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME, 0, winreg.KEY_SET_VALUE) as k:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 0 if dark else 1)
    # Tell open apps the theme changed (WM_SETTINGCHANGE "ImmersiveColorSet").
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 2, 1000, None)
    return dark_mode() == dark


# --- screenshots --------------------------------------------------------------------

def pictures_folder() -> str:
    key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return os.path.expandvars(winreg.QueryValueEx(k, "My Pictures")[0])
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Pictures")


def screenshot() -> str | None:
    """Save the whole screen as a PNG in Pictures\\Screenshots; the path if it was saved."""
    from PIL import ImageGrab

    folder = os.path.join(pictures_folder(), "Screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, datetime.datetime.now().strftime("图灵截图 %Y-%m-%d %H%M%S.png"))
    ImageGrab.grab(all_screens=True).save(path)
    return path if os.path.getsize(path) > 0 else None


# --- power ----------------------------------------------------------------------------

def sleep_pc():
    ctypes.windll.powrprof.SetSuspendState(False, True, False)


def shutdown(restart: bool, seconds: int = 30):
    subprocess.Popen(["shutdown", "/r" if restart else "/s", "/t", str(seconds)], creationflags=_NO_WINDOW)


def cancel_shutdown() -> bool:
    return subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=_NO_WINDOW).returncode == 0


def empty_recycle_bin():
    """Shows Windows' own "are you sure" box; nothing is deleted unless the user agrees."""
    threading.Thread(target=lambda: ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0),
                     daemon=True).start()


def open_settings(page: str):
    os.startfile(f"ms-settings:{page}")


# --- the skill ----------------------------------------------------------------------

_BRIGHT_SET = re.compile(r"^(?:把)?(?:屏幕)?亮度(?:调|设|设置)?(?:到|成|为)\s*(.+?)%?$|^set (?:the )?brightness to (\d+)%?$", re.I)
_BRIGHT_UP = re.compile(r"^(?:把)?(?:屏幕)?(?:调亮|亮)(?:一)?点|^(?:把)?(?:屏幕)?亮度(?:调)?(?:高|大)(?:一)?点|^(?:把)?(?:屏幕)?亮度调(?:高|大)(?:一些)?$|^(?:调高|提高|增加|加大|调大)(?:一下)?(?:屏幕)?亮度|^屏幕(?:调)?亮(?:一)?点|^brighter$|^(?:turn )?(?:the )?brightness up|increase (?:the )?brightness", re.I)
_BRIGHT_DOWN = re.compile(r"^(?:把)?(?:屏幕)?(?:调暗|暗)(?:一)?点|^(?:把)?(?:屏幕)?亮度(?:调)?(?:低|小)(?:一)?点|^(?:把)?(?:屏幕)?亮度调(?:低|小)(?:一些)?$|^(?:调低|降低|减小|减少|调小)(?:一下)?(?:屏幕)?亮度|^屏幕(?:调)?暗(?:一)?点|^dimmer$|^(?:turn )?(?:the )?brightness down|decrease (?:the )?brightness", re.I)
_BRIGHT_QUERY = re.compile(r"^(?:现在)?(?:屏幕)?亮度(?:是)?多少|^what(?:'s| is) the brightness", re.I)
_DARK = re.compile(r"^(?:打开|开启|切换到|换成|用)?(?:深色|暗色|黑色|夜间)(?:模式|主题)$|^(?:turn on |switch to )?dark mode$", re.I)
_LIGHT = re.compile(r"^(?:打开|开启|切换到|换成|用)?(?:浅色|亮色|白色|日间)(?:模式|主题)$|^关闭(?:深色|暗色|夜间)(?:模式|主题)$|^(?:turn on |switch to )?light mode$|^turn off dark mode$", re.I)
_BATTERY = re.compile(r"电池|电量|battery", re.I)
_SCREENSHOT = re.compile(r"^(?:帮我)?(?:截个?图|截屏|截一?张图|屏幕截图|把屏幕截下来)$|^take (?:a )?screenshot$|^screenshot$", re.I)
_SLEEP = re.compile(r"^(?:让)?(?:电脑)?(?:睡眠|休眠|待机|睡觉)$|^让电脑(?:睡眠|休眠|睡觉)$|^(?:put the (?:pc|computer) to )?sleep$", re.I)
_SHUTDOWN = re.compile(r"^(?:帮我)?(?:把电脑)?关机$|^关(?:掉|闭)电脑$|^shut ?down(?: the (?:pc|computer))?$", re.I)
_RESTART = re.compile(r"^(?:帮我)?(?:把电脑)?(?:重启|重新启动)(?:电脑|一下电脑)?$|^restart(?: the (?:pc|computer))?$", re.I)
_CANCEL_SHUTDOWN = re.compile(r"^取消(?:关机|重启)$|^(?:不要|别)(?:关机|重启)了?$|^cancel (?:the )?(?:shutdown|restart)$", re.I)
_RECYCLE = re.compile(r"^清空回收站$|^empty (?:the )?recycle bin$", re.I)
_CLIPBOARD = re.compile(r"剪贴板|剪切板|clipboard", re.I)
_PAGES = [
    (re.compile(r"蓝牙|bluetooth", re.I), "bluetooth", ("蓝牙", "Bluetooth")),
    (re.compile(r"wi-?fi|无线网|无线网络|网络连接", re.I), "network-wifi", ("Wi-Fi", "Wi-Fi")),
    (re.compile(r"勿扰|免打扰|专注|do not disturb|focus", re.I), "notifications", ("勿扰模式", "Do Not Disturb")),
    (re.compile(r"夜间模式|护眼|夜灯|night light", re.I), "nightlight", ("夜间模式", "night light")),
    (re.compile(r"省电|节电|节能|battery saver|energy saver", re.I), "batterysaver", ("省电模式", "battery saver")),
]
# Turing can't pair or connect a device itself; it opens the page where one click does.
_CONNECT = re.compile(r"^(?:帮我)?(?:连上|连接|连一下|配对)(?:一下)?(?:我的)?(?:蓝牙|耳机|音箱|音响|鼠标|键盘|手柄)"
                      r"|^(?:pair|connect)(?: my| the)? (?:bluetooth|headphones|earbuds|airpods|speaker)", re.I)
_SWITCHY = re.compile(r"^(?:打开|开启|关闭|关掉|关上|开|关|turn (?:on|off)|enable|disable)", re.I)


class Device(Skill):
    name = "device"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _SCREENSHOT.match(text):
            return self.take_screenshot(ctx)
        if _CANCEL_SHUTDOWN.match(text):
            return self.power("cancel", ctx)
        if _SHUTDOWN.match(text):
            return self.power("shutdown", ctx)
        if _RESTART.match(text):
            return self.power("restart", ctx)
        if _SLEEP.match(text):
            return self.power("sleep", ctx)
        if _RECYCLE.match(text):
            return self.recycle(ctx)
        if _DARK.match(text):
            return self.theme(True, ctx)
        if _LIGHT.match(text):
            return self.theme(False, ctx)
        if m := _BRIGHT_SET.match(text):
            value = parse_number(next(g for g in m.groups() if g))
            return self.brightness(ctx, to=value) if value is not None else None
        if _BRIGHT_UP.match(text):
            return self.brightness(ctx, by=20)
        if _BRIGHT_DOWN.match(text):
            return self.brightness(ctx, by=-20)
        if _BRIGHT_QUERY.match(text):
            return self.brightness(ctx)
        if _BATTERY.search(text) and len(text) <= 16:
            return self.battery(ctx)
        if _CLIPBOARD.search(text) and re.search(r"读|念|说|是什么|有什么|read|what", text, re.I):
            return self.clipboard(ctx)
        if _CONNECT.match(text):
            open_settings("bluetooth")
            return ctx.reply("我没法替你连蓝牙设备，已打开蓝牙设置，在那里点一下你的设备就能连上。",
                             "I can't connect Bluetooth devices myself, so I opened Bluetooth settings: click your device there.")
        if _SWITCHY.match(text):
            for pattern, page, names in _PAGES:
                if pattern.search(text):
                    return self.settings_page(page, names, ctx)
        return None

    def brightness(self, ctx: Context, to: int | None = None, by: int | None = None) -> str:
        now = get_brightness()
        if now is None:
            open_settings("display")
            return ctx.reply("这个屏幕不能由我调亮度（外接显示器通常不行），已打开显示设置。",
                             "I can't change this screen's brightness (external monitors usually can't be), so I opened Display settings.")
        if to is None and by is None:
            return ctx.reply(f"屏幕亮度现在是 {now}%", f"Brightness is {now}%")
        if by is not None and (now >= 100 and by > 0 or now <= 0 and by < 0):
            return ctx.reply("屏幕已经是最亮了。" if by > 0 else "屏幕已经是最暗了。",
                             "It's already at full brightness." if by > 0 else "It's already at the lowest brightness.")
        after = set_brightness(to if to is not None else now + by)
        if after is None or (to is not None and abs(after - to) > 5) or (by is not None and after == now):
            return ctx.reply(f"亮度没调成功，现在还是 {now}%。", f"That didn't change it; brightness is still {now}%.")
        return ctx.reply(f"屏幕亮度已调到 {after}%", f"Brightness is now {after}%")

    def theme(self, dark: bool, ctx: Context) -> str:
        if dark_mode() == dark:
            return ctx.reply("现在已经是深色模式了。" if dark else "现在已经是浅色模式了。",
                             "Already in dark mode." if dark else "Already in light mode.")
        if set_dark_mode(dark):
            return ctx.reply("已切换到深色模式" if dark else "已切换到浅色模式",
                             "Switched to dark mode" if dark else "Switched to light mode")
        return ctx.reply("没能切换主题。", "Couldn't change the theme.")

    def battery(self, ctx: Context) -> str:
        b = psutil.sensors_battery()
        if b is None:
            return ctx.reply("这台电脑没有电池。", "This PC has no battery.")
        plug = ctx.reply("，正在充电" if b.power_plugged else "", ", charging" if b.power_plugged else "")
        if b.power_plugged and b.percent >= 100:
            plug = ctx.reply("，已充满", ", fully charged")
        left = ""
        if not b.power_plugged and b.secsleft > 0:
            h, m = divmod(b.secsleft // 60, 60)
            left = ctx.reply(f"，大约还能用 {h} 小时 {m} 分钟", f", about {h} h {m} min left")
        return ctx.reply(f"电池还剩 {b.percent:.0f}%{plug}{left}。", f"Battery is at {b.percent:.0f}%{plug}{left}.")

    def take_screenshot(self, ctx: Context) -> str:
        path = screenshot()
        if not path:
            return ctx.reply("截图没有保存成功。", "The screenshot wasn't saved.")
        return ctx.reply("已截图，保存在“图片”里的 Screenshots 文件夹", "Screenshot saved in Pictures > Screenshots")

    def power(self, action: str, ctx: Context) -> str:
        if action == "cancel":
            return ctx.reply("已取消关机", "Shutdown cancelled") if cancel_shutdown() \
                else ctx.reply("现在没有要关机或重启。", "There's no shutdown or restart pending.")
        question = {"sleep": ("要让电脑睡眠吗？说“确定”或者“取消”。", "Put the PC to sleep? Say yes or cancel."),
                    "shutdown": ("要关机吗？说“确定”或者“取消”。", "Shut down the PC? Say yes or cancel."),
                    "restart": ("要重启电脑吗？说“确定”或者“取消”。", "Restart the PC? Say yes or cancel.")}[action]
        if not ctx.confirm(ctx.reply(*question)):
            return ctx.reply("好的，不操作了。", "OK, I'll leave it.")
        if action == "sleep":
            threading.Timer(2.0, sleep_pc).start()  # after Turing has finished speaking
            return ctx.reply("好的，电脑马上睡眠", "Going to sleep now")
        shutdown(restart=action == "restart")
        return ctx.reply("30 秒后关机，要取消就说“取消关机”。" if action == "shutdown"
                         else "30 秒后重启，要取消就说“取消关机”。",
                         "Shutting down in 30 seconds; say \"cancel shutdown\" to stop it." if action == "shutdown"
                         else "Restarting in 30 seconds; say \"cancel shutdown\" to stop it.")

    def recycle(self, ctx: Context) -> str:
        if not ctx.confirm(ctx.reply("回收站里的文件清空后就找不回来了，要清空吗？",
                                     "Files emptied from the recycle bin can't be recovered. Empty it?")):
            return ctx.reply("好的，不清空了。", "OK, I won't empty it.")
        empty_recycle_bin()
        return ctx.reply("已弹出 Windows 的确认窗口，点“是”就会清空。", "Windows is asking to confirm; click Yes to empty it.")

    def clipboard(self, ctx: Context) -> str:
        text = keyboard._get_clipboard()
        if not text or not text.strip():
            return ctx.reply("剪贴板里没有文字。", "There's no text on the clipboard.")
        return ctx.reply(f"剪贴板里是：{text.strip()[:300]}", f"The clipboard says: {text.strip()[:300]}")

    def settings_page(self, page: str, names: tuple, ctx: Context) -> str:
        open_settings(page)
        zh, en = names
        return ctx.reply(f"我没法直接开关{zh}，已打开{zh}设置，你点一下开关就行。",
                         f"I can't switch {en} myself, so I opened its Settings page for you.")

    def tools(self) -> list[Tool]:
        return [
            Tool("brightness", "Read or set the screen brightness (0-100); `change` adjusts by that many points.",
                 schema({"set": {"type": "integer"}, "change": {"type": "integer"}}),
                 lambda a, ctx: self.brightness(ctx, to=a.get("set"), by=a.get("change"))),
            Tool("dark_mode", "Switch Windows to dark (true) or light (false) mode.",
                 schema({"dark": {"type": "boolean"}}, ["dark"]), lambda a, ctx: self.theme(bool(a["dark"]), ctx)),
            Tool("battery", "Battery level and charging state.", schema(), lambda a, ctx: self.battery(ctx)),
            Tool("take_screenshot", "Save a screenshot of the whole screen as a file (not for looking at it: "
                 "that's look_at_screen).", schema(), lambda a, ctx: self.take_screenshot(ctx)),
            Tool("power", "Sleep, shut down or restart the PC (asks the user first), or cancel a pending shutdown.",
                 schema({"action": {"type": "string", "enum": ["sleep", "shutdown", "restart", "cancel"]}}, ["action"]),
                 lambda a, ctx: self.power(a["action"], ctx)),
            Tool("empty_recycle_bin", "Empty the recycle bin (asks the user, then Windows confirms).", schema(),
                 lambda a, ctx: self.recycle(ctx)),
            Tool("read_clipboard", "The text currently on the clipboard.", schema(),
                 lambda a, ctx: (keyboard._get_clipboard() or "(no text on the clipboard)")[:2000]),
            Tool("open_settings_page",
                 "Open a Windows Settings page when something can't be switched directly: "
                 "bluetooth, network-wifi, notifications (Do Not Disturb), nightlight, display, sound.",
                 schema({"page": {"type": "string"}}, ["page"]),
                 lambda a, ctx: (open_settings(a["page"].strip()), f"Opened Settings > {a['page']}. The "
                                 "switch itself was NOT changed; tell the user to flip it.")[1]),
        ]
