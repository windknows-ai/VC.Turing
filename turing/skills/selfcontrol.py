"""Talking to Turing about Turing: what it can do, how it speaks (speed, voice, language),
pausing it, opening its settings, and which AI it uses."""

import re

from .. import config
from . import Context, Skill, Tool, notes, schema

VOICES = {"female": {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-JennyNeural"},
          "male": {"zh": "zh-CN-YunxiNeural", "en": "en-US-GuyNeural"}}

HELP_ZH = ("我能打开和关闭软件、切换窗口和桌面、调音量和亮度、放音乐和视频、在抖音 B站 YouTube 里搜索、"
           "查天气 汇率 股价 新闻、记笔记和待办、定提醒和闹钟、截图、找文件、发微信、写邮件草稿、"
           "看你的屏幕回答问题，接入 AI 后什么问题都可以问。说“图灵”叫醒我就行。")
HELP_EN = ("I can open and close apps, switch windows and desktops, change volume and brightness, play music "
           "and videos, search Douyin, bilibili and YouTube, check weather, exchange rates, stocks and news, "
           "keep notes, to-dos and reminders, take screenshots, find files, send WeChat messages, draft emails, "
           "and look at your screen. With an AI connected, ask me anything. Just say \"Hey Turing\".")

_HELP = re.compile(r"^(?:你)?(?:能|会|可以)(?:做|干|帮我做)?(?:什么|哪些)(?:事情?)?(?:呢)?$|^(?:有什么|有哪些)功能$|^帮助$|"
                   r"^what can you do\??$|^help$", re.I)
_SLOWER = re.compile(r"^(?:你)?(?:说话)?(?:说|讲)?(?:得)?慢(?:一)?点(?:说)?$|^语速(?:调)?慢(?:一)?点$|^(?:speak|talk) slower$", re.I)
_FASTER = re.compile(r"^(?:你)?(?:说话)?(?:说|讲)?(?:得)?快(?:一)?点(?:说)?$|^语速(?:调)?快(?:一)?点$|^(?:speak|talk) faster$", re.I)
_FEMALE = re.compile(r"^(?:换|切换|改)(?:成|到)?女(?:声|生|的声音)$|^用女声$|^(?:use|switch to) a female voice$", re.I)
_MALE = re.compile(r"^(?:换|切换|改)(?:成|到)?男(?:声|生|的声音)$|^用男声$|^(?:use|switch to) a male voice$", re.I)
_PAUSE = re.compile(r"^(?:暂停聆听|停止聆听|别听了|不要听了|你休息一下|休息吧|先别听)$|^stop listening$", re.I)
_SETTINGS = re.compile(r"^打开(?:图灵的?|你的)(?:设置|人设|ai连接|测试)(?:页面)?$|^open (?:turing'?s|your) settings$", re.I)
_ENGLISH = re.compile(r"^(?:以后)?(?:用|说)英(?:文|语)(?:回答我|跟我说|回复)?$|^(?:reply|answer|speak) (?:to me )?in english$", re.I)
_CHINESE = re.compile(r"^(?:以后)?(?:用|说)中文(?:回答我|跟我说|回复)?$|^(?:reply|answer|speak) (?:to me )?in chinese$", re.I)
_BOTH = re.compile(r"^(?:我说什么语言你就用什么语言|跟着我的语言回答)$|^(?:reply|answer) in my language$", re.I)
_WHICH_AI = re.compile(r"^你(?:是)?用(?:的)?(?:什么|哪个)(?:ai|模型|大模型)|^你(?:背后)?是(?:什么|哪个)(?:ai|模型)|"
                       r"^what (?:ai|model) (?:are you|do you use)", re.I)
_PAGES = {"设置": "settings", "人设": "persona", "ai连接": "ai", "测试": "test", "settings": "settings"}


def _rate(cfg: dict) -> int:
    m = re.match(r"([+-]?\d+)%", str(cfg.get("rate", "+0%")))
    return int(m.group(1)) if m else 0


class SelfControl(Skill):
    name = "selfcontrol"

    def handle(self, text: str, ctx: Context) -> str | None:
        if _HELP.match(text):
            return ctx.reply(HELP_ZH, HELP_EN)
        if _SLOWER.match(text):
            return self.speed(-15, ctx)
        if _FASTER.match(text):
            return self.speed(+15, ctx)
        if _FEMALE.match(text):
            return self.voice("female", ctx)
        if _MALE.match(text):
            return self.voice("male", ctx)
        if _PAUSE.match(text):
            ctx.state["stop_listening"] = True
            return ctx.reply("好的，我先不听了。要我继续，点一下屏幕角落的小圆球。",
                             "OK, I've stopped listening. Click the orb to bring me back.")
        if m := _SETTINGS.match(text):
            page = next((v for k, v in _PAGES.items() if k in text.lower()), "settings")
            from .. import app

            app.emit("open_page", page)
            return ctx.reply("已打开图灵的设置", "Opened Turing's settings")
        if _ENGLISH.match(text):
            return self.language("en", ctx)
        if _CHINESE.match(text):
            return self.language("zh", ctx)
        if _BOTH.match(text):
            return self.language("", ctx)
        if _WHICH_AI.match(text):
            ai = ctx.config.get("ai", {})
            if not ai.get("provider") or ai.get("provider") == "none":
                return ctx.reply("现在没有接入 AI，我只用本地指令。", "No AI is connected; I only use local commands.")
            return ctx.reply(f"我现在用的是 {ai['provider']} 的 {ai.get('model') or '默认模型'}。",
                             f"I'm using {ai['provider']}, model {ai.get('model') or 'default'}.")
        return None

    def speed(self, change: int, ctx: Context) -> str:
        voice = ctx.config.setdefault("voice", {})
        new = max(-50, min(60, _rate(voice) + change))
        voice["rate"] = f"{new:+d}%"  # in place: the speaker reads it for the next sentence
        config.save_section("voice", {"rate": voice["rate"]})
        slower = change < 0
        return ctx.reply("好的，我说慢一点" if slower else "好的，我说快一点", "OK, I'll speak slower" if slower else "OK, I'll speak faster")

    def voice(self, kind: str, ctx: Context) -> str:
        voice = ctx.config.setdefault("voice", {})
        if voice.get("engine") == "sapi":
            return ctx.reply("现在用的是离线声音，换声音要先在设置里改成在线声音。",
                             "The offline voice is in use; switch to the online voice in Settings first.")
        voice.update(VOICES[kind])
        config.save_section("voice", VOICES[kind])
        return ctx.reply("好的，换成女声了" if kind == "female" else "好的，换成男声了",
                         "OK, switched to a female voice" if kind == "female" else "OK, switched to a male voice")

    def language(self, lang: str, ctx: Context) -> str:
        notes.set_profile(reply_language=lang)
        if lang:
            ctx.zh = lang == "zh"
        return {"en": "OK, I'll answer in English from now on.", "zh": "好的，以后用中文回答你。",
                "": ctx.reply("好的，你说什么语言我就用什么语言回答。", "OK, I'll answer in whichever language you speak.")}[lang]

    def tools(self) -> list[Tool]:
        return [Tool("turing_voice", "Change how Turing speaks: speed (slower/faster) or voice (female/male).",
                     schema({"change": {"type": "string", "enum": ["slower", "faster", "female", "male"]}}, ["change"]),
                     lambda a, ctx: (self.speed(-15 if a["change"] == "slower" else 15, ctx)
                                     if a["change"] in ("slower", "faster") else self.voice(a["change"], ctx)))]
