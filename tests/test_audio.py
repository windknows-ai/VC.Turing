"""The microphone recovers by itself from unplugged devices, default-device changes and
sleep, and never piles up audio nobody reads."""

import types

import numpy as np
import pytest

from turing import audio


class FakeStream:
    opened = []

    def __init__(self, device=None, callback=None, **kw):
        self.device, self.callback = device, callback
        self.running = False
        FakeStream.opened.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def close(self):
        pass

    def feed(self, n=1):
        for _ in range(n):
            self.callback(np.full((audio.CHUNK, 1), 0.01, np.float32), audio.CHUNK, None, None)


@pytest.fixture
def mic(monkeypatch):
    FakeStream.opened = []
    calls = types.SimpleNamespace(restarts=0, output_active=False)
    devices = [{"name": "USB Mic", "max_input_channels": 1}, {"name": "Speakers", "max_input_channels": 0}]

    def restart():
        calls.restarts += 1

    fake_sd = types.SimpleNamespace(
        InputStream=FakeStream,
        _terminate=restart,
        _initialize=lambda: None,
        query_devices=lambda i=None: devices if i is None else devices[i],
        get_stream=lambda: types.SimpleNamespace(active=calls.output_active),
    )
    monkeypatch.setattr(audio, "sd", fake_sd)
    defaults = {"value": ("mic-a", "spk-a")}
    monkeypatch.setattr(audio, "_default_endpoints", lambda: defaults["value"])
    asleep = {"value": 0.0}
    monkeypatch.setattr(audio, "_asleep_seconds", lambda: asleep["value"])
    notes = []
    m = audio.Microphone(notify=notes.append)
    m.start()
    return types.SimpleNamespace(mic=m, calls=calls, defaults=defaults, asleep=asleep,
                                 notes=notes, devices=devices)


def test_queue_is_bounded(mic):
    FakeStream.opened[-1].feed(audio.Microphone.MAX_QUEUED + 50)
    assert mic.mic._q.qsize() == audio.Microphone.MAX_QUEUED


def test_dead_stream_is_reopened(mic):
    mic.mic._last_audio -= 10  # no audio for 10 s
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 1 and mic.calls.restarts == 1
    assert len(FakeStream.opened) == 2 and FakeStream.opened[-1].running
    assert mic.notes


def test_new_default_device_is_picked_up(mic):
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 0
    mic.defaults["value"] = ("mic-b", "spk-a")  # headset plugged in
    mic.mic._next_check = 0
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 1


def test_sleep_and_resume_reopens(mic):
    mic.asleep["value"] = 3600  # an hour asleep since the last read
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 1


def test_waits_while_turing_is_talking(mic):
    mic.calls.output_active = True
    mic.mic._last_audio -= 10
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 0  # would cut Turing off mid-sentence
    mic.calls.output_active = False
    mic.mic.read(timeout=0.01)
    assert mic.mic.reopened == 1


def test_chosen_mic_is_found_again_by_name(monkeypatch, mic):
    m = audio.Microphone(device=0, notify=mic.notes.append)
    m.start()
    mic.devices.insert(0, {"name": "Bluetooth Headset", "max_input_channels": 1})  # indexes shift
    m._last_audio -= 10
    m.read(timeout=0.01)
    assert FakeStream.opened[-1].device == 1
