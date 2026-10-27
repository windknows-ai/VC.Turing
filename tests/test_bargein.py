"""Barge-in: Turing's own echo must not count as the user; the user talking over it must."""

import wave

import numpy as np
import pytest

from turing import models
from turing.audio import CHUNK

WAVS = models.KWS.path / "test_wavs"
pytestmark = pytest.mark.skipif(not (WAVS / "zh_0.wav").exists(), reason="speech models not downloaded")


def load(name: str) -> np.ndarray:
    with wave.open(str(WAVS / name)) as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def run(mic: np.ndarray, played: np.ndarray) -> int | None:
    """Feed 100 ms chunks; return the chunk index where an interruption is detected."""
    from turing.bargein import BargeIn, rms

    detector = BargeIn()
    for i in range(min(len(mic), len(played)) // CHUNK):
        window = played[max(0, (i - 2) * CHUNK):(i + 1) * CHUNK]
        if detector.feed(mic[i * CHUNK:(i + 1) * CHUNK], rms(window), i * CHUNK / 16000):
            return i
    return None


def turing_voice(seconds: float) -> np.ndarray:
    voice = np.concatenate([load("zh_0.wav"), load("zh_1.wav"), load("zh_2.wav")])
    return np.resize(voice, int(seconds * 16000))


def test_own_echo_does_not_interrupt():
    played = turing_voice(6)
    echo = 0.3 * played + 0.002 * np.random.default_rng(0).standard_normal(len(played))
    assert run(echo.astype(np.float32), played) is None


def test_user_talking_over_turing_interrupts():
    played = turing_voice(6)
    mic = 0.3 * played
    user = load("zh_3.wav")
    start = int(2.5 * 16000)
    mic[start:start + len(user)] += 1.2 * user[: len(mic) - start]
    hit = run(mic.astype(np.float32), played)
    assert hit is not None and hit * CHUNK >= start - CHUNK


def test_headphones_any_speech_interrupts():
    played = turing_voice(6)
    mic = np.zeros_like(played)  # no echo at all
    user = load("zh_3.wav")
    start = int(2 * 16000)
    mic[start:start + len(user)] += 0.5 * user[: len(mic) - start]
    assert run(mic, played) is not None


def test_user_cutting_in_at_the_very_start_still_interrupts():
    """Talking while Turing's echo is first measured mustn't hide the user from then on."""
    played = turing_voice(6)
    mic = 0.3 * played
    user = np.resize(load("zh_3.wav"), 4 * 16000)  # starts 0.2 s in and keeps talking
    start = int(0.2 * 16000)
    mic[start:start + len(user)] += 1.2 * user[: len(mic) - start]
    assert run(mic.astype(np.float32), played) is not None


def test_quiet_user_is_heard():
    """About half the old fixed floor (0.01): the user's real speech is often around there."""
    played = turing_voice(6)
    mic = 0.05 * played
    user = load("zh_3.wav")
    user = user * (0.012 / np.sqrt(np.mean(user[np.abs(user) > 0.01] ** 2)))
    start = int(2.5 * 16000)
    mic[start:start + len(user)] += user[: len(mic) - start]
    assert run(mic.astype(np.float32), played) is not None


def test_interrupting_while_turing_thinks():
    """Nothing plays yet: any clear speech counts."""
    from turing.bargein import BargeIn

    user = load("zh_3.wav")
    detector = BargeIn()
    hits = [detector.feed(user[i * CHUNK:(i + 1) * CHUNK], 0.0) for i in range(len(user) // CHUNK)]
    assert any(hits)
