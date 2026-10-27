"""Everyday keys in the app the user is working in: save, undo, copy, paste, select all,
zoom, scroll, full screen, going back to the previous window.

Keys only ever go to the user's own front window (never Turing's), after checking it
really is in front, and the reply names that app, so "保存一下" can't land elsewhere.
"""

import re

import win32gui

from .. import keyboard
from . import Context, Skill, Tool, schema, windows

# action: (keys, zh done, en done)
ACTIONS = {
    "save": ("ctrl+s", "已在{}里保存（按了 Ctrl+S）", "Saved in {} (Ctrl+S)"),
    "save_as": ("ctrl+shift+s", "已在{}里打开“另存为”", "Opened Save As in {}"),
    "undo": ("ctrl+z", "已在{}里撤销", "Undid that in {}"),
    "redo": ("ctrl+y", "已在{}里重做", "Redid that in {}"),
    "select_all": ("ctrl+a", "已在{}里全选", "Selected all in {}"),
    "copy": ("ctrl+c", "已复制{}里选中的内容", "Copied the selection in {}"),
    "cut": ("ctrl+x", "已剪切{}里选中的内容", "Cut the selection in {}"),
    "paste": ("ctrl+v", "已粘贴到{}", "Pasted into {}"),
    "enter": ("enter", "已在{}里按了回车", "Pressed Enter in {}"),
    "zoom_in": ("ctrl+plus", "已把{}放大", "Zoomed in {}"),
    "zoom_out": ("ctrl+minus", "已把{}缩小", "Zoomed out {}"),
    "zoom_reset": ("ctrl+0", "已把{}恢复默认大小", "Reset the zoom in {}"),
    "page_down": ("pagedown", "已在{}里往下翻了一页", "Paged down in {}"),
    "page_up": ("pageup", "已在{}里往上翻了一页", "Paged up in {}"),
    "top": ("ctrl+home", "已滚到{}的最上面", "Went to the top in {}"),
    "bottom": ("ctrl+end", "已滚到{}的最下面", "Went to the bottom in {}"),
    "fullscreen": ("f11", "已让{}全屏（按了 F11）", "Made {} full screen (F11)"),
    "video_fullscreen": ("f", "已让{}里的视频全屏", "Made the video in {} full screen"),
    "exit_fullscreen": ("esc", "已在{}里退出全屏", "Left full screen in {}"),
    "find": ("ctrl+f", "已在{}里打开查找", "Opened Find in {}"),
    "print": ("ctrl+p", "已在{}里打开打印", "Opened Print in {}"),
}
PATTERNS = [
    ("save_as", r"^(?:帮我)?(?:把这个文件)?另存为$|^save as$"),
    ("save", r"^(?:帮我)?(?:保存|存)(?:一下|下)?(?:文件|这个|文档)?$|^save(?: this| it| the file)?$"),
    ("undo", r"^(?:撤销|撤回|撤销一下|返回上一步)(?:刚才的?操作)?$|^undo(?: that| it)?$"),
    ("redo", r"^重做(?:一下)?$|^redo(?: that)?$"),
    ("select_all", r"^全选(?:一下)?$|^select all$"),
    ("copy", r"^复制(?:一下)?(?:选中的?(?:内容|文字)?)?$|^copy(?: that| it)?$"),
    ("cut", r"^剪切(?:一下)?$|^cut(?: that| it)?$"),
    ("paste", r"^粘贴(?:一下)?$|^paste(?: it)?$"),
    ("enter", r"^(?:按一?下)?回车(?:键)?$|^press enter$"),
    ("zoom_in", r"^(?:把(?:字|页面|网页)?)?放大(?:一点|一些|些)?$|^(?:字)?(?:调)?大一点$|^zoom in$"),
    ("zoom_out", r"^(?:把(?:字|页面|网页)?)?缩小(?:一点|一些|些)?$|^zoom out$"),
    ("zoom_reset", r"^(?:恢复|还原)(?:默认|原来的)?(?:大小|缩放)$|^reset (?:the )?zoom$"),
    ("page_down", r"^(?:往下|向下)(?:翻|滚)(?:一页|一下)?$|^下一页$|^scroll down$|^page down$"),
    ("page_up", r"^(?:往上|向上)(?:翻|滚)(?:一页|一下)?$|^上一页$|^scroll up$|^page up$"),
    ("top", r"^(?:滚|翻|回)到(?:最)?(?:上面|顶部|开头)$|^(?:scroll|go) to the top$"),
    ("bottom", r"^(?:滚|翻)到(?:最)?(?:下面|底部|结尾)$|^(?:scroll|go) to the bottom$"),
    ("video_fullscreen", r"^(?:把)?视频全屏(?:播放)?$|^全屏(?:播放|看)视频$|^(?:make )?(?:the )?video full ?screen$"),
    ("fullscreen", r"^(?:网页|窗口)?全屏(?:播放)?$|^(?:go )?full ?screen$"),
    ("exit_fullscreen", r"^(?:退出|关闭|取消)全屏$|^exit full ?screen$"),
    ("find", r"^(?:在(?:页面|网页)里)?查找$|^find on (?:the )?page$"),
    ("print", r"^打印(?:一下)?(?:这个|这页|文件)?$|^print(?: this)?$"),
]
PATTERNS = [(a, re.compile(p, re.I)) for a, p in PATTERNS]
_PREVIOUS = re.compile(r"^(?:回到|切回|切到|返回)上一个(?:窗口|程序|软件)$|^切换窗口$|^switch (?:back )?(?:to the )?(?:previous|last) window$|^switch windows?$", re.I)


def act(action: str, ctx=None) -> tuple[bool, str, str]:
    """(done, app name, keys pressed). Only into the user's own window, once it's really in
    front, and, right after an app was opened for this command, only into that app."""
    hwnd = windows.current_window()
    if hwnd is None:
        return False, "", ""
    name = windows.label(hwnd)
    if ctx is not None:
        from .keys import not_the_app_just_opened

        if not_the_app_just_opened(ctx, hwnd):
            return False, name, ""
    if win32gui.GetForegroundWindow() != hwnd and not windows.focus(hwnd):
        return False, name, ""
    keys = ACTIONS[action][0]
    if action == "video_fullscreen" and windows.process_name(hwnd) not in windows.BROWSERS:
        keys = "f11"  # a video app rather than a web player: the window's own full screen
    keyboard.press(keys)
    return True, name, keys


class Editing(Skill):
    name = "editing"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _PREVIOUS.match(text):
            return self.previous(ctx)
        for action, pattern in PATTERNS:
            if pattern.match(text):
                return self.do(action, ctx)
        return None

    def do(self, action: str, ctx: Context) -> str:
        done, name, keys = act(action, ctx)
        if not name:
            return ctx.reply("前面没有可以操作的窗口。", "There's no window in front to do that in.")
        if not done:
            return ctx.reply(f"没有在{name}里按键：要操作的软件还没到前面来。",
                             f"Nothing was pressed in {name}: the app you meant isn't in front yet.")
        if action == "video_fullscreen" and keys == "f11":
            action = "fullscreen"  # not a web player: the whole window went full screen
        _, zh, en = ACTIONS[action]
        return ctx.reply(zh.format(name), en.format(name))

    def previous(self, ctx: Context) -> str:
        order = windows.app_windows()
        front = win32gui.GetForegroundWindow()
        others = [h for h in order if h != front]
        # When Turing's own window is in front, "previous" is the user's front app's predecessor.
        target = others[1] if front not in order and len(others) > 1 else (others[0] if others else None)
        if target is None:
            return ctx.reply("没有别的窗口可以切换。", "There's no other window to switch to.")
        name = windows.label(target)
        if windows.focus(target):
            return ctx.reply(f"已切换到{name}", f"Switched to {name}")
        return ctx.reply(f"没能切换到{name}。", f"Couldn't switch to {name}.")

    def tools(self) -> list[Tool]:
        return [
            Tool("edit_key",
                 "Do an everyday key action in the app the user is working in (never Turing): "
                 + ", ".join(ACTIONS) + ". Use this instead of press_keys for these.",
                 schema({"action": {"type": "string", "enum": list(ACTIONS)}}, ["action"]),
                 lambda a, ctx: self.do(a["action"], ctx)),
            Tool("previous_window", "Switch back to the window the user was in before.", schema(),
                 lambda a, ctx: self.previous(ctx)),
        ]
