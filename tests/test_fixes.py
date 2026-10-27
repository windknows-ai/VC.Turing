"""Asking ChatGPT, correcting a message while confirming it, and Chrome's profile picker."""

import json

import pytest

from turing import app, stt
from turing.skills import Context, browsers, messaging, normalize, sites, web


@pytest.mark.parametrize("text, bot, question", [
    ("帮我问一下ChatGPT我今天出门要准备什么", "ChatGPT", "我今天出门要准备什么"),
    ("浏览器用我现在这个界面使用ChatGPT问一下今天的天气怎么样", "ChatGPT", "今天的天气怎么样"),
    ("用claude问问怎么煮咖啡", "Claude", "怎么煮咖啡"),
    ("ChatGPT然后问一下他如果我今天出门需要准备什么", "ChatGPT", "如果我今天出门需要准备什么"),
    ("ask chatgpt what to wear today", "ChatGPT", "what to wear today"),
])
def test_ask_a_chatbot(text, bot, question):
    found = sites.parse_ask(normalize(text))
    assert found and (found[0].name, found[1]) == (bot, question)


def test_not_a_chatbot_question():
    assert sites.parse_ask(normalize("打开ChatGPT")) is None
    assert sites.parse_ask(normalize("问一下今天天气")) is None


def test_asking_opens_the_question_link(monkeypatch):
    opened = []
    monkeypatch.setattr(web.webbrowser, "open", opened.append)
    reply = web.Chatbots({}).handle(normalize("帮我问一下ChatGPT今天要带伞吗"), Context(config={}, say=print))
    assert opened == ["https://chatgpt.com/?q=%E4%BB%8A%E5%A4%A9%E8%A6%81%E5%B8%A6%E4%BC%9E%E5%90%97"]
    assert "ChatGPT" in reply


@pytest.mark.parametrize("heard", ["叉G P T", "I G P T", "chat g p t", "查GPT"])
def test_chatgpt_heard_right(heard):
    assert stt.clean(f"帮我问一下{heard}今天") == "帮我问一下ChatGPT今天"


@pytest.mark.parametrize("answer, fixed", [
    ("没有给他发Where are you", "Where are you"),
    ("不是，发 where are you", "where are you"),
    ("我说的是晚上一起吃饭", "晚上一起吃饭"),
    ("no, send where are you", "where are you"),
])
def test_correction(answer, fixed):
    assert app.correction(answer) == fixed


@pytest.mark.parametrize("answer, verdict", [("发送", True), ("发吧", True), ("不发", False),
                                             ("取消", False), ("好的", True)])
def test_plain_answers_are_not_corrections(answer, verdict):
    assert app.correction(answer) is None
    assert app.yes_or_no(answer) is verdict


def test_corrected_message_is_confirmed_again(monkeypatch):
    sent, asked = [], []
    answers = iter([("correction", "Where are you"), ("yes", None)])

    def confirm(question):
        asked.append(question)
        kind, value = next(answers)
        if kind == "correction":
            ctx.state["correction"] = value
            return False
        return True

    ctx = Context(config={}, say=print, confirm=confirm)
    monkeypatch.setattr(messaging, "send_wechat", lambda c, m: sent.append((c, m)))
    reply = messaging.Messaging({}).send("土豆", "不要语", ctx)
    assert sent == [("土豆", "Where are you")] and "土豆" in reply
    assert "Where are you" in asked[1]


def test_chrome_without_profile_opens_the_last_used(tmp_path):
    folder = tmp_path / "Google" / "Chrome" / "User Data"
    folder.mkdir(parents=True)
    cache = {"Default": {"name": "Your Chrome"}, "Profile 2": {"name": "Person 1"}}
    (folder / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Profile 2", "info_cache": cache}}), encoding="utf-8")
    assert browsers.last_used("chrome", str(tmp_path)).directory == "Profile 2"
    one = {"profile": {"last_used": "Default", "info_cache": {"Default": {"name": "Your Chrome"}}}}
    (folder / "Local State").write_text(json.dumps(one), encoding="utf-8")
    assert browsers.last_used("chrome", str(tmp_path)) is None  # no picker to skip


def test_ui_language(monkeypatch):
    import ctypes

    from turing import config

    assert config.ui_language({"app": {"language": "en"}}) == "en"
    assert config.ui_language({"app": {"language": "zh"}}) == "zh"
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", lambda: 0x0804)
    assert config.ui_language({"app": {"language": "auto"}}) == "zh"  # Chinese Windows
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", lambda: 0x1009)
    assert config.ui_language({"app": {}}) == "en"  # English (Canada)


class _Brain:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask(self, text, ctx):
        self.asked.append(text)
        return self.answer


def test_claimed_success_after_a_failed_action_is_corrected():
    from turing.skills import honest

    log = [("press_keys", "Error: nothing sent. 记事本 isn't in front yet", False)]
    ctx = Context(config={}, say=print)
    brain = _Brain("刚才没能按下按键，记事本还没出现在前面。")
    assert honest("已经帮你刷新了页面。", log, ctx, brain) == "刚才没能按下按键，记事本还没出现在前面。"
    assert "Error" in brain.asked[0]
    # If the AI insists, a plain admission is said instead.
    assert "没能确认" in honest("已经刷新好了。", log, ctx, _Brain("已经刷新好了。"))


def test_honest_replies_and_clean_runs_pass_untouched():
    from turing.skills import honest

    ctx = Context(config={}, say=print)
    bad = [("type_text", "typed into the window \"X\". UNVERIFIED: don't tell the user", False)]
    assert honest("我试着输入了，但没法确认，请看一下。", bad, ctx, None) == "我试着输入了，但没法确认，请看一下。"
    good = [("open_app", "正在打开记事本", False)]
    assert honest("已经打开记事本了。", good, ctx, None) == "已经打开记事本了。"


@pytest.mark.parametrize("reply", ["已经在记事本里为你写好“你好世界”了。", "我帮你把记事本打开并输入好了", "消息发送了",
                                   "Done, I wrote it in Notepad."])
def test_claims_with_words_in_between_are_caught(reply):
    from turing.skills import honest

    log = [("type_text", "Error: nothing sent. 记事本 isn't in front yet", False)]
    assert "没能确认" in honest(reply, log, Context(config={}, say=print), _Brain(reply)) or \
        "couldn't confirm" in honest(reply, log, Context(config={}, say=print), _Brain(reply)).lower()


def test_plain_answers_are_not_claims():
    from turing.skills import _CLAIM

    for reply in ("今天奥克维尔阴，8到17度。", "光速大约每秒30万公里。", "你叫小明。"):
        assert not _CLAIM.search(reply)


@pytest.mark.parametrize("answer, verdict", [
    ("发送", True), ("好的发吧", True), ("嗯对", True), ("对的", True), ("确定", True), ("花送", True), ("ok send it", True),
    ("不发", False), ("取消", False), ("算了吧", False), ("别发了", False), ("no", False),
    # Not answers: must never count as yes (this one once sent a message to Mom)
    ("周四游泳是今到几点", None), ("好像有人在叫我", None), ("这个是什么意思", None), ("what time is it", None),
])
def test_only_a_clear_yes_sends(answer, verdict):
    assert app.yes_or_no(answer) is verdict


def test_accurate_recognizer_not_loaded_when_memory_is_low(monkeypatch):
    """With the PC nearly out of memory, Qwen3-ASR (1-2 GB) mustn't be loaded on top."""
    import numpy as np

    loads = []
    t = stt.Transcriber.__new__(stt.Transcriber)
    t.mode = "auto"
    t._fast = lambda samples: "hello 图灵"
    t._accurate = type("Fake", (), {"loaded": False, "warm": lambda self: loads.append("warm"),
                                    "__call__": lambda self, s: loads.append("run") or "hello Turing"})()
    monkeypatch.setattr(stt, "memory_to_spare", lambda: False)
    assert t._recognize(np.zeros(16000, dtype=np.float32)) == "hello 图灵"
    t.warm_up()
    assert loads == []
    monkeypatch.setattr(stt, "memory_to_spare", lambda: True)
    assert t._recognize(np.zeros(16000, dtype=np.float32)) == "hello Turing"
