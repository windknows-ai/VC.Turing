"""Control center logic that doesn't need a window."""

from turing.control_center import ollama
from turing.control_center.api import GROUPS
from turing.ai import PROVIDERS


def names(recs, flag):
    return [m["name"] for m in recs if m[flag]]


def test_recommend_for_8gb_laptop_with_32gb_ram():
    recs = ollama.recommend(vram_gb=8, ram_gb=32)
    assert names(recs, "best") == ["qwen3.5:35b-a3b"]
    assert "qwen3.5:27b" not in names(recs, "fits")
    assert "qwen3.5:9b" in names(recs, "fits")


def test_recommend_for_big_gpu():
    assert names(ollama.recommend(vram_gb=24, ram_gb=64), "best") == ["qwen3.5:27b"]


def test_recommend_without_gpu():
    recs = ollama.recommend(vram_gb=0, ram_gb=16)
    assert names(recs, "best") == ["qwen3.5:4b"]


def test_every_provider_has_a_group():
    assert set(PROVIDERS) == set(GROUPS)


def test_cloud_models_are_cloud_tags():
    assert all(m["name"].endswith((":cloud", "-cloud")) for m in ollama.CLOUD_MODELS)
    assert any(not m["paid"] for m in ollama.CLOUD_MODELS), "offer at least one free cloud model"


def test_closing_the_main_window_never_waits_for_its_page(monkeypatch):
    """Closing runs on the window thread; waiting there for the page deadlocks Turing."""
    import threading

    from turing.control_center import floating

    closing_thread = threading.current_thread()
    calls = []

    class FakeMain:
        def hide(self):
            pass

        def evaluate_js(self, script):
            calls.append(threading.current_thread() is closing_thread)

    monkeypatch.setattr(floating.config, "load", lambda: {"app": {"close_to_orb": True}})
    f = floating.Floating.__new__(floating.Floating)
    f.main, f._quitting, f.main_visible = FakeMain(), False, True
    assert f._on_main_closing() is False  # tucked away, not closed
    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.02)
    assert calls == [False]  # the page was told, but from another thread
    assert f.main_visible is False
