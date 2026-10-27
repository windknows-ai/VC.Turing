"""Send WeChat messages: "给土豆发微信说你好" / "send a WeChat message to Tom saying hi".

Uses WeChat's own keyboard shortcuts (Ctrl+F to find the chat, Enter to send) rather
than clicking on the screen, which is far more reliable. Always asks before sending.
"""

import re
import time

from . import Context, Skill, Tool, schema

WECHAT_PROCESSES = ("weixin.exe", "wechat.exe")
WECHAT_SHOW_KEYS = "ctrl+alt+w"  # WeChat's own "show WeChat" shortcut (its default)


TRAY_HINT_ZH = ("微信在右下角托盘里，我用微信的快捷键 Ctrl+Alt+W 没能把它叫出来。请在微信设置的“快捷键”里打开"
                "“显示/隐藏窗口”，或者先点一下托盘里的微信图标。")
TRAY_HINT_EN = ("WeChat is in the tray and its Ctrl+Alt+W shortcut didn't bring it back. Turn on the show/hide "
                "window shortcut in WeChat's settings, or click WeChat's tray icon first.")


def show_wechat_from_tray(hwnd: int, seconds: float = 2.5) -> bool:
    """Ask WeChat to show its window itself, with its own shortcut. Forcing a hidden WeChat
    window visible leaves it frozen; starting Weixin.exe again opens a second, logged-out
    WeChat. False if the shortcut didn't bring it back (changed or turned off in WeChat)."""
    import win32gui

    from .. import keyboard

    if win32gui.IsWindowVisible(hwnd):
        return True
    keyboard.press(WECHAT_SHOW_KEYS)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if win32gui.IsWindowVisible(hwnd):
            time.sleep(0.3)  # let it finish drawing before keys go to it
            return True
        time.sleep(0.1)
    return False

_ZH = re.compile(
    r"^(?:用微信)?(?:给|跟|向)(?P<to>.+?)(?:发|发送)(?:一?条|个|一下)?(?:微信|消息|信息|微信消息)?"
    r"(?:说|内容是|内容为|：|:)\s*(?P<msg>.+)$"
    r"|^(?:用微信)?(?:发|发送)(?:一?条|个)?(?:微信|消息|信息|微信消息)(?:给|到)(?P<to2>.+?)(?:说|：|:)\s*(?P<msg2>.+)$"
    r"|^用微信(?:告诉|跟)(?P<to3>.+?)说\s*(?P<msg3>.+)$"
)
# "跟我说个笑话" is a request to Turing, not a message to send.
_NOT_A_CONTACT = {"我", "我们", "你", "图灵", "turing", "me", "us", "you"}
_EN = re.compile(
    r"^(?:send|text)\s+(?:a\s+)?(?:wechat\s+)?(?:message\s+)?to\s+(?P<to>.+?)\s+(?:saying|that says|:)\s*(?P<msg>.+)$"
    r"|^(?:tell|message)\s+(?P<to2>.+?)\s+on\s+wechat\s+(?:that\s+)?(?P<msg2>.+)$",
    re.I,
)


# Calls, which Turing can't place (yet).
_CALL = re.compile(r"打(?:个|一个|一通)?(?:微信)?(?:视频|语音|电话)|视频(?:通话|电话|聊天)|语音(?:通话|电话)|"
                   r"(?:call|video ?chat|facetime|ring)", re.I)
# ...unless it's the text of a message: "发微信说晚上打电话给你".
_DICTATED = re.compile(r"说|告诉|写|发(?:个|一个|一条)?(?:消息|信息|微信)|saying|tell", re.I)
# Other ways to send a message, which Turing can't do (yet).
_OTHER_APPS = re.compile(r"QQ|qq|短信|邮件|邮箱|email|e-mail|钉钉|飞书|Telegram|WhatsApp|"
                         r"Discord|iMessage|SMS|text message", re.I)


def parse(text: str) -> tuple[str, str] | None:
    """(contact, message) from a spoken command, or None."""
    for pattern in (_ZH, _EN):
        m = pattern.match(text.strip())
        if m:
            groups = {k: v for k, v in m.groupdict().items() if v}
            to = next(v for k, v in groups.items() if k.startswith("to")).strip(" ，,")
            msg = next(v for k, v in groups.items() if k.startswith("msg")).strip()
            if to.lower() in _NOT_A_CONTACT:
                return None
            return to, msg
    return None


def send_wechat(contact: str, message: str) -> None:
    """Open the chat with `contact` in WeChat and send `message`. Raises if WeChat isn't open."""
    from .. import keyboard

    # The main window is titled 微信 and is often hidden in the tray, which is fine.
    hwnd = keyboard.find_window(WECHAT_PROCESSES, title="微信") or keyboard.find_window(WECHAT_PROCESSES)
    if hwnd is None:
        raise RuntimeError("WeChat is not running")
    if not show_wechat_from_tray(hwnd):
        raise RuntimeError("WeChat stayed in the tray")
    if not keyboard.focus(hwnd):
        raise RuntimeError("couldn't bring WeChat to the front")
    keyboard.press("ctrl+f")          # WeChat's search box
    time.sleep(0.4)
    keyboard.type_text(contact)
    time.sleep(1.2)                   # let the search results appear
    keyboard.press("enter")           # open the first match's chat; focus moves to its input
    time.sleep(0.8)
    keyboard.type_text(message)
    time.sleep(0.2)
    keyboard.press("enter")           # send


class Messaging(Skill):
    name = "messaging"

    def handle(self, text: str, ctx: Context) -> str | None:
        parsed = parse(text)
        if parsed is None:
            return None
        return self.send(*parsed, ctx)

    def send(self, contact: str, message: str, ctx: Context) -> str:
        asked = ctx.state.get("command", "")
        if _CALL.search(asked) and not _DICTATED.search(asked):
            # A call can't become a text message; Turing can't place WeChat calls.
            return ctx.reply("我还不能打微信电话或视频，什么都没有发。要发一条文字消息吗？",
                             "I can't make WeChat calls yet, so nothing was sent. Want to send a text message instead?")
        other = _OTHER_APPS.search(asked)
        if other and "微信" not in asked and "wechat" not in asked.lower():
            return ctx.reply(f"我现在只能用微信发消息，还不能用{other.group(0)}发。",
                             f"I can only send WeChat messages, not {other.group(0)}.")
        for _ in range(3):
            ctx.state.pop("correction", None)
            if ctx.confirm(ctx.reply(f"要用微信给{contact}发“{message}”吗？说“发送”或者“取消”。",
                                     f"Send “{message}” to {contact} on WeChat? Say send or cancel.")):
                break
            # "不是，发 Where are you": ask again with the corrected words.
            if not (fixed := ctx.state.pop("correction", None)):
                return ctx.reply("好的，不发了。", "OK, I won't send it.")
            message = fixed
        else:
            return ctx.reply("好的，不发了。", "OK, I won't send it.")
        try:
            send_wechat(contact, message)
        except RuntimeError as e:
            if "not running" in str(e):
                return ctx.reply("微信没有打开，请先登录微信。", "WeChat isn't open. Please sign in to WeChat first.")
            if "tray" in str(e):
                return ctx.reply(TRAY_HINT_ZH, TRAY_HINT_EN)
            return ctx.reply("没能切换到微信窗口，请把微信打开后再试。",
                             "I couldn't switch to WeChat. Open it and try again.")
        return ctx.reply(f"已经发给{contact}了。", f"Sent to {contact}.")

    def tools(self) -> list[Tool]:
        return [Tool(
            "send_wechat",
            "Send a WeChat message to a contact or group, by the name shown in WeChat. "
            "Turing asks the user to confirm out loud before sending, so don't ask first.",
            schema({"contact": {"type": "string"}, "message": {"type": "string"}},
                   ["contact", "message"]),
            lambda args, ctx: self.send(args["contact"].strip(), args["message"].strip(), ctx),
        )]
