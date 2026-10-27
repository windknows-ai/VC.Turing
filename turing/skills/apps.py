"""Open installed apps ("打开微信" / "open Chrome") and common folders ("打开下载")."""

import difflib
import json
import os
import re
import subprocess
import threading
import time
import winreg
from dataclasses import dataclass

from pypinyin import lazy_pinyin

from . import Context, Fallback, Skill, Tool, browsers, schema

_OPEN = re.compile(r"^(打开|启动|运行|开启|开|open|launch|start|run)\s*(.+)$")
_CLOSE = re.compile(r"^(关闭|关掉|关上|退出|结束|关)\s*(.+)$|^(close|quit|exit)\s+(.+)$")
_THIS_WINDOW = {"当前窗口", "这个窗口", "窗口", "当前的窗口", "this window", "the window", "window"}
_TURING = {"图灵", "turing"}
_JUNK = re.compile(r"卸载|uninstall|帮助|help|readme|release notes|documentation|manual|website", re.I)
_STRIP = re.compile(r"[\s\-_.·()（）]")

# Known folders, read from the registry so redirected folders (e.g. D:\Documents) work.
_FOLDERS = {
    "Desktop": ("桌面", "desktop"),
    "{374DE290-123F-4565-9164-39C4925E467B}": ("下载", "下载文件夹", "downloads", "download folder"),
    "Personal": ("文档", "我的文档", "documents", "my documents"),
    "My Pictures": ("图片", "相册", "pictures", "photos"),
    "My Music": ("音乐文件夹", "music folder"),
    "My Video": ("视频", "视频文件夹", "videos"),
}
_EXPLORER = ("文件管理器", "资源管理器", "文件资源管理器", "此电脑", "我的电脑", "文件夹",
             "file explorer", "explorer", "this pc", "folder", "folders", "files")
_BROWSER = ("浏览器", "browser", "the browser", "web browser")
_BROWSER_PROGIDS = {"Chrome": "Google Chrome", "MSEdge": "Microsoft Edge", "Firefox": "Firefox",
                    "Brave": "Brave", "Opera": "Opera"}


@dataclass
class App:
    name: str
    app_id: str
    key: str
    pinyin: str


def _key(name: str) -> str:
    return _STRIP.sub("", name.lower())


def _pinyin(name: str) -> str:
    return "".join(lazy_pinyin(_key(name)))


def list_start_apps() -> list[App]:
    """Every app in the Start menu (desktop and Store apps), via Get-StartApps."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
        capture_output=True, encoding="utf-8", timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    items = json.loads(out or "[]")
    if isinstance(items, dict):
        items = [items]
    return [App(i["Name"], i["AppID"], _key(i["Name"]), _pinyin(i["Name"]))
            for i in items if i.get("Name") and not _JUNK.search(i["Name"])]


def _match(query: str, apps: list[App]) -> App | None:
    q, qp = _key(query), _pinyin(query)
    if not q:
        return None
    for test in (
        lambda a: a.key == q,
        lambda a: a.pinyin == qp,
        lambda a: a.key.startswith(q),
        lambda a: len(q) >= 2 and q in a.key,
        lambda a: len(qp) >= 4 and qp in a.pinyin,  # homophones: 网易运 -> 网易云
    ):
        hits = [a for a in apps if test(a)]
        if hits:
            return min(hits, key=lambda a: len(a.key))  # "微信" over "微信开发者工具"
    return None


# Windows' own apps are listed under the system language's name: "open notepad" has to
# find 记事本 on Chinese Windows, and "打开记事本" Notepad on English Windows.
_SYSTEM_APPS = [("记事本", "notepad"), ("计算器", "calculator"), ("设置", "settings"), ("画图", "paint"),
                ("任务管理器", "task manager"), ("终端", "terminal"), ("相机", "camera"), ("照片", "photos"),
                ("时钟", "clock"), ("截图工具", "snipping tool"), ("控制面板", "control panel"),
                ("命令提示符", "command prompt"), ("文件资源管理器", "file explorer"),
                ("微软商店", "microsoft store"), ("应用商店", "microsoft store"), ("日历", "calendar"),
                ("邮件", "mail"), ("天气", "weather"), ("地图", "maps"), ("录音机", "sound recorder"),
                ("便笺", "sticky notes"), ("媒体播放器", "media player"), ("写字板", "wordpad")]


# Sites people "open" like apps, when no app by that name is installed.
_WEBSITES = {_key(k): v for k, v in {
    "youtube": "https://www.youtube.com", "油管": "https://www.youtube.com", "百度": "https://www.baidu.com",
    "baidu": "https://www.baidu.com", "谷歌": "https://www.google.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "谷歌邮箱": "https://mail.google.com", "b站": "https://www.bilibili.com",
    "哔哩哔哩": "https://www.bilibili.com", "bilibili": "https://www.bilibili.com", "知乎": "https://www.zhihu.com",
    "微博": "https://weibo.com", "淘宝": "https://www.taobao.com", "京东": "https://www.jd.com",
    "小红书": "https://www.xiaohongshu.com", "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "outlook": "https://outlook.live.com", "netflix": "https://www.netflix.com",
    "twitter": "https://x.com", "推特": "https://x.com", "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com", "reddit": "https://www.reddit.com", "维基百科": "https://zh.wikipedia.org",
    "wikipedia": "https://en.wikipedia.org", "亚马逊": "https://www.amazon.ca", "amazon": "https://www.amazon.ca",
    "谷歌地图": "https://www.google.com/maps", "地图": "https://www.google.com/maps", "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
}.items()}


def _other_language(query: str) -> list[str]:
    k = _key(query)
    return [en if _key(zh) == k else zh for zh, en in _SYSTEM_APPS if k in (_key(zh), _key(en))]


def find_app(query: str, apps: list[App], aliases: dict[str, str]) -> App | None:
    # Try the alias target and the spoken name: on Chinese Windows "记事本" is listed
    # as 记事本, on English Windows as Notepad.
    target = aliases.get(_key(query))
    queries = [target, query] if target else [query]
    queries += [q for q in _other_language(query) if q not in queries]
    for q in queries:
        if app := _match(q, apps):
            return app
    scored = [(difflib.SequenceMatcher(None, _pinyin(q), a.pinyin).ratio(), a)
              for q in queries for a in apps]
    score, best = max(scored, key=lambda s: s[0], default=(0, None))
    return best if score >= 0.75 else None


def _clean(name: str) -> str:
    """"我的微信" / "the chrome app" -> the app's name."""
    return re.sub(r"^(the|my|a)\s+|^(我的|一个|那个|这个)|\s*(app|软件|程序|应用)$", "",
                  name.strip(), flags=re.I).strip()


def switch_to_running(app: App) -> bool:
    """If the app is already running, bring its window forward (even from the tray).

    Starting it again can do the wrong thing: a second WeChat shows its login window.
    Only works for apps listed by their .exe path, which covers most desktop apps.
    """
    if not (os.path.isabs(app.app_id) and app.app_id.lower().endswith(".exe")):
        return False
    import win32gui

    from .. import keyboard
    from .messaging import WECHAT_PROCESSES, show_wechat_from_tray

    hwnd = keyboard.window_of_exe(app.app_id, title=app.name)
    if not hwnd:
        return False
    if not win32gui.IsWindowVisible(hwnd):
        # In the tray: the app has to show its own window (see keyboard.focus).
        if os.path.basename(app.app_id).lower() in WECHAT_PROCESSES:
            if not show_wechat_from_tray(hwnd):
                raise TrayError(app.name)
        else:
            os.startfile(app.app_id)  # single-instance apps answer by showing their window
            end = time.monotonic() + 4
            while not win32gui.IsWindowVisible(hwnd) and time.monotonic() < end:
                time.sleep(0.1)
            return True  # started it the app's own way; it shows itself
    return keyboard.focus(hwnd)


class TrayError(RuntimeError):
    """The app is in the tray and wouldn't show itself."""


def launch(app: App):
    app_id = app.app_id
    if "://" in app_id or os.path.isabs(app_id):
        os.startfile(app_id)
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])


def _folder(query: str) -> str | None:
    key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    for reg_name, names in _FOLDERS.items():
        if query in names:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return os.path.expandvars(winreg.QueryValueEx(k, reg_name)[0])
    return None


def _default_browser() -> str:
    key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            prog_id = winreg.QueryValueEx(k, "ProgId")[0]
    except OSError:
        return "Microsoft Edge"
    return next((name for frag, name in _BROWSER_PROGIDS.items() if frag.lower() in prog_id.lower()),
                "Microsoft Edge")


class Apps(Skill):
    name = "apps"

    def __init__(self, config):
        super().__init__(config)
        self.aliases = {_key(k): v for k, v in config.get("apps", {}).get("aliases", {}).items()}
        self._apps: list[App] = []
        self._ready = threading.Event()
        threading.Thread(target=self.refresh, daemon=True).start()

    def refresh(self):
        self._apps = list_start_apps()
        self._ready.set()

    @property
    def apps(self) -> list[App]:
        self._ready.wait(timeout=30)
        return self._apps

    def handle(self, text: str, ctx: Context) -> str | None:
        c = _CLOSE.match(text)
        if c:
            return self.close(_clean(c.group(2) or c.group(4)), ctx)
        profile = ""
        if leading := browsers.split_leading(text):
            text, profile = leading
        m = _OPEN.match(text)
        if not m:
            return None
        raw = m.group(2).strip()
        if not profile:
            app_part, profile = browsers.split_profile(raw)
            if profile and not browsers.kind_of(self._resolve(_clean(app_part))):
                profile = ""  # "open X with Y" about something other than a browser
            elif profile:
                raw = app_part
        return self.open(raw, ctx, profile)

    def _resolve(self, query: str) -> str:
        """The app name a query will open, without opening it ('' if unknown)."""
        if query in _BROWSER:
            return _default_browser()
        app = find_app(query, self.apps, self.aliases)
        return app.name if app else query

    def open(self, raw: str, ctx: Context, profile: str = "", wait: bool = False) -> str:
        query = _clean(raw)
        if path := _folder(raw) or _folder(query):
            os.startfile(path)
            return ctx.reply(f"已打开{query}", f"Opening {query}")
        if raw in _EXPLORER or query in _EXPLORER:
            subprocess.Popen(["explorer.exe"])
            return ctx.reply("已打开文件管理器", "Opening File Explorer")
        if query in _BROWSER:
            query = _default_browser()
        app = find_app(query, self.apps, self.aliases)
        if app is None:
            # One refresh in case it was installed after Turing started.
            self.refresh()
            app = find_app(query, self._apps, self.aliases)
        if app is None and (home := _WEBSITES.get(_key(query))):
            import webbrowser

            webbrowser.open(home)
            return ctx.reply(f"已在浏览器里打开{raw}", f"Opened {raw} in the browser")
        if app is None:
            # Let the AI (if any) take a smarter guess before giving up.
            return Fallback(ctx.reply(f"没找到叫{query}的软件", f"I couldn't find an app called {query}"))
        if profile and (kind := browsers.kind_of(app.name)):
            return self._open_profile(kind, profile, ctx)
        # Typing tools check this, so keys meant for it can't land in another window.
        ctx.state["opened"] = {"name": app.name, "at": time.monotonic(),
                               "exe": app.app_id if app.app_id.lower().endswith(".exe") else ""}
        if wait:
            from . import windows

            ctx.state["windows_before"] = set(windows.app_windows())
        try:
            switched = switch_to_running(app)
        except TrayError:
            from .messaging import TRAY_HINT_EN, TRAY_HINT_ZH

            return ctx.reply(TRAY_HINT_ZH, TRAY_HINT_EN)
        if switched:
            return ctx.reply(f"已切换到{app.name}", f"Switched to {app.name}")
        # A browser with several profiles opens at "Who's using Chrome?"; go straight
        # into the last one used, as the browser itself would on a link.
        if (kind := browsers.kind_of(app.name)) and (last := browsers.last_used(kind)):
            if browsers.launch(kind, last):
                return ctx.reply(f"正在打开{app.name}", f"Opening {app.name}")
        launch(app)
        if wait:
            return self._wait_for_window(app, ctx)
        return ctx.reply(f"正在打开{app.name}", f"Opening {app.name}")

    def _wait_for_window(self, app: App, ctx: Context, seconds: float = 10) -> str:
        """For the AI: wait until the app's window is up and in front, so whatever it types
        next goes into this app (and say so if it never came)."""
        import psutil
        import win32process

        from . import windows

        before = ctx.state.pop("windows_before", set())
        started, end = time.monotonic(), time.monotonic() + seconds
        while time.monotonic() < end:
            new = [h for h in windows.app_windows() if h not in before]
            if not new and time.monotonic() - started > 1.5:
                # Already running (Notepad just adds a tab): its existing window will do.
                existing = windows.find(app.name)
                new = [existing] if existing else []
            if new and windows.focus(new[0]):
                try:
                    exe = psutil.Process(win32process.GetWindowThreadProcessId(new[0])[1]).exe()
                except psutil.Error:
                    exe = ""
                ctx.state["opened"].update(exe=exe, at=time.monotonic())
                return f"{app.name} is open and in front (window \"{windows.label(new[0])}\"); typing goes there now."
            time.sleep(0.3)
        return (f"Started {app.name}, but its window didn't appear within {seconds:.0f} s. "
                "Don't type yet; tell the user.")

    def _open_profile(self, kind: str, wanted: str, ctx: Context) -> str:
        browser = browsers.NAMES[kind]
        choices = browsers.profiles(kind)
        profile = browsers.find(wanted, choices)
        if profile is None:
            names = "、".join(p.label for p in choices) or "（没有找到）"
            return ctx.reply(f"{browser} 里没有能确定是“{wanted}”的账号。现有的是：{names}。",
                             f"No {browser} profile clearly matches \"{wanted}\". "
                             f"There are: {', '.join(p.label for p in choices)}.")
        if not browsers.launch(kind, profile):
            return ctx.reply(f"没找到 {browser} 的程序文件。", f"Couldn't find {browser} itself.")
        return ctx.reply(f"正在用 {profile.label} 打开 {browser}",
                         f"Opening {browser} as {profile.label}")

    def close(self, query: str, ctx: Context) -> str:
        """Close an app's windows the way their × button does."""
        from .. import keyboard

        if query.lower() in _TURING:
            return ctx.reply("要退出图灵，请右键点屏幕角落的小圆球，选“退出图灵”。",
                             "To quit Turing, right-click the orb and choose Quit.")
        if query.lower() in _THIS_WINDOW:
            import win32gui

            keyboard.close(win32gui.GetForegroundWindow())
            return ctx.reply("已关闭当前窗口", "Closed the window")
        app = find_app(query, self.apps, self.aliases)
        windows = []
        if app and os.path.isabs(app.app_id) and app.app_id.lower().endswith(".exe"):
            windows = keyboard.windows_of_exe(app.app_id)
        if not windows:
            windows = keyboard.windows_titled(app.name if app else query) or keyboard.windows_titled(query)
        if not windows:
            name = app.name if app else query
            return Fallback(ctx.reply(f"没有找到打开着的{name}", f"{name} doesn't seem to be open"))
        for hwnd in windows[:5]:
            keyboard.close(hwnd)
        name = app.name if app else query
        return ctx.reply(f"已关闭{name}", f"Closed {name}")

    def tools(self) -> list[Tool]:
        return [
            Tool("close_app",
                 "Close an app's windows, like clicking its × (the app may ask to save). Pass "
                 "the name the user said, or \"当前窗口\" for the window in front.",
                 schema({"name": {"type": "string"}}, ["name"]),
                 lambda args, ctx: self.close(_clean(args["name"]), ctx)),
            Tool("open_app",
                 "Open an installed app, a common folder (desktop, downloads, documents, pictures, "
                 "videos), File Explorer, or the default browser. Pass the name the user said, "
                 "e.g. 微信, QQ音乐, Chrome, 下载. For Chrome or Edge, `profile` opens it "
                 "straight into one account (profile name, person's name, email or a word like "
                 "student / work); without it the browser may stop at its profile picker.",
                 schema({"name": {"type": "string"}, "profile": {"type": "string"}}, ["name"]),
                 lambda args, ctx: self.open(args["name"].strip().lower(), ctx,
                                             (args.get("profile") or "").strip(), wait=True)),
            Tool("find_apps",
                 "Search the Start menu for installed apps whose name contains `query`. Use it when "
                 "open_app can't find what the user asked for.",
                 schema({"query": {"type": "string"}}, ["query"]),
                 lambda args, ctx: ", ".join(self._search(args["query"])) or "no matches"),
        ]

    def _search(self, query: str) -> list[str]:
        q, qp = _key(query), _pinyin(query)
        return [a.name for a in self.apps if q in a.key or (len(qp) >= 2 and qp in a.pinyin)][:15]
