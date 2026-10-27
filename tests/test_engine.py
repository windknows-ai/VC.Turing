"""Start / pause / start again from the app, without a microphone or speech models."""

import threading
import time

from turing import app, engine


class SlowStopAssistant:
    """Stands in for app.Assistant: runs until stopped, then takes a while to wind down."""

    def __init__(self, cfg, source=None):
        pass

    def run(self, stop):
        app.emit("state", "waiting")
        stop.wait()
        time.sleep(1.0)  # e.g. still finishing a command when paused


def make_engine(monkeypatch):
    monkeypatch.setattr(engine.models, "ensure", lambda **kw: None)
    monkeypatch.setattr(engine, "Microphone", lambda device=None, notify=None: object())
    monkeypatch.setattr(engine.app, "Assistant", SlowStopAssistant)
    return engine.Engine()


def wait_for(e, state, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if e.state == state:
            return True
        time.sleep(0.02)
    return False


def test_start_right_after_pause_still_starts(monkeypatch):
    e = make_engine(monkeypatch)
    e.start()
    assert wait_for(e, "waiting")
    # Pause, then press start again while the old run is still winding down.
    e._stop.set()
    threading.Thread(target=e.start).start()
    time.sleep(1.5)
    assert wait_for(e, "waiting"), e.state
    e.stop()


def test_start_twice_runs_once(monkeypatch):
    e = make_engine(monkeypatch)
    e.start()
    first = e._thread
    e.start()
    assert e._thread is first
    e.stop()


def test_live_words_are_shown_but_not_logged(monkeypatch):
    e = make_engine(monkeypatch)
    try:
        app.emit("state", "listening")
        for words in ("帮我", "帮我打开", "帮我打开微信"):
            app.emit("partial", words)
        status = e.status()
        assert status["partial"] == "帮我打开微信"
        assert not [ev for ev in status["events"] if ev["kind"] == "partial"]
        app.emit("you", "你 / You: 帮我打开微信")
        assert e.status()["partial"] == ""
        app.emit("partial", "再")
        app.emit("state", "waiting")
        assert e.status()["partial"] == ""
    finally:
        app.LISTENERS.remove(e._on_event)
