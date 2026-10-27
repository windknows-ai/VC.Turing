"""Tests must never press real keys or type on the user's PC (one once hid their WeChat)."""

import pytest


@pytest.fixture(autouse=True)
def no_real_keystrokes(monkeypatch):
    from turing import keyboard

    # The real ones stay reachable for tests that fake the Windows calls underneath.
    if not hasattr(keyboard, "real_type_text"):
        keyboard.real_type_text, keyboard.real_press = keyboard.type_text, keyboard.press

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to press real keys; monkeypatch keyboard.press / type_text")

    monkeypatch.setattr(keyboard, "press", refuse)
    monkeypatch.setattr(keyboard, "type_text", refuse)
