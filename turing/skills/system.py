"""Small system actions and chit-chat."""

import ctypes
import re

from . import Context, Skill, Tool, schema

_LOCK = re.compile(r"^(锁屏|锁定(电脑|屏幕)|把(电脑|屏幕)锁(上|了)|lock (the |my )?(screen|computer|pc))$")
_WHO = re.compile(r"^(你是谁|你叫什么(名字)?|介绍一下你自己|who are you|what('s| is) your name)$")
_HELLO = re.compile(r"^(你好|嗨|哈喽|在吗|hi|hello|hey)$")
_THANKS = re.compile(r"^(谢谢|多谢|thanks|thank you)$")


class System(Skill):
    name = "system"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _LOCK.match(text):
            ctypes.windll.user32.LockWorkStation()
            return ctx.reply("已锁屏", "Locked")
        if _WHO.match(text):
            return ctx.reply("我是图灵，你的桌面语音助手。", "I'm Turing, your desktop voice assistant.")
        if _HELLO.match(text):
            return ctx.reply("你好，我在", "Hi, I'm here")
        if _THANKS.match(text):
            return ctx.reply("不客气", "You're welcome")
        return None

    def tools(self) -> list[Tool]:
        def lock(args, ctx):
            ctypes.windll.user32.LockWorkStation()
            return "locked"

        return [Tool("lock_screen", "Lock the Windows session.", schema(), lock)]
