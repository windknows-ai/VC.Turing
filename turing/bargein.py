"""Notice the user talking over Turing ("barge-in"), so Turing can stop and listen.

The hard part is echo: with speakers, the microphone also hears Turing's own voice.
Turing knows what it's playing, so it measures how much of that comes back through the
mic (the echo coupling) once sound is actually coming out, and keeps measuring as it
speaks. It counts as the user when the mic is clearly louder than the echo should be
*and* the voice activity detector hears speech, in 2 of the last 3 tenths of a second.
Before any sound plays (Turing still thinking or fetching its voice) there is no echo,
so any clear speech above the room's own noise counts. With headphones there's no echo
either, and any speech counts.

Tested on this PC's real speaker echo mixed with the user's real recorded voice:
cutting in at the start or mid-sentence, at normal and 3x volume, 28-29 of 30 caught in
about 0.6 s, and Turing's own voice never mistaken for the user.
"""

import numpy as np
import sherpa_onnx

from . import models
from .audio import SAMPLE_RATE

VAD_WINDOW = 512
LEARN_SECONDS = 0.5     # how much of Turing's sound to hear before trusting the echo estimate
ECHO_MARGIN = 2.0       # the user must be this many times louder than the expected echo
SILENT = 0.005          # below this, nothing is playing (between sentences, or not started)
NEEDED, OUT_OF = 2, 3   # this many of the last few 100 ms chunks = an interruption


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


class BargeIn:
    def __init__(self):
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(models.VAD.path)
        cfg.silero_vad.threshold = 0.5
        cfg.silero_vad.min_speech_duration = 0.1
        cfg.silero_vad.window_size = VAD_WINDOW
        cfg.sample_rate = SAMPLE_RATE
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=10)
        self._buf = np.zeros(0, dtype=np.float32)
        self._ratios: list[float] = []   # mic / played while Turing's voice is coming out
        self._quiet: list[float] = []    # mic while nothing plays: the room's own noise
        self._heard = 0.0                # seconds of Turing's sound so far
        self._recent: list[bool] = []

    def feed(self, mic: np.ndarray, played_level: float, elapsed: float = 0.0) -> bool:
        """Feed one 100 ms mic chunk with the loudness of what was playing at that moment.
        Returns True once the user is clearly talking over Turing. (`elapsed` is no longer
        needed: learning starts when sound does.)"""
        level = rms(mic)
        self._buf = np.concatenate([self._buf, mic])
        while len(self._buf) >= VAD_WINDOW:
            self._vad.accept_waveform(self._buf[:VAD_WINDOW])
            self._buf = self._buf[VAD_WINDOW:]
        speech = self._vad.is_speech_detected()

        if played_level < SILENT:
            self._quiet = (self._quiet + [level])[-50:]
        else:
            self._heard += len(mic) / SAMPLE_RATE
            self._ratios = (self._ratios + [level / played_level])[-100:]
            if self._heard < LEARN_SECONDS:
                return False

        # Kept up to date all through the reply, so if the user talked over the first
        # moments (inflating it), it settles back as Turing goes on.
        coupling = float(np.median(self._ratios)) if self._ratios else 0.0
        noise = float(np.percentile(self._quiet, 20)) if self._quiet else 0.002
        floor = min(max(0.004, 2.5 * noise), 0.008)
        loud = level > max(floor, ECHO_MARGIN * coupling * played_level)
        self._recent = (self._recent + [speech and loud])[-OUT_OF:]
        return sum(self._recent) >= NEEDED
