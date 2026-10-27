"""Text-to-speech: Microsoft Edge neural voices online, Windows SAPI offline fallback."""

import asyncio
import re
import threading
import time

import numpy as np
import sounddevice as sd

from .audio import play

RATE = 24000  # sample rate of the synthesized speech

_CJK = re.compile(r"[一-鿿]")


def is_chinese(text: str) -> bool:
    return bool(_CJK.search(text))


class Speaker:
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._lock = threading.Lock()
        self._sapi = None
        self._online = cfg["engine"] == "edge"
        self._cache: dict[str, np.ndarray] = {}
        self._playing: tuple[np.ndarray, float] | None = None
        self.last_synth_seconds = 0.0  # time spent waiting for the online voice

    def prepare(self, texts):
        """Synthesize phrases ahead of time (e.g. "我在") so they play instantly."""
        if not self._online:
            return
        for text in texts:
            try:
                self._cache[text] = self._edge(text)
            except Exception:
                return

    def _audio(self, text: str) -> np.ndarray | None:
        """Synthesized speech for `text`, or None when only the offline voice is available."""
        self.last_synth_seconds = 0.0
        if text in self._cache:
            return self._cache[text]
        if self._online:
            try:
                started = time.perf_counter()
                audio = self._edge(text)
                self.last_synth_seconds = time.perf_counter() - started
                return audio
            except Exception as e:  # offline, blocked, or service changed
                print(f"  (online voice unavailable, using offline voice: {e})")
                self._online = False
        return None

    def played_level(self) -> float:
        """Loudness of what was playing over the last quarter second (0 if silent)."""
        playing = self._playing
        if playing is None:
            return 0.0
        samples, started = playing
        pos = int((time.monotonic() - started) * RATE)
        window = samples[max(0, pos - RATE // 4):max(0, pos)]
        return float(np.sqrt(np.mean(np.square(window)))) if len(window) else 0.0

    def say_interruptible(self, text: str, should_stop) -> bool:
        """Speak `text`, stopping early as soon as `should_stop()` is true.
        Returns True if it was cut off. (The offline voice can't be cut off.)"""
        with self._lock:
            samples = self._audio(text)
            if samples is None:
                self._say_sapi(text)
                return False
            self._playing = (samples, time.monotonic())
            sd.play(samples, RATE)
            try:
                while sd.get_stream().active:
                    if should_stop():
                        sd.stop()
                        return True
                    time.sleep(0.03)
                return False
            finally:
                self._playing = None

    def say(self, text: str):
        """Speak `text` and block until done. Safe to call from any thread."""
        with self._lock:
            samples = self._audio(text)
            if samples is None:
                self._say_sapi(text)
            else:
                play(samples, RATE)

    def _edge(self, text: str) -> np.ndarray:
        import edge_tts
        import miniaudio

        voice = self._cfg["zh"] if is_chinese(text) else self._cfg["en"]

        async def fetch() -> bytes:
            comm = edge_tts.Communicate(text, voice, rate=self._cfg["rate"])
            audio = bytearray()
            async for part in comm.stream():
                if part["type"] == "audio":
                    audio += part["data"]
            return bytes(audio)

        mp3 = asyncio.run(fetch())
        decoded = miniaudio.decode(
            mp3, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1, sample_rate=24000
        )
        return np.frombuffer(decoded.samples, dtype=np.float32)

    def _say_sapi(self, text: str):
        import pyttsx3

        if self._sapi is None:
            self._sapi = pyttsx3.init()
        want_zh = is_chinese(text)
        for v in self._sapi.getProperty("voices"):
            name = (v.name or "") + " " + " ".join(map(str, v.languages or []))
            if want_zh == bool(re.search(r"Chinese|zh|Huihui|Kangkang|Yaoyao", name, re.I)):
                self._sapi.setProperty("voice", v.id)
                break
        self._sapi.say(text)
        self._sapi.runAndWait()
