"""System volume: set, up/down, mute/unmute, and "how loud is it"."""

import re

from ..numbers import NUMBER, parse_number
from . import Context, Skill, Tool, schema

_SET = re.compile(
    rf"^(把)?(音量|声音)(调到|调成|调整到|调整为|调整成|调节到|设为|设置为|设成|设置成|设置到|改成|改到|到|为)?(百分之)?{NUMBER}(%|的?音量)?$"
    rf"|^(set )?(the )?volume (to )?{NUMBER}( percent|%)?$"
)
_UP = re.compile(r"^(大声(一)?点|声音大(一)?点|(把)?(音量|声音)(调|开)?(大|高)(一)?点?|(调大|调高|增大|提高)(音量|声音)|"
                 r"音量加|louder|volume up|turn (it|the volume) up|turn up the volume)$")
_DOWN = re.compile(r"^(小声(一)?点|声音小(一)?点|(把)?(音量|声音)(调|关)?(小|低)(一)?点?|(调小|调低|减小|降低)(音量|声音)|"
                   r"音量减|quieter|softer|volume down|turn (it|the volume) down|turn down the volume)$")
_MUTE = re.compile(r"^(静音|关闭声音|把声音关了|mute( the sound)?)$")
_UNMUTE = re.compile(r"^(取消静音|打开声音|恢复声音|unmute)$")
_QUERY = re.compile(r"^((现在)?音量(是)?多(少|大)|what('s| is) the volume)$")

STEP = 10


def _endpoint():
    import comtypes
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()  # needed once per thread; the AI calls this from worker threads

    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> int:
    return round(_endpoint().GetMasterVolumeLevelScalar() * 100)


def set_volume(percent: int) -> int:
    percent = max(0, min(100, percent))
    ep = _endpoint()
    ep.SetMute(0, None)
    ep.SetMasterVolumeLevelScalar(percent / 100, None)
    return percent


class Volume(Skill):
    name = "volume"

    def handle(self, text: str, ctx: Context) -> str | None:
        if m := _SET.match(text):
            raw = next(g for g in (m.group(5), m.group(10)) if g)
            value = parse_number(raw)
            if value <= 1 and "." in raw:
                value *= 100
            v = set_volume(round(value))
        elif _UP.match(text):
            v = set_volume(get_volume() + STEP)
        elif _DOWN.match(text):
            v = set_volume(get_volume() - STEP)
        elif _MUTE.match(text):
            _endpoint().SetMute(1, None)
            return ctx.reply("已静音", "Muted")
        elif _UNMUTE.match(text):
            _endpoint().SetMute(0, None)
            return ctx.reply("已取消静音", "Unmuted")
        elif _QUERY.match(text):
            return ctx.reply(f"现在音量是 {get_volume()}", f"Volume is {get_volume()} percent")
        else:
            return None
        return ctx.reply(f"音量 {v}", f"Volume {v}")

    def tools(self) -> list[Tool]:
        return [Tool(
            "volume",
            "Read or change the system volume (0-100). Give `level` to set it, `change` to "
            "adjust it relatively (e.g. 10 or -10), or `mute`. With no arguments it just "
            "reports the current volume.",
            schema({
                "level": {"type": "integer", "minimum": 0, "maximum": 100},
                "change": {"type": "integer", "minimum": -100, "maximum": 100},
                "mute": {"type": "boolean"},
            }),
            self._tool,
        )]

    def _tool(self, args: dict, ctx: Context) -> str:
        if "mute" in args:
            _endpoint().SetMute(1 if args["mute"] else 0, None)
        if "level" in args:
            set_volume(int(args["level"]))
        elif "change" in args:
            set_volume(get_volume() + int(args["change"]))
        muted = bool(_endpoint().GetMute())
        return f"volume={get_volume()} muted={muted}"
