"""Sending messages: parsing, the yes/no confirmation, and never sending without a yes.
Nothing here touches the real keyboard or WeChat."""

import pytest

from turing.app import is_question, yes_or_no
from turing.keyboard import _vk
from turing.skills import Context, normalize
from turing.skills import messaging
from turing.skills.messaging import Messaging, parse


@pytest.mark.parametrize("text,expected", [
    ("给土豆发微信说你好", ("土豆", "你好")),
    ("给土豆发一条消息说今晚一起吃饭吗", ("土豆", "今晚一起吃饭吗")),
    ("用微信给妈妈发消息说我到家了", ("妈妈", "我到家了")),
    ("发微信给张三说明天见", ("张三", "明天见")),
    ("用微信告诉李四说会议改到三点", ("李四", "会议改到三点")),
    ("send a wechat message to Tom saying see you soon", ("Tom", "see you soon")),
])
def test_parse_message_commands(text, expected):
    # Commands arrive lower-cased; WeChat's search doesn't care about case.
    to, msg = parse(normalize(text))
    assert (to.lower(), msg.lower()) == (expected[0].lower(), expected[1].lower())


@pytest.mark.parametrize("text", ["跟我说个笑话", "给我说说今天的新闻", "打开微信", "现在几点了"])
def test_not_message_commands(text):
    assert parse(normalize(text)) is None


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(messaging, "send_wechat", lambda to, msg: calls.append((to, msg)))
    return calls


def ctx_answering(answer: bool, asked: list):
    return Context(config={}, say=print, confirm=lambda q: asked.append(q) or answer)


def test_sends_only_after_yes(sent):
    asked = []
    reply = Messaging({}).handle("给土豆发微信说你好", ctx_answering(True, asked))
    assert sent == [("土豆", "你好")]
    assert "土豆" in asked[0] and "你好" in asked[0]
    assert "已经发给土豆" in reply


def test_no_means_no(sent):
    reply = Messaging({}).handle("给土豆发微信说你好", ctx_answering(False, []))
    assert sent == []
    assert "不发" in reply


def test_default_context_never_sends(sent):
    # A Context nobody wired a confirm into answers "no".
    Messaging({}).handle("给土豆发微信说你好", Context(config={}, say=print))
    assert sent == []


def test_wechat_not_running(monkeypatch):
    def fail(to, msg):
        raise RuntimeError("WeChat is not running")

    monkeypatch.setattr(messaging, "send_wechat", fail)
    reply = Messaging({}).handle("给土豆发微信说你好", ctx_answering(True, []))
    assert "微信没有打开" in reply


@pytest.mark.parametrize("answer,expected", [
    ("发", True), ("发吧", True), ("好的", True), ("对", True), ("确定", True), ("yes", True),
    ("不发", False), ("不要", False), ("算了", False), ("取消", False), ("no", False),
    ("嗯不对", False), ("今天天气不错", False), ("什么", None),
    # Misheard "发": matched by sound.
    ("花", True), ("华", True), ("法", True), ("罚吧", True), ("发松", True), ("却定", True),
    # A misheard "不发" must still be a no.
    ("不花", False), ("步发", False), ("区小", False), ("没", False),
])
def test_yes_or_no(answer, expected):
    assert yes_or_no(answer) is expected


def test_is_question():
    assert is_question("你想用哪个软件来发呢")
    assert is_question("要给土豆发“你好”吗？")
    assert not is_question("已经发给土豆了。")


def test_key_names():
    assert _vk("enter") == 0x0D and _vk("Ctrl") == 0x11 and _vk("f") == ord("F") and _vk("f5") == 0x74
    with pytest.raises(ValueError):
        _vk("hyper")


def test_running_app_is_brought_forward_not_relaunched(monkeypatch):
    from turing import keyboard
    from turing.skills import apps

    wechat = apps.App("微信", r"D:\Program Files\Tencent\Weixin\Weixin.exe", "微信", "weixin")
    monkeypatch.setattr(keyboard, "window_of_exe", lambda exe, title=None: 42)
    import win32gui
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda hwnd: True)  # open, not in the tray
    monkeypatch.setattr(keyboard, "press", lambda keys: pytest.fail("no real key presses in tests"))
    focused = []
    monkeypatch.setattr(keyboard, "focus", lambda hwnd: focused.append(hwnd) or True)
    launched = []
    monkeypatch.setattr(apps, "launch", launched.append)
    skill = apps.Apps.__new__(apps.Apps)
    skill.aliases, skill._apps = {}, [wechat]
    skill._ready = type("Ready", (), {"wait": lambda self, timeout=None: True})()
    reply = skill.handle("打开微信", Context(config={}, say=print))
    assert focused == [42] and launched == [] and "切换到微信" in reply


class FakeProcess:
    def __init__(self, exe):
        self._exe = exe

    def exe(self):
        return self._exe


def test_same_program_matches_launcher_children_not_neighbours():
    from turing.keyboard import same_program

    douyin = same_program(r"D:\Program Files (x86)\ByteDance\douyin\douyin.exe")
    assert douyin(FakeProcess(r"D:\Program Files (x86)\ByteDance\douyin\douyin.exe"))
    assert douyin(FakeProcess(r"D:\Program Files (x86)\ByteDance\douyin\6.2.0\douyin_app.exe"))
    assert not douyin(FakeProcess(r"D:\Program Files (x86)\ByteDance\feishu\feishu.exe"))
    # A program sitting directly in a shared folder only matches itself.
    cmd = same_program(r"C:\Windows\System32\cmd.exe")
    assert cmd(FakeProcess(r"C:\Windows\System32\cmd.exe"))
    assert not cmd(FakeProcess(r"C:\Windows\System32\notepad.exe"))


@pytest.fixture
def apps_skill(monkeypatch):
    from turing.skills import apps

    douyin = apps.App("抖音", r"D:\Program Files (x86)\ByteDance\douyin\douyin.exe", "抖音", "douyin")
    skill = apps.Apps.__new__(apps.Apps)
    skill.aliases, skill._apps = {}, [douyin]
    skill._ready = type("Ready", (), {"wait": lambda self, timeout=None: True})()
    return skill


def test_close_app(apps_skill, monkeypatch):
    from turing import keyboard

    closed = []
    monkeypatch.setattr(keyboard, "windows_of_exe", lambda exe: [7, 8])
    monkeypatch.setattr(keyboard, "close", closed.append)
    reply = apps_skill.handle("关闭抖音", Context(config={}, say=print))
    assert closed == [7, 8] and "已关闭抖音" in reply


def test_close_app_not_open(apps_skill, monkeypatch):
    from turing import keyboard
    from turing.skills import Fallback

    monkeypatch.setattr(keyboard, "windows_of_exe", lambda exe: [])
    monkeypatch.setattr(keyboard, "windows_titled", lambda title: [])
    monkeypatch.setattr(keyboard, "close", lambda h: pytest.fail("closed something"))
    reply = apps_skill.handle("关掉抖音", Context(config={}, say=print))
    assert isinstance(reply, Fallback) and "没有找到打开着的抖音" in reply


def test_close_turing_explains_how(apps_skill):
    assert "小圆球" in apps_skill.handle("退出图灵", Context(config={}, say=print))


def test_typed_commands_confirm_themselves():
    from turing.app import Assistant

    bot = Assistant.__new__(Assistant)
    bot.source, bot._stt = None, None
    assert bot.confirm("要发吗？") is True
