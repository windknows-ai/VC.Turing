"""Files: make a folder, find a file by name, open the latest download. Results are
checked on disk; downloaded programs are only shown in Explorer, never run."""

import os
import re
import subprocess
import time

from . import Context, Skill, Tool, schema
from .apps import _folder

_PLACES = r"桌面|文档|我的文档|下载|下载文件夹|图片|视频|desktop|documents|downloads|pictures|videos"
_NEW = re.compile(rf"^(?:在|到)?\s*({_PLACES})?\s*(?:上|里|里面)?\s*(?:新建|创建|建|新增)(?:一个)?\s*"
                  r"(?:名叫|叫做?|名字是|名为)?\s*[“\"]?(.*?)[”\"]?\s*(?:的)?文件夹$"
                  rf"|^(?:create|make) a (?:new )?folder(?: called| named)?\s*(.*?)(?: on (?:the )?({_PLACES}))?$", re.I)
_FIND = re.compile(rf"^(?:帮我)?(?:找|搜|查|搜索|查找)(?:一下|找)?\s*(?:在)?\s*({_PLACES}|电脑)?\s*(?:上|里|里面)?\s*(?:的)?"
                   r"\s*(.+?)\s*(?:这个|那个)?(?:文件|文档)$|^find (?:the )?(?:file )?(.+?) files?$", re.I)
_LATEST = re.compile(r"^(?:打开|看看)?(?:我)?(?:最近|刚才|刚刚|最新)(?:一个)?下载的(?:那个)?(?:文件|东西)$|^open (?:the |my )?(?:latest|last|newest) download$", re.I)
_RUNNABLE = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".scr", ".lnk", ".com"}
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "$recycle.bin", "appdata"}


def place(name: str | None) -> str:
    return _folder(name.lower()) if name and _folder(name.lower()) else _folder("桌面")


def new_folder(where: str | None, name: str) -> str | None:
    """Create it (adding (2), (3)… if taken); the path if it exists afterwards."""
    base = place(where)
    name = re.sub(r'[\\/:*?"<>|]', "", name).strip() or "新建文件夹"
    path, n = os.path.join(base, name), 2
    while os.path.exists(path):
        path, n = os.path.join(base, f"{name} ({n})"), n + 1
    os.makedirs(path)
    return path if os.path.isdir(path) else None


def find_files(query: str, where: str | None = None, limit: int = 5, seconds: float = 4.0) -> list[str]:
    """Files whose name contains `query`, in the user's own folders (newest first)."""
    roots = [place(where)] if where and where != "电脑" else [_folder(f) for f in ("桌面", "文档", "下载")]
    q = query.lower().strip()
    found, end = [], time.monotonic() + seconds
    for root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            found += [os.path.join(folder, f) for f in files + dirs if q in f.lower()]
            if time.monotonic() > end or len(found) > 200:
                break
    found.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return found[:limit]


def show_in_explorer(path: str):
    subprocess.Popen(["explorer.exe", "/select,", path])


def latest_download() -> str | None:
    folder = _folder("下载")
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.isfile(os.path.join(folder, f)) and not f.endswith((".crdownload", ".part", ".tmp"))]
    return max(files, key=os.path.getmtime) if files else None


class Files(Skill):
    name = "files"

    def handle(self, text: str, ctx: Context) -> str | None:
        if m := _NEW.match(text):
            where = m.group(1) or m.group(4)
            name = (m.group(2) if m.group(2) is not None else m.group(3)) or ""
            return self.make(where, name, ctx)
        if _LATEST.match(text):
            return self.latest(ctx)
        if m := _FIND.match(text):
            return self.find(m.group(2) or m.group(3), m.group(1), ctx)
        return None

    def make(self, where, name, ctx: Context) -> str:
        path = new_folder(where, name)
        if not path:
            return ctx.reply("文件夹没有建成。", "The folder wasn't created.")
        show_in_explorer(path)
        folder = os.path.basename(path)
        return ctx.reply(f"已新建文件夹“{folder}”", f"Created the folder \"{folder}\"")

    def find(self, query: str, where, ctx: Context) -> str:
        hits = find_files(query, where)
        if not hits:
            return ctx.reply(f"在桌面、文档和下载里没找到名字带“{query}”的文件。",
                             f"No files named like \"{query}\" in Desktop, Documents or Downloads.")
        show_in_explorer(hits[0])
        names = "、".join(os.path.basename(h) for h in hits[:3])
        more = ctx.reply(f"等 {len(hits)} 个", f" and {len(hits) - 1} more") if len(hits) > 1 else ""
        return ctx.reply(f"找到了：{names}{more}，已在文件夹里选中最新的那个。",
                         f"Found {names}{more}; the newest is selected in Explorer.")

    def latest(self, ctx: Context) -> str:
        path = latest_download()
        if not path:
            return ctx.reply("下载文件夹是空的。", "The Downloads folder is empty.")
        name = os.path.basename(path)
        if os.path.splitext(name)[1].lower() in _RUNNABLE:
            show_in_explorer(path)  # never run a downloaded program by voice
            return ctx.reply(f"最近下载的是程序“{name}”，为了安全我只在文件夹里选中它，没有运行。",
                             f"The latest download is a program, \"{name}\"; I selected it in Explorer but didn't run it.")
        os.startfile(path)
        return ctx.reply(f"已打开最近下载的“{name}”", f"Opened your latest download, \"{name}\"")

    def tools(self) -> list[Tool]:
        return [
            Tool("create_folder", "Create a folder in desktop / documents / downloads / pictures.",
                 schema({"name": {"type": "string"}, "where": {"type": "string"}}, ["name"]),
                 lambda a, ctx: self.make(a.get("where"), a["name"], ctx)),
            Tool("find_files", "Find files by part of their name in the user's Desktop, Documents and "
                 "Downloads; selects the newest match in Explorer.",
                 schema({"name": {"type": "string"}, "where": {"type": "string"}}, ["name"]),
                 lambda a, ctx: self.find(a["name"], a.get("where"), ctx)),
            Tool("open_latest_download", "Open the most recently downloaded file (programs are only shown).",
                 schema(), lambda a, ctx: self.latest(ctx)),
        ]
