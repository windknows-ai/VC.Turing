"""Windows virtual desktops: switch to one by its name ("切换到学习那个桌面"), by number, or
next / previous; make a new one; say which one this is.

Windows keeps the desktops' order, names and the current one in the registry. Switching
is done with the system's own Ctrl+Win+←/→ the right number of times, and then checked
by reading the current desktop back, so Turing never says it switched when it didn't.
"""

import re
import time
import uuid
import winreg

from pypinyin import lazy_pinyin

from . import Context, Skill, Tool, schema

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_SWITCH = re.compile(r"^(?:帮我)?(?:切换到|切换去|切到|切去|转到|跳到|去|换到|回到)\s*(.+?)\s*(?:那个|这个)?\s*(?:虚拟)?桌面$")
_SWITCH_EN = re.compile(r"^(?:switch|go|move)\s+to\s+(?:the\s+)?(.+?)\s+desktop$"
                        r"|^(?:switch|go)\s+to\s+desktop\s+(.+)$", re.I)
_NEXT = re.compile(r"^(?:切换到|切到|去)?下一个桌面$|^(?:switch|go) to (?:the )?next desktop$", re.I)
_PREV = re.compile(r"^(?:切换到|切到|去|回到)?上一个桌面$|^(?:switch|go) (?:back )?to (?:the )?previous desktop$", re.I)
_NEW = re.compile(r"^(?:新建|创建|添加|加|开)(?:一个)?(?:新的?)?(?:虚拟)?桌面$|^(?:create|add|make) a new desktop$|^new desktop$", re.I)
_WHICH = re.compile(r"^(?:我)?现在(?:是)?在(?:哪个|第几个)桌面|^(?:which|what) desktop am i on", re.I)


def desktops() -> tuple[list[tuple[uuid.UUID, str]], int]:
    """[(id, name)] in order, and the index of the current one (-1 if unknown)."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
        ids = bytes(winreg.QueryValueEx(k, "VirtualDesktopIDs")[0])
        try:
            current = uuid.UUID(bytes_le=bytes(winreg.QueryValueEx(k, "CurrentVirtualDesktop")[0]))
        except OSError:
            current = None
    order = [uuid.UUID(bytes_le=ids[i:i + 16]) for i in range(0, len(ids), 16)]
    named = []
    for i, guid in enumerate(order):
        name = ""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY + rf"\Desktops\{{{str(guid).upper()}}}") as d:
                name = winreg.QueryValueEx(d, "Name")[0]
        except OSError:
            pass
        named.append((guid, name or f"桌面 {i + 1}"))
    return named, (order.index(current) if current in order else -1)


def find(query: str, names: list[str]) -> int | None:
    """Index of the desktop the user means: by name, by sound, or by number."""
    q = query.strip().lower()
    q = re.sub(r"^(?:第|desktop\s*|桌面\s*)", "", q)
    q = re.sub(r"(?:个)$", "", q)
    if q.isdigit():
        return int(q) - 1 if 0 < int(q) <= len(names) else None
    if q in _CN_NUM and _CN_NUM[q] <= len(names):
        return _CN_NUM[q] - 1
    lowered = [n.lower() for n in names]
    for match in ([i for i, n in enumerate(lowered) if n == q],
                  [i for i, n in enumerate(lowered) if q in n or n in q],
                  [i for i, n in enumerate(names) if "".join(lazy_pinyin(n)) == "".join(lazy_pinyin(q))]):
        if len(match) == 1:
            return match[0]
    return None


def _press(keys: str):
    from .. import keyboard

    keyboard.press(keys)


def switch_to(target: int, timeout: float = 2.0) -> bool:
    """Go to desktop `target` (0-based) and confirm Windows really is there."""
    _, current = desktops()
    if current < 0:
        return False
    step = "ctrl+win+right" if target > current else "ctrl+win+left"
    for _ in range(abs(target - current)):
        _press(step)
        time.sleep(0.25)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if desktops()[1] == target:
            return True
        time.sleep(0.1)
    return False


class Desktops(Skill):
    name = "desktops"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _WHICH.match(text):
            return self.which(ctx)
        if _NEW.match(text):
            return self.new(ctx)
        if _NEXT.match(text):
            return self.switch("next", ctx)
        if _PREV.match(text):
            return self.switch("previous", ctx)
        m = _SWITCH.match(text) or _SWITCH_EN.match(text)
        if m:
            return self.switch(next(g for g in m.groups() if g), ctx)
        return None

    def which(self, ctx: Context) -> str:
        named, current = desktops()
        if current < 0:
            return ctx.reply("我看不出现在是哪个桌面。", "I can't tell which desktop this is.")
        names = "、".join(n for _, n in named)
        return ctx.reply(f"现在在第 {current + 1} 个桌面“{named[current][1]}”。一共有：{names}。",
                         f"You're on desktop {current + 1}, \"{named[current][1]}\". All of them: {names}.")

    def switch(self, wanted: str, ctx: Context) -> str:
        named, current = desktops()
        names = [n for _, n in named]
        if wanted in ("next", "previous"):
            target = current + (1 if wanted == "next" else -1)
            if not 0 <= target < len(named):
                return ctx.reply("已经是最后一个桌面了。" if wanted == "next" else "已经是第一个桌面了。",
                                 "That's already the last desktop." if wanted == "next"
                                 else "That's already the first desktop.")
        else:
            target = find(wanted, names)
            if target is None:
                return ctx.reply(f"没有找到叫“{wanted}”的桌面。现有的是：{'、'.join(names)}。",
                                 f"There's no desktop called \"{wanted}\". There are: {', '.join(names)}.")
        if target == current:
            return ctx.reply(f"现在就在“{names[target]}”桌面。", f"You're already on \"{names[target]}\".")
        if switch_to(target):
            return ctx.reply(f"已切换到“{names[target]}”桌面", f"Switched to the \"{names[target]}\" desktop")
        return ctx.reply("切换桌面没有成功。", "Switching desktops didn't work.")

    def new(self, ctx: Context) -> str:
        before = len(desktops()[0])
        _press("ctrl+win+d")
        end = time.monotonic() + 2
        while time.monotonic() < end:
            named, current = desktops()
            if len(named) > before:
                return ctx.reply(f"已新建并切换到第 {current + 1} 个桌面", f"Made a new desktop, number {current + 1}")
            time.sleep(0.1)
        return ctx.reply("新建桌面没有成功。", "Making a new desktop didn't work.")

    def tools(self) -> list[Tool]:
        return [
            Tool("switch_desktop",
                 "Switch Windows virtual desktop: pass the desktop's name as the user said it "
                 "(e.g. 学习), its number, \"next\" or \"previous\". Checks it really switched.",
                 schema({"desktop": {"type": "string"}}, ["desktop"]),
                 lambda args, ctx: self.switch(str(args["desktop"]).strip(), ctx)),
            Tool("new_desktop", "Create a new virtual desktop and go to it.", schema(),
                 lambda args, ctx: self.new(ctx)),
            Tool("list_desktops", "Which virtual desktops exist, and which one the user is on.",
                 schema(), lambda args, ctx: self.which(ctx)),
        ]
