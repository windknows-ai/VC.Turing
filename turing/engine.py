"""Runs Turing in the background of the desktop app, and lets the app watch and test it."""

import collections
import itertools
import threading
import time

import numpy as np

from . import app, config, models
from .audio import SAMPLE_RATE, Microphone


class Engine:
    def __init__(self):
        self.state = "stopped"
        self.partial = ""  # words heard so far while the user is still talking
        self._events = collections.deque(maxlen=300)
        self._ids = itertools.count(1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._mic: Microphone | None = None
        self._assistant: app.Assistant | None = None
        self._typing_assistant: app.Assistant | None = None
        self.watchers: list = []  # UI parts that react to (kind, text) as it happens
        app.LISTENERS.append(self._on_event)

    # --- events ---------------------------------------------------------------

    def _on_event(self, kind: str, text: str):
        if kind == "state":
            self.state = text
            if text != "listening":
                self.partial = ""
        elif kind == "partial":
            self.partial = text  # changes several times a second: not worth a log entry
        else:
            if kind == "you":
                self.partial = ""
            self._events.append({"id": next(self._ids), "kind": kind, "text": text,
                                 "time": time.strftime("%H:%M")})
        for watcher in list(self.watchers):
            try:
                watcher(kind, text)
            except Exception:
                pass

    def level(self) -> float:
        """How loud things are right now, 0..1: Turing's voice while it speaks, else the mic."""
        if self.state == "stopped" or not self._mic:
            return 0.0
        assistant = self._assistant
        if self.state == "speaking" and assistant and assistant.speaker:
            return min(1.0, assistant.speaker.played_level() * 6)
        return self._mic.level

    def status(self, since: int = 0) -> dict:
        return {
            "state": self.state,
            "level": self.level(),
            "partial": self.partial,
            "events": [e for e in self._events if e["id"] > since],
        }

    # --- start / stop ---------------------------------------------------------

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        with self._lock:
            if self.running:
                if not self._stop.is_set():
                    return  # already listening
                # Still winding down from a pause: wait for it, or the new start is lost.
                self._thread.join(timeout=15)
                if self.running:
                    app.log("⚠️", "图灵还在停止中，请稍后再试。", kind="error")
                    return
            self._stop.clear()
            self.state = "loading"
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        try:
            cfg = config.load()
            models.ensure(mirror=cfg["models"]["mirror"])
            device = str(cfg["listen"]["device"]).strip()
            self._mic = Microphone(int(device) if device else None,
                                   notify=lambda m: app.log("🎤", m))
            self._assistant = app.Assistant(cfg, source=self._mic)
            if not self._stop.is_set():
                self._assistant.run(self._stop)
        except Exception as e:
            app.log("⚠️", f"图灵没能启动：{e}", kind="error")
            app.log_exception()
        finally:
            self._assistant = None
            self.state = "stopped"

    def stop(self):
        with self._lock:
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=5)

    def restart(self):
        if self.running:
            self.stop()
            self.start()

    # --- test panel -----------------------------------------------------------

    def type_command(self, text: str) -> str:
        """Run a typed command as if it had been spoken.

        Always uses a separate, microphone-less assistant: the listening one owns the mic,
        and a typed command is already explicit, so it needn't be confirmed by voice.
        """
        if self._typing_assistant is None:
            self._typing_assistant = app.Assistant(config.load())
        assistant = self._typing_assistant
        app.log("⌨️", f"你 / You: {text}", kind="you")
        reply = assistant.handle(text)
        assistant.say(reply)
        if self.running:
            self.state = "waiting"
        return reply

    def record_test(self, seconds: float = 4.0) -> dict:
        """Record from the microphone and show what speech recognition makes of it."""
        import sounddevice as sd

        from .stt import Transcriber

        cfg = config.load()
        device = str(cfg["listen"]["device"]).strip()
        audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1,
                       dtype="float32", device=int(device) if device else None)
        sd.wait()
        samples = audio[:, 0]
        listening = self._assistant._stt if self._assistant else None
        stt = listening or Transcriber(cfg["listen"])  # not kept: 250 MB+ for a rare test
        try:
            peak = float(np.max(np.abs(samples)))
            return {"text": stt.transcribe(samples), "peak": round(peak, 3)}
        finally:
            if stt is not listening:
                stt.close()

    def speak_test(self, text: str):
        from .tts import Speaker

        Speaker(config.load()["voice"]).say(text)


def microphones() -> list[dict]:
    """Input devices, listed once each (Windows lists every mic under several drivers)."""
    import sounddevice as sd

    default_in = sd.default.device[0]
    devices = sd.query_devices()
    host = devices[default_in]["hostapi"] if default_in is not None and default_in >= 0 else 0
    return [{"index": i, "name": d["name"], "default": i == default_in}
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0 and d["hostapi"] == host]
