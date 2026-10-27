"""Skills are what Turing can do. Each skill looks at a command and either handles it
(returning what to say back) or returns None so the next skill gets a try.

Skills can also offer tools to the AI, so a command no rule matches ("太吵了",
"放点音乐然后调小声一点") can still be carried out.

To add a skill: subclass `Skill`, implement `handle` (and optionally `tools`),
and add it to `load_skills`.
"""

import re
from dataclasses import dataclass, field, replace
from typing import Callable

from ..tts import is_chinese

# Polite filler that doesn't change what the command means.
_FILLER = re.compile(
    r"^(请|麻烦你?|帮我|给我|帮忙|你能不能|你可以|你帮我|能不能|可以|图灵)+"
    r"|^(please |can you |could you |would you |hey turing |turing )+"
    r"|(一下|吧|呀|啊|呢|好吗|谢谢| please| thanks| thank you)+$"
)


def normalize(text: str) -> str:
    original = text = text.strip("﻿ \t\r\n").lower()
    prev = None
    while prev != text:
        prev, text = text, _FILLER.sub("", text).strip()
    # "谢谢" on its own is the whole command, not filler.
    return text or original


@dataclass
class Context:
    """What a skill gets to work with besides the command itself."""

    config: dict
    say: Callable[[str], None]  # speak something later, e.g. when a timer ends
    zh: bool = True
    state: dict = field(default_factory=dict)
    # Ask the user a yes/no question and wait for the answer. Anything that acts on the
    # user's behalf toward other people (sending a message) must get a yes first.
    # Without someone to ask, the answer is no.
    confirm: Callable[[str], bool] = lambda question: False
    # True once the user has interrupted this command; nothing more may be done for it.
    cancelled: Callable[[], bool] = lambda: False

    def reply(self, zh: str, en: str) -> str:
        return zh if self.zh else en


@dataclass
class ToolImage:
    """A tool result that includes a picture for the AI to look at (e.g. a screenshot)."""

    text: str
    data: bytes
    media_type: str = "image/jpeg"

    def __str__(self) -> str:
        return f"{self.text} [image, {len(self.data) // 1024} KB]"


@dataclass
class Tool:
    """An action the AI may call. `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict
    run: Callable[[dict, Context], str]


class Fallback(str):
    """A reply that means "a rule matched but couldn't do it". If an AI is set up,
    the command goes to the AI instead; otherwise this reply is spoken."""


def schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or []}


class Skill:
    name = "skill"

    def __init__(self, config: dict):
        self.config = config

    def handle(self, text: str, ctx: Context) -> str | None:
        raise NotImplementedError

    def tools(self) -> list[Tool]:
        return []


def load_skills(config: dict) -> list[Skill]:
    from .apps import Apps
    from .selfcontrol import SelfControl
    from .pcstatus import PCStatus
    from .notes import Notes
    from .everyday import Everyday
    from .editing import Editing
    from .calendar import Calendar
    from .clock import Clock
    from .desktops import Desktops
    from .device import Device
    from .files import Files
    from .info import Info
    from .keys import Keys
    from .media import Media
    from .messaging import Messaging
    from .screen import Screen
    from .system import System
    from .volume import Volume
    from .weather import Weather
    from .web import Chatbots, Web
    from .windows import Windows

    # Order matters: more specific skills first. Chatbots come first because the question
    # for ChatGPT can be about anything; System comes before Screen so "lock the screen"
    # locks it rather than looking at it.
    return [cls(config) for cls in
            (Chatbots, SelfControl, Media, Volume, Clock, Calendar, System, Device, PCStatus, Notes,
             Desktops, Windows, Editing, Messaging, Weather, Info, Screen, Files, Everyday, Web,
             Apps, Keys)]


NO_AI_REPLY = ("这个我还不会。运行设置接入 AI 之后，我就能理解更多说法了。",
               "I can't do that yet. Set up an AI provider and I'll understand much more.")


# A reply that says something was done.
_DID = (r"打开|切换|切到|关闭|关掉|发送|发|搜索|搜|创建|新建|设置|设|调|最小化|最大化|锁|播放|放|暂停|写|输入|打|"
        r"截|清空|删|移|按|刷新|完成|保存|存|选|复制|粘贴|翻译|提交|弄")
_CLAIM = re.compile(rf"(?:已经?|帮你|为你|为您|给你|替你).{{0,15}}?(?:{_DID})|(?:{_DID})(?:好了|好|完了|了)|好了|搞定|成功|"
                    r"\b(?:done|opened|switched|sent|closed|created|turned|minimi[sz]ed|maximi[sz]ed|"
                    r"took|saved|moved|typed|pressed|refreshed|wrote|written|entered)\b", re.I)
# ...unless it also says it didn't work.
_ADMITS = re.compile(r"没(?:能|有|成功)|未能|不能|无法|失败|不了|试着|尝试|couldn'?t|didn'?t|not able|"
                     r"unable|failed|tried", re.I)


def problems(tool_log: list) -> list[str]:
    """Tool results in this command that failed or couldn't be confirmed."""
    return [f"{name}: {result[:160]}" for name, result, is_error in tool_log
            if is_error or result.startswith("Error") or "UNVERIFIED" in result]


def honest(reply: str, tool_log: list, ctx: Context, brain) -> str:
    """Don't let the AI say it did something a tool says didn't happen (or can't confirm).

    Small models often write "已经帮你…了" after a failed or blind action. Then the AI is
    asked to say it again truthfully; if that still claims success, a plain admission
    is used instead.
    """
    trouble = problems(tool_log)
    if not trouble or not _CLAIM.search(reply) or _ADMITS.search(reply):
        return reply
    note = ("[Turing check] Your reply was: " + reply + "\nBut these actions failed or weren't "
            "confirmed:\n- " + "\n- ".join(trouble) + "\nTell the user again, truthfully and in one "
            "or two sentences in their language, what actually happened. Don't claim success. "
            "Don't call any tools.")
    try:
        fixed = brain.ask(note, replace(ctx, confirm=lambda q: False))
    except Exception:
        fixed = ""
    if fixed and not (_CLAIM.search(fixed) and not _ADMITS.search(fixed)):
        return fixed
    return ctx.reply("刚才的操作我没能确认成功，请看一下屏幕。",
                     "I couldn't confirm that worked. Please check the screen.")


def route(skills: list[Skill], raw_text: str, ctx: Context, brain=None) -> str:
    """Try the fast local rules first; hand anything else to the AI if there is one."""
    ctx.zh = is_chinese(raw_text)
    from .notes import profile

    if (lang := profile().get("reply_language")) in ("zh", "en"):
        ctx.zh = lang == "zh"
    ctx.state["command"] = raw_text  # some tools check what was actually asked
    ctx.state["tool_log"] = []
    text = normalize(raw_text)
    for skill in skills:
        reply = skill.handle(text, ctx)
        if isinstance(reply, Fallback) and brain is not None:
            break
        if reply is not None:
            return reply
    if brain is not None:
        reply = brain.ask(raw_text, ctx)
        return honest(reply, ctx.state.get("tool_log", []), ctx, brain)
    return ctx.reply(*NO_AI_REPLY)
