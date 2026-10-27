"""The main loop: wait for the wake word, listen to one command, act, answer."""

import collections
import random
import re
from dataclasses import replace
import threading
import time
import traceback

import numpy as np
from pypinyin import lazy_pinyin

from . import ai, audio, config, personas
from .bargein import BargeIn
from .memory import Memory
from .paths import CONFIG_FILE, DATA_DIR
from .skills import Context, load_skills, route
from .stt import Transcriber
from .tts import Speaker, is_chinese
from .wakeword import WakeWord

# Audio kept from just before the wake word fires. Detection lags the end of the word,
# and a one-breath command ("嗨图灵打开微信") has already begun by then; the wake word
# itself is trimmed from the transcript afterwards.
PREROLL_CHUNKS = 10  # x 100 ms

# Anyone interested in what Turing is doing (the desktop app) registers here.
# Each listener gets (kind, text): kind is "state", "wake", "you", "turing" or "info".
LISTENERS: list = []


LOG_FILE = DATA_DIR / "turing.log"
_LOG_LIMIT = 1_000_000  # bytes; the log starts over when it gets bigger


def _write_log(line: str):
    """Keep a log on disk too: the desktop app has no console to print to."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if LOG_FILE.exists() and LOG_FILE.stat().st_size > _LOG_LIMIT else "a"
        with open(LOG_FILE, mode, encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log(icon: str, text: str, kind: str = "info"):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {icon} {text}"
    print(line[11:], flush=True)
    _write_log(line)
    emit(kind, text)


def log_exception():
    """Write the current exception's traceback to the log file."""
    _write_log(traceback.format_exc())


def emit(kind: str, text: str = ""):
    for listener in list(LISTENERS):
        try:
            listener(kind, text)
        except Exception:
            pass


class Assistant:
    def __init__(self, cfg: dict, source=None, speak: bool = True):
        self.cfg = cfg
        self.source = source
        self.speaker = Speaker(cfg["voice"]) if speak else None
        self.skills = load_skills(cfg)
        self.ctx = Context(config=cfg, say=self.say, confirm=self.confirm)
        self._stt = None  # set while listening to the microphone
        self._confirming = threading.Event()
        self._config_mtime = _mtime()
        self._persona_mtime = personas.mtime()
        self.memory = Memory()
        self.brain = None
        self._load_brain()
        if self.speaker:
            listen = cfg["listen"]
            threading.Thread(target=self.speaker.prepare,
                             args=(listen["prompt_zh"] + listen["prompt_en"],), daemon=True).start()

    def _load_brain(self):
        self.brain = ai.create_brain(self.cfg, [t for s in self.skills for t in s.tools()],
                                     memory=self.memory)
        if self.brain:
            log("🧠", f"AI: {self.cfg['ai']['provider']} / {self.brain.model}")
        else:
            log("🧠", "AI 未开启，只用本地指令 / AI off, local commands only")

    def reload_if_changed(self):
        """Pick up changes made in the settings window without a restart."""
        mtime, persona_mtime = _mtime(), personas.mtime()
        persona_changed = persona_mtime != self._persona_mtime
        if mtime == self._config_mtime and not persona_changed:
            return
        self._config_mtime, self._persona_mtime = mtime, persona_mtime
        new = config.load()
        ai_changed = new["ai"] != self.cfg["ai"]
        for section, values in new.items():
            # Update in place: skills and the recognizer hold references to these dicts,
            # so e.g. a new pause length or weather city applies to the next command.
            if isinstance(values, dict) and isinstance(self.cfg.get(section), dict):
                self.cfg[section].clear()
                self.cfg[section].update(values)
            else:
                self.cfg[section] = values
        if ai_changed or persona_changed:
            log("🔄", "AI 设置已更新 / AI settings changed")
            self._load_brain()

    def reply(self, text: str) -> np.ndarray | None:
        """Say a reply the user may talk over. If they do, Turing stops at once and this
        returns the audio of what they've said so far (to listen on from there)."""
        if not text.strip():
            return None
        if not (self.speaker and self.source and self.cfg["listen"].get("barge_in", True)):
            self.say(text)
            return None
        log("🤖", f"图灵 / Turing: {text}", kind="turing")
        emit("state", "speaking")
        detector = BargeIn()
        # The last 0.8 s, handed to the listener so the user's first words aren't lost.
        # Not more: further back it's mostly Turing's own voice.
        heard = collections.deque(maxlen=8)
        cut = threading.Event()
        started = time.monotonic()
        self.source.flush()
        talker = threading.Thread(target=self.speaker.say_interruptible,
                                  args=(spoken(text), cut.is_set), daemon=True)
        talker.start()
        while talker.is_alive():
            chunk = self.source.read(timeout=0.05)
            if chunk is None:
                continue
            heard.append(chunk)
            if detector.feed(chunk, self.speaker.played_level(), time.monotonic() - started):
                cut.set()
        talker.join()
        if not cut.is_set():
            self.source.flush()  # the tail of our own voice
            return None
        log("✋", "被打断，接着听 / Interrupted, listening")
        return np.concatenate(heard) if heard else None

    def say(self, text: str):
        log("🤖", f"图灵 / Turing: {text}", kind="turing")
        if self.speaker:
            emit("state", "speaking")
            with self._muted():
                self.speaker.say(spoken(text))

    def _muted(self):
        return self.source.muted() if self.source else _nullcontext()

    def chime(self, rising=True):
        if self.speaker:
            with self._muted():
                audio.play(audio.chime(rising))

    def acknowledge(self, wake_word: str):
        """The user said the name and paused: answer like Siri does."""
        listen = self.cfg["listen"]
        self.say(random.choice(listen["prompt_zh"] if is_chinese(wake_word) else listen["prompt_en"]))
        emit("state", "listening")

    @staticmethod
    def _partial(text: str):
        """Words heard so far, while the user is still talking (shown live in the app)."""
        if text:
            emit("partial", text)

    def confirm(self, question: str) -> bool:
        """Ask a yes/no question out loud and listen for the answer (no wake word needed)."""
        if self.source is None or self._stt is None:
            # Typed into the app's test page: the command itself was explicit.
            log("❔", f"{question}（打字指令，直接确认）")
            return True
        self._confirming.set()  # the question owns the microphone until answered
        try:
            return self._ask_yes_no(question)
        finally:
            self._confirming.clear()

    def _ask_yes_no(self, question: str) -> bool:
        for _ in range(2):
            self.say(question)
            emit("state", "listening")
            answer = self._stt.listen(self.source, on_partial=self._partial)
            if not answer:
                return False
            log("🗣️", f"你 / You: {answer}", kind="you")
            if fixed := correction(answer):
                # "不是，给他发 Where are you": not a no, but new wording to confirm.
                self.ctx.state["correction"] = fixed
                return False
            verdict = yes_or_no(answer)
            if verdict is not None:
                return verdict
            question = self.ctx.reply(f"没听清，你说的是“{answer}”。请说“发送”或者“取消”。",
                                      "Sorry, please say send or cancel.")
        return False

    def handle(self, text: str, cancel: threading.Event | None = None) -> str:
        """Run one text command through the skills and return the reply.

        `cancel` is set if the user talks over Turing while it works; from then on the
        command does nothing more (no tools, no confirmations).
        """
        self.reload_if_changed()
        emit("state", "thinking")
        ctx = self.ctx
        if cancel is not None:
            ctx = replace(self.ctx, cancelled=cancel.is_set,
                          confirm=lambda q: not cancel.is_set() and self.confirm(q))
        try:
            return route(self.skills, text, ctx, brain=self.brain)
        except Exception as e:
            log("⚠️", f"{type(e).__name__}: {e}")
            log_exception()
            return self.ctx.reply("出了点问题，没能完成。", "Something went wrong.")

    def think(self, text: str) -> tuple[str, np.ndarray | None]:
        """Work out the reply while still listening. Returns (reply, None), or ("", audio)
        if the user started talking first (they're changing or correcting the command)."""
        if not (self.source and self.cfg["listen"].get("barge_in", True)):
            return self.handle(text), None
        cancel = threading.Event()
        result = {}
        worker = threading.Thread(target=lambda: result.update(reply=self.handle(text, cancel)),
                                  daemon=True)
        detector = BargeIn()
        heard = collections.deque(maxlen=8)
        self.source.flush()
        worker.start()
        while worker.is_alive():
            if self._confirming.is_set():
                time.sleep(0.05)  # Turing is asking yes/no: that question owns the mic
                continue
            chunk = self.source.read(timeout=0.05)
            if chunk is None:
                continue
            heard.append(chunk)
            # Nothing is playing while thinking, so any clear speech is the user.
            if detector.feed(chunk, 0.0, elapsed=10.0):
                cancel.set()
                log("✋", "思考时被打断，接着听 / Interrupted while thinking")
                return "", np.concatenate(heard)
        return result.get("reply", ""), None

    def _converse(self, text: str, stt, stop: threading.Event):
        """Answer, then keep the conversation going without the wake word while it's
        natural to: the user talked over the answer, or Turing asked them something."""
        follow_up = float(self.cfg["listen"].get("follow_up_seconds", 8))
        while True:
            asr_seconds = stt.last_seconds
            started = time.monotonic()
            reply, interrupted = self.think(text)
            think_seconds = time.monotonic() - started
            if interrupted is None:
                interrupted = self.reply(reply)
                synth = self.speaker.last_synth_seconds if self.speaker else 0.0
                log("⏱", f"识别 {asr_seconds:.2f}s，思考 {think_seconds:.2f}s，"
                         f"合成语音 {synth:.2f}s / recognize, think, synthesize")
            if stop.is_set():
                return
            if interrupted is not None:
                emit("state", "listening")
                text = stt.listen(self.source, preroll=interrupted, stop=stop,
                                  on_partial=self._partial)
            elif is_question(reply) or follow_up > 0:
                # Keep the conversation open: a follow-up needs no wake word. After a
                # question, give the user a little longer to answer.
                emit("state", "listening")
                wait = max(follow_up, 6.0) if is_question(reply) else follow_up
                text = stt.listen(self.source, stop=stop, wait=wait, on_partial=self._partial)
            else:
                return
            if not text or stop.is_set():
                return
            log("🗣️", f"你 / You: {text}", kind="you")

    def run(self, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        emit("state", "loading")
        wake = WakeWord(self.cfg["wake"])
        stt = self._stt = Transcriber(self.cfg["listen"])
        recent = collections.deque(maxlen=PREROLL_CHUNKS)
        names = " / ".join(self.cfg["wake"]["keywords"])
        self.source.start()
        log("💤", f"等待唤醒 / Waiting for: {names}")
        emit("state", "waiting")
        try:
            while not stop.is_set():
                chunk = self.source.read(timeout=0.5)
                if chunk is None:
                    if getattr(self.source, "finished", False):
                        return
                    continue
                recent.append(chunk)
                heard = wake.feed(chunk)
                if not heard:
                    continue
                log("👂", f"听到「{heard}」/ Heard the wake word", kind="wake")
                emit("state", "listening")
                stt.warm_up()
                if self.brain:
                    # A local model loads while the user is still talking. It isn't loaded
                    # at startup, so it doesn't sit in graphics memory unused.
                    threading.Thread(target=self.brain.warm_up, daemon=True).start()
                try:
                    text = stt.listen(
                        self.source,
                        preroll=np.concatenate(recent),
                        prompt=lambda: self.acknowledge(heard),
                        prompt_after=float(self.cfg["listen"]["prompt_after_seconds"]),
                        stop=stop,
                        on_partial=self._partial,
                    )
                    if stop.is_set():
                        break
                    if not text:
                        log("💤", "没听到指令 / No command heard")
                        self.chime(rising=False)
                    else:
                        log("🗣️", f"你 / You: {text}", kind="you")
                        self._converse(text, stt, stop)
                        if self.ctx.state.pop("stop_listening", False):
                            stop.set()  # "暂停聆听": the orb's menu or a click brings Turing back
                except Exception as e:
                    # One bad command (a voice or sound device hiccup) mustn't stop listening.
                    log("⚠️", f"{type(e).__name__}: {e}", kind="error")
                    log_exception()
                wake.reset()
                recent.clear()
                self.source.flush()
                emit("state", "waiting")
        finally:
            self.source.stop()
            stt.close()
            self._stt = None
            emit("state", "stopped")


_NO = re.compile(r"不|别|算了|取消|先不|no\b|nope|cancel|don'?t|stop|wait", re.I)
_YES = re.compile(r"发|是|对|好|行|可以|确定|确认|嗯|没问题|yes|yeah|yep|sure|ok|okay|send|do it|go ahead",
                  re.I)


# Short answers are easy to mishear ("发" comes back as "花", "华" or "法"), so answers are
# also matched by sound. "No" sounds win: misreading a no as a yes would send a message.
_NO_SOUNDS = {"bu", "bie", "mei"}
_NO_PAIRS = {("qu", "xiao"), ("suan", "le"), ("deng", "deng")}
_YES_SOUNDS = {"fa", "hua", "shi", "dui", "hao", "xing", "en", "ng", "o"}
_YES_PAIRS = {("fa", "song"), ("que", "ding"), ("que", "ren"), ("ke", "yi")}


_CORRECTION = re.compile(
    r"^(?:不是|不对|没有|错了|不|no|nope)?[，,。.\s]*(?:是|应该是|我说的是|我是说|要)?\s*"
    r"(?:给(?:他|她|它|ta)|跟(?:他|她)|对(?:他|她))?\s*(?:发|说|写|回)\s*(?:的是)?[：:，,\s]*(.+)$"
    r"|^(?:不是|不对|错了)?[，,。.\s]*(?:我说的是|我是说|应该是)\s*[：:，,\s]*(.+)$"
    r"|^(?:no|nope)?[,.\s]*(?:send|say|tell (?:him|her|them))\s*[:,]?\s*(.+)$", re.I)
# What follows 发 when it is just "send it": 发送 / 发吧 / 发出去.
_JUST_SEND = re.compile(r"^(?:送|送吧|送了|吧|了|出去|过去|出去吧|吧好|it|it now)[。.!！]?$", re.I)


def correction(answer: str) -> str | None:
    """New wording in an answer to "send this?", e.g. "没有，给他发 Where are you"."""
    m = _CORRECTION.match(answer.strip())
    if not m:
        return None
    text = next(g for g in m.groups() if g).strip(" ，,。")
    if not text or _JUST_SEND.match(text) or yes_or_no(text) is not None and len(text) <= 3:
        return None
    return text


# A yes is the whole answer being yes words: "发送", "好的发吧", "嗯对", "ok send it". A sentence
# that merely contains 是 or 好 ("周四游泳是几点") is not a yes: it once sent a message.
_YES_FULL = re.compile(
    r"^(?:(?:嗯|恩|哦|好|好的|好啊|对|对的|是|是的|行|可以|确定|确认|发|发送|发吧|发出去|没问题|"
    r"ok|okay|yes|yeah|yep|sure|send(?: it)?|do it|go ahead)[，,\s]*)+(?:吧|啊|呀|了|呢|的)?$", re.I)
_FILLER_SOUNDS = {"song", "ba", "a", "ya", "la", "le", "de"}


def yes_or_no(answer: str) -> bool | None:
    """Read a spoken yes/no to "send this?". None (ask again) unless it's clear.

    "No" wins: "不发" contains "发", and a no misread as a yes would send a message.
    """
    a = re.sub(r"[。.!！?？~～\s]+$", "", answer.strip()).strip("，, ")
    if not a:
        return None
    if _NO.search(a):
        return False
    sounds = [s for s in lazy_pinyin(a, errors="ignore") if s]
    pairs = set(zip(sounds, sounds[1:]))
    short = len(a) <= 4 if is_chinese(a) else len(a.split()) <= 4
    if short and (_NO_SOUNDS & set(sounds) or _NO_PAIRS & pairs):
        return False
    if _YES_FULL.match(a):
        return True
    # Short answers misheard by sound ("花送" for "发送", "华" for "发").
    if short and is_chinese(a) and (_YES_SOUNDS & set(sounds) or _YES_PAIRS & pairs) \
            and set(sounds) <= _YES_SOUNDS | _FILLER_SOUNDS | {"que", "ding", "ren", "ke", "yi"}:
        return True
    return None


def is_question(reply: str) -> bool:
    return reply.rstrip().endswith(("?", "？", "吗", "呢"))


_SENTENCE_END = re.compile(r"(?<=[。！？!?])|(?<=\.)\s")


def spoken(text: str, zh_limit: int = 70, en_limit: int = 200) -> str:
    """The part of a reply worth reading aloud. Long answers are cut after a sentence or
    two; the full text is in the app's conversation log."""
    zh = is_chinese(text)
    limit = zh_limit if zh else en_limit
    if len(text) <= limit:
        return text
    out = ""
    for sentence in filter(None, (s.strip() for s in _SENTENCE_END.split(text))):
        if out and len(out) + len(sentence) > limit:
            break
        out += sentence if zh else (" " + sentence if out else sentence)
    return out + ("完整内容在图灵窗口里。" if zh else " The rest is in the Turing window.")


def _mtime() -> float:
    try:
        return CONFIG_FILE.stat().st_mtime
    except OSError:
        return 0.0


class _nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
