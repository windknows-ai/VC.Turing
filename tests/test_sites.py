"""Searching inside an app or site, and not typing into the wrong window."""

import time
import types

import pytest

from turing.skills import Context, keys, normalize, sites, web


@pytest.mark.parametrize("text, site, query", [
    ("打开抖音然后帮我搜索一下张大仙", "抖音", "张大仙"),
    ("抖音搜张大仙", "抖音", "张大仙"),
    ("在B站上搜一下原神", "B站", "原神"),
    ("去小红书找一下奥克维尔美食", "小红书", "奥克维尔美食"),
    ("Open YouTube and search for lofi music.", "YouTube", "lofi music"),
    ("search youtube for lofi", "YouTube", "lofi"),
    ("search for elden ring on steam", "Steam", "elden ring"),
])
def test_parse(text, site, query):
    found = sites.parse(normalize(text))
    assert found and (found[0].name, found[1]) == (site, query)


@pytest.mark.parametrize("text", ["打开抖音", "搜索张大仙", "打开记事本", "抖音"])
def test_not_a_site_search(text):
    assert sites.parse(normalize(text)) is None


def test_links():
    url, in_app = sites.link(sites.find_site("抖音"), "张大仙")
    assert url == "https://www.douyin.com/search/%E5%BC%A0%E5%A4%A7%E4%BB%99" and not in_app


def test_douyin_search_opens_results_and_says_where(monkeypatch):
    opened = []
    monkeypatch.setattr(web.webbrowser, "open", opened.append)
    reply = web.Web({}).handle(normalize("打开抖音然后帮我搜索一下张大仙"), Context(config={}, say=print))
    assert opened == ["https://www.douyin.com/search/%E5%BC%A0%E5%A4%A7%E4%BB%99"]
    assert "浏览器" in reply and "张大仙" in reply


def test_unknown_app_search_is_an_honest_error():
    out = web.Web({})._search_in("记事本", "hello", Context(config={}, say=print))
    assert out.startswith("Error") and "nothing was done" in out


def test_no_typing_into_another_window_after_opening_an_app(monkeypatch):
    import win32gui
    import win32process

    typed = []
    monkeypatch.setattr(keys.Keys, "__init__", lambda self, cfg=None: None)
    from turing import keyboard

    monkeypatch.setattr(keyboard, "type_text", typed.append)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda: 1)
    monkeypatch.setattr(win32gui, "GetWindowText", lambda h: "Claude")
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda h: (0, 999999))
    tool = next(t for t in keys.Keys().tools() if t.name == "type_text")
    ctx = Context(config={}, say=print)
    ctx.state["opened"] = {"name": "抖音", "exe": r"D:\douyin\douyin.exe", "at": time.monotonic()}
    out = tool.run({"text": "张大仙"}, ctx)
    assert out.startswith("Error") and "Claude" in out and typed == []
    ctx.state["opened"]["at"] -= 60  # long ago: typing into the front window is fine again
    assert not tool.run({"text": "hi"}, ctx).startswith("Error") and typed == ["hi"]
