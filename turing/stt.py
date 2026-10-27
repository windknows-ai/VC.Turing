"""Local speech-to-text: Silero VAD finds where you start and stop talking,
SenseVoice transcribes it (Chinese, English, or both mixed)."""

import gc
import re
import threading
import time
import wave

import numpy as np
import sherpa_onnx
from pypinyin import lazy_pinyin

from . import models
from .audio import SAMPLE_RATE

VAD_WINDOW = 512
PRE_ROLL = int(0.3 * SAMPLE_RATE)

_PUNCT = re.compile(r"[，。！？、,.!?;；:：\"“”'‘’…~]")
# Drop spaces between Chinese characters but keep them between English words.
_CJK_SPACE = re.compile(r"(?<=[一-鿿])\s+|\s+(?=[一-鿿])")
# The wake word leaks into a command said in one breath ("嗨图灵打开微信"), often
# misheard ("海图林", "嗨徒灵", "Hey Touring"), so it's matched by sound, not spelling.
# "turing", "touring", "during", "toing", "tooring"... and a bare leftover "hey".
_WAKE_EN = re.compile(
    r"^(?:(?:hey|hi|hay|eh)\b[\s,]*)?(?:(?:t|d|th)[aeiou]{1,3}r?ing|ring)?\b[\s,]*", re.I)
_TU = {"tu", "du", "tou", "tuo"}
_LING = {"ling", "lin", "lian"}  # 图灵 heard as 图林 / 图联


_DICTATION = re.compile(r"发|告诉|回复|回他|回她|说一声|转告|send|tell|reply|text")

# Product names speech recognition spells out or hears as Chinese.
_NAMES = [(re.compile(r"(?:叉|插|查|茶|差|恰|chat|i)\s*g\s*p\s*t", re.I), "ChatGPT")]


def clean(text: str) -> str:
    text = _PUNCT.sub(" ", text)
    text = _CJK_SPACE.sub("", text)
    for pattern, name in _NAMES:
        text = pattern.sub(name, text)
    return " ".join(text.split())


def strip_wake(text: str) -> str:
    """Drop a leading "(嗨)图灵" / "Hey Turing" and anything before it."""
    text = text.strip()
    m = _WAKE_EN.match(text)
    if m and m.group(0).strip():
        return text[m.end():].strip()
    head = [lazy_pinyin(c)[0] for c in text[:6]]
    for i, sound in enumerate(head):
        if sound in _LING and ((i > 0 and head[i - 1] in _TU) or (i == 0 and text[0] in "灵林铃玲凌")):
            return text[i + 1:].strip()
    return text


def _sensevoice(threads: int, hotwords: str):
    d = models.ASR.path
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(d / "model.int8.onnx"), tokens=str(d / "tokens.txt"),
        use_itn=True,  # "音量调到三十" -> "音量调到30"
        num_threads=threads)


def _qwen3(threads: int, hotwords: str):
    d = models.QWEN3_ASR.path
    if not models.installed(models.QWEN3_ASR):
        raise FileNotFoundError("Qwen3-ASR is not downloaded")
    return sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
        conv_frontend=str(d / "conv_frontend.onnx"), encoder=str(d / "encoder.int8.onnx"),
        decoder=str(d / "decoder.int8.onnx"), tokenizer=str(d / "tokenizer"),
        num_threads=threads, hotwords=hotwords)


# name -> (builder, description shown in the app)
RECOGNIZERS = {
    "sensevoice": (_sensevoice, "SenseVoice：快，适合只说一种语言"),
    "qwen3": (_qwen3, "Qwen3-ASR：更准，中英混说和口音都好，稍慢"),
}


def make_recognizer(name: str, threads: int = 4, hotwords: str = ""):
    """A function samples -> text for the named recognizer."""
    build, _ = RECOGNIZERS.get(name, RECOGNIZERS["sensevoice"])
    asr = build(threads, hotwords)

    def recognize(samples: np.ndarray) -> str:
        # Quiet microphones transcribe worse; bring speech up to a steady level.
        peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
        if 0.005 < peak < 0.5:
            samples = samples * (0.5 / peak)
        stream = asr.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        asr.decode_stream(stream)
        return clean(stream.result.text)

    return recognize


_LATIN = re.compile(r"[A-Za-z]{2,}")
# Words Qwen3-ASR should favour: the wake word, words said to confirm, and app names
# people say a lot. Users can add their own ([listen] hotwords).
DEFAULT_HOTWORDS = ["图灵", "Turing", "ChatGPT", "发送", "取消", "微信", "QQ音乐", "网易云音乐", "抖音",
                    "Discord", "Chrome", "Spotify", "Steam", "Oakville"]
KEEP_RECORDINGS = 30


def save_recording(samples: np.ndarray, text: str):
    """Keep a command's audio and what was heard, for diagnosing recognition (local only)."""
    from .paths import DATA_DIR

    folder = DATA_DIR / "recordings"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with wave.open(str(folder / f"{stamp}.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    (folder / f"{stamp}.txt").write_text(text, encoding="utf-8")
    old = sorted(folder.glob("*.wav"))[:-KEEP_RECORDINGS]
    for wav in old:
        wav.unlink(missing_ok=True)
        wav.with_suffix(".txt").unlink(missing_ok=True)


# Words after which people usually keep talking: a pause here isn't the end.
_CONTINUES = re.compile(
    r"(然后|和|还有|就是|那个|这个|嗯|呃|的|把|给|跟|在|是|再|并且|而且|或者|帮我|我想|"
    r"\band|\bthen|\bthe|\bto|\ba|\bum|\buh|\bor|\bwith|\bfor|\bof)$", re.I)
VAD_MIN_SILENCE = 0.3   # the detector ends a stretch of speech after this much quiet;
                        # stretches are then joined into one command (see listen)


LOW_MEMORY_GB = 3.0


def memory_to_spare() -> bool:
    """Is there room to load Qwen3-ASR (1-2 GB)? When the PC is nearly out of memory, loading
    it would make everything crawl, so the fast recognizer is used instead."""
    import psutil

    return psutil.virtual_memory().available / 2**30 >= LOW_MEMORY_GB


class OnDemand:
    """A recognizer that's only in memory while it's being used.

    Qwen3-ASR takes 1-2.2 GB of RAM (growing with the longest sentence heard) and 3-4 s
    to load. It's loaded in the background when Turing is woken (`warm`), which usually
    finishes while the user is talking, and dropped again after `idle_seconds` unused.
    """

    def __init__(self, build, idle_seconds: float = 300):
        self._build = build
        self._idle = idle_seconds
        self._fn = None
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._timer: threading.Timer | None = None

    @property
    def loaded(self) -> bool:
        return self._fn is not None

    def warm(self):
        if self._fn is None:
            threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        with self._lock:
            if self._fn is None:
                self._fn = self._build()
        self._last_used = time.monotonic()
        self._schedule_unload()

    def __call__(self, samples: np.ndarray) -> str:
        self._load()
        return self._fn(samples)

    def _schedule_unload(self):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self._idle, self._unload_if_idle)
        self._timer.daemon = True
        self._timer.start()

    def _unload_if_idle(self):
        if time.monotonic() - self._last_used >= self._idle - 1:
            with self._lock:
                self._fn = None
            gc.collect()

    def close(self):
        """Drop the model now (a pending unload timer would otherwise keep it alive)."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        with self._lock:
            self._fn = None


class Transcriber:
    """Speech to text, with the recognizer chosen by `asr` in [listen]:

    - "auto" (default): SenseVoice first (0.1 s); if it heard any English, Qwen3-ASR
      re-does it (about 0.7 s more) since it's far better with English and with
      Chinese and English mixed. Plain Chinese stays fast.
    - "sensevoice" / "qwen3": always that one.
    """

    def __init__(self, cfg: dict, hotwords: str = ""):
        self._cfg = cfg
        self.mode = cfg.get("asr", "auto")
        self._fast = make_recognizer("sensevoice")
        self._accurate = None
        self.last_seconds = 0.0  # how long the last transcription took
        self._keep = bool(cfg.get("keep_recordings", True))
        if self.mode in ("auto", "qwen3") and models.installed(models.QWEN3_ASR):
            words = ",".join(DEFAULT_HOTWORDS + [w for w in cfg.get("hotwords", []) if w])
            self._accurate = OnDemand(lambda: make_recognizer("qwen3", hotwords=hotwords or words))
        vad_cfg = sherpa_onnx.VadModelConfig()
        vad_cfg.silero_vad.model = str(models.VAD.path)
        vad_cfg.silero_vad.min_silence_duration = VAD_MIN_SILENCE
        vad_cfg.silero_vad.min_speech_duration = 0.15
        vad_cfg.silero_vad.max_speech_duration = float(cfg["max_command_seconds"])
        vad_cfg.silero_vad.window_size = VAD_WINDOW
        vad_cfg.sample_rate = SAMPLE_RATE
        self._vad = sherpa_onnx.VoiceActivityDetector(vad_cfg, buffer_size_in_seconds=30)

    def close(self):
        """Let go of the models when the listener stops, rather than when the GC gets to it."""
        if self._accurate is not None:
            self._accurate.close()
        self._accurate = None

    # --- recognition -----------------------------------------------------------

    def warm_up(self):
        """Turing was woken: start loading the accurate recognizer if it'll be needed."""
        if self._accurate is not None and (self._accurate.loaded or memory_to_spare()):
            self._accurate.warm()

    def _recognize(self, samples: np.ndarray) -> str:
        if self.mode == "qwen3" and self._accurate:
            return self._accurate(samples)
        text = self._fast(samples)
        # English, or a message to someone (its exact words matter more than 1 s): the
        # fast recognizer often turns English inside Chinese into Chinese ("不要语").
        if self.mode == "auto" and self._accurate and (_LATIN.search(text) or _DICTATION.search(text)) \
                and (self._accurate.loaded or memory_to_spare()):
            return self._accurate(samples)
        return text

    def transcribe(self, samples: np.ndarray) -> str:
        started = time.perf_counter()
        text = self._recognize(samples)
        self.last_seconds = time.perf_counter() - started
        if self._keep and text and len(samples) > SAMPLE_RATE // 2:
            try:
                save_recording(samples, text)
            except OSError:
                pass
        return text

    def quick(self, samples: np.ndarray) -> str:
        """Fast rough text, for showing words live while someone is still talking."""
        return self._fast(samples) if len(samples) else ""

    # --- listening -------------------------------------------------------------

    def _start(self, preroll: np.ndarray | None):
        self._vad.reset()
        pre = preroll if preroll is not None else np.zeros(0, dtype=np.float32)
        # The pre-roll (audio from just before listening began, e.g. the end of the
        # wake word) is kept for cutting the command out, but not fed to the VAD, so
        # the wake word's tail isn't taken as the start of a command.
        self._chunks = [pre]
        self._total = len(pre)
        self._offset = len(pre)
        self._buf = np.zeros(0, dtype=np.float32)

    def _audio(self, start: int, end: int) -> np.ndarray:
        return np.concatenate(self._chunks)[max(0, start):end]

    def end_pause(self, partial: str, spoken_seconds: float) -> float:
        """How long a pause must last before the command counts as finished.

        The base comes from settings ([listen] end_silence_seconds). It's longer when
        the words so far trail off mid-thought ("打开微信然后", "and the") or when only
        a word or two has been said, so a natural pause doesn't cut the sentence.
        """
        pause = float(self._cfg["end_silence_seconds"])
        if _CONTINUES.search(partial.strip()):
            pause += 1.2  # people often stop for a second or more after "然后…"
        elif spoken_seconds < 0.8:
            pause += 0.4
        return pause

    def listen(self, source, preroll=None, prompt=None, prompt_after: float = 0.6,
               stop=None, on_partial=None, wait: float | None = None) -> str | None:
        """Record one command from `source` and return its text.

        `preroll`: audio from right before listening began, so a command said in the
        same breath as the wake word keeps its first syllables. If nobody speaks for
        `prompt_after` seconds, `prompt()` is called once (e.g. to say "我在").
        `on_partial(text)` gets the words so far while the user is talking.
        Returns None if nobody spoke within `wait` (default: [listen] wait_seconds).
        """
        self._start(preroll)
        wait = float(self._cfg["wait_seconds"] if wait is None else wait)
        longest = float(self._cfg["max_command_seconds"]) * SAMPLE_RATE
        quiet_since = time.monotonic()
        give_up = quiet_since + wait
        prompted = prompt is None
        utt_start = utt_end = None      # the command so far, in sample positions
        finish_at = None                # end it then, unless speech resumes
        speech_from = None              # where the stretch being spoken now began
        last_partial = 0.0
        while True:
            if stop is not None and stop.is_set():
                return None  # paused from the app
            chunk = source.read(timeout=0.05)
            finished = chunk is None and getattr(source, "finished", False)
            if chunk is not None:
                self._chunks.append(chunk)
                self._total += len(chunk)
                self._buf = np.concatenate([self._buf, chunk])
                while len(self._buf) >= VAD_WINDOW:
                    self._vad.accept_waveform(self._buf[:VAD_WINDOW])
                    self._buf = self._buf[VAD_WINDOW:]
            if finished:
                self._vad.flush()
            now = time.monotonic()
            talking = self._vad.is_speech_detected()
            if talking:
                finish_at = None
                if speech_from is None:
                    speech_from = max(0, self._total - int(0.4 * SAMPLE_RATE))

            # A stretch of speech just ended: add it to the command, and decide how
            # long to wait for more.
            while not self._vad.empty():
                front = self._vad.front
                start = self._offset + front.start
                end = start + len(front.samples)
                self._vad.pop()
                speech_from = None
                if utt_start is None:
                    utt_start = start
                utt_end = end
                partial = self.quick(self._audio(utt_start, utt_end))
                if not partial.strip() and utt_end - utt_start < SAMPLE_RATE:
                    # A cough or the wake word's tail, nothing more: keep waiting.
                    utt_start = utt_end = None
                    quiet_since, give_up = now, now + wait
                    continue
                if on_partial and partial:
                    on_partial(strip_wake(partial))
                spoken = (utt_end - utt_start) / SAMPLE_RATE
                finish_at = now + max(0.0, self.end_pause(partial, spoken) - VAD_MIN_SILENCE)

            # Show the words while they're being said.
            if talking and on_partial and now - last_partial > 0.6:
                last_partial = now
                begin = utt_start if utt_start is not None else speech_from
                if begin is not None and self._total - begin > SAMPLE_RATE // 2:
                    on_partial(strip_wake(self.quick(self._audio(begin, self._total))))

            too_long = utt_start is not None and self._total - utt_start > longest
            if utt_end is not None and ((finish_at and now >= finish_at and not talking)
                                        or finished or too_long):
                text = self._finish(utt_start, utt_end if not too_long else self._total)
                if text:
                    return text
                utt_start = utt_end = finish_at = None
                quiet_since, give_up = now, now + wait
            if finished:
                return None
            if not prompted and utt_start is None and not talking and now - quiet_since >= prompt_after:
                prompted = True
                prompt()
                self._start(None)
                quiet_since = time.monotonic()
                give_up = quiet_since + wait
                continue
            if utt_start is None and not talking and now > give_up:
                return None

    def _finish(self, start: int, end: int) -> str:
        """Final text of the command between `start` and `end`."""
        # The VAD notices speech a moment late, which clips the first syllable
        # ("今天" -> "请天"); cut with some lead-in. Speech that began right away also
        # gets the whole pre-roll, wake word tail included, which strip_wake removes.
        lead_from = 0 if start - self._offset < PRE_ROLL else start - PRE_ROLL
        text = self.transcribe(self._audio(lead_from, end))
        return strip_wake(text) if lead_from < self._offset else text