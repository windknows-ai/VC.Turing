"""Play / pause / next / previous / "what's playing" for whatever app is playing media
(QQ 音乐, 网易云, Spotify, browsers ...), through Windows' media session API."""

import asyncio
import ctypes
import re

from . import Context, Skill, Tool, schema

# What's being played or paused, said or not: "继续播放(刚才没放完的)音乐", "stop the music".
_WHAT_ZH = r"(一下)?(刚才|刚刚)?(没放完|没听完|没看完)?的?(音乐|歌|歌曲|视频)?"
_WHAT_EN = r"( the| my)?( music| song| video)?"

COMMANDS = {
    "play": rf"((继续|接着|开始)(播放|放)?|播放|放){_WHAT_ZH}|"
            rf"(play|resume|continue|keep playing|continue playing|start playing){_WHAT_EN}",
    "pause": rf"(暂停|停止|停)(播放)?{_WHAT_ZH}|停下|别放了|不听了|关掉(音乐|歌)|"
             rf"(pause|stop|stop playing){_WHAT_EN}",
    "next": r"(下一|换一)(首|曲|个)(歌)?|切歌|next( song| track)?|skip( this)?( song)?",
    "previous": r"上一(首|曲|个)(歌)?|previous( song| track)?|go back|last song",
    "now_playing": r"(这|现在|正在)(放|播|播放)?的?是(什么|哪)(首)?歌|这首歌叫什么|这是谁的歌|"
                   r"what('s| is) (this song|playing)|what song is this",
}
_PATTERNS = {k: re.compile(rf"^({v})$") for k, v in COMMANDS.items()}

# Fallback media keys, for when the session API isn't available.
_VK = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "previous": 0xB1}


def _press(vk: int):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


async def _session():
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return (await Manager.request_async()).get_current_session()


async def _run(action: str):
    """Returns (ok, info) where info is (title, artist) for now_playing."""
    session = await _session()
    if session is None:
        return False, None
    if action == "now_playing":
        props = await session.try_get_media_properties_async()
        return True, (props.title, props.artist)
    method = {
        "play": session.try_play_async,
        "pause": session.try_pause_async,
        "next": session.try_skip_next_async,
        "previous": session.try_skip_previous_async,
    }[action]
    return await method(), None


class Media(Skill):
    name = "media"

    def handle(self, text: str, ctx: Context) -> str | None:
        action = next((k for k, p in _PATTERNS.items() if p.match(text)), None)
        return None if action is None else self.do(action, ctx)

    def tools(self) -> list[Tool]:
        return [Tool(
            "media_control",
            "Control whatever music or video is playing on the PC (QQ Music, NetEase, Spotify, "
            "browser video...). now_playing returns the current song title and artist.",
            schema({"action": {"type": "string", "enum": list(COMMANDS)}}, ["action"]),
            lambda args, ctx: self.do(args["action"], ctx),
        )]

    def do(self, action: str, ctx: Context) -> str:
        if action not in COMMANDS:
            raise ValueError(f"unknown media action {action!r}")
        try:
            ok, info = asyncio.run(_run(action))
        except Exception:
            if action == "now_playing":
                return ctx.reply("我查不到现在在放什么。", "I can't tell what's playing.")
            _press(_VK[action])
            ok, info = True, None
        if not ok:
            return ctx.reply("现在没有在播放的媒体。", "Nothing is playing right now.")
        if action == "now_playing":
            title, artist = info
            if not title:
                return ctx.reply("我查不到歌名。", "I can't see the song name.")
            return ctx.reply(f"这是{artist}的《{title}》。" if artist else f"这是《{title}》。",
                             f"This is {title} by {artist}." if artist else f"This is {title}.")
        # Media actions speak for themselves; a short reply keeps it snappy.
        return ctx.reply(
            {"play": "好的", "pause": "已暂停", "next": "下一首", "previous": "上一首"}[action],
            {"play": "Playing", "pause": "Paused", "next": "Next", "previous": "Previous"}[action],
        )
