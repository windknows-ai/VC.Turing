"""Let the AI see the user's screen: "屏幕上是什么", "用浏览器查一下这个界面", "这个报错什么意思"."""

import re

from . import Context, Fallback, Skill, Tool, ToolImage, schema

# Requests that are about what's on screen. They always need the AI, which takes the
# screenshot itself through the look_at_screen tool.
_ABOUT_SCREEN = re.compile(
    r"屏幕|界面|这个页面|当前页面|这一?页|这个窗口|当前窗口|这个报错|这个错误|这张图|这个图片|这段(话|文字|代码)"
    r"|\b(screen|this page|this window|this error|this picture|this image)\b", re.I)


class Screen(Skill):
    name = "screen"

    def handle(self, text: str, ctx: Context) -> str | None:
        if not _ABOUT_SCREEN.search(text):
            return None
        # Without an AI this is as far as we get; with one, the AI takes over.
        return Fallback(ctx.reply("看屏幕需要先在 AI 连接里选一个能看图的 AI。",
                                  "To look at your screen, connect an AI that can see images first."))

    def tools(self) -> list[Tool]:
        return [Tool(
            "look_at_screen",
            "Take a screenshot of the screen the user is looking at (the monitor with the "
            "active window) so you can see it. Use it whenever the user refers to what's on "
            "screen.",
            schema(),
            self._look,
        )]

    def _look(self, args: dict, ctx: Context) -> ToolImage:
        from .. import screen

        data, title = screen.capture()
        return ToolImage(f"Screenshot of the user's screen. Active window: {title or 'unknown'}.", data)
