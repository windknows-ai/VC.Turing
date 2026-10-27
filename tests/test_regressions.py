"""One test per bug that has happened before and had no test yet, so none can come back
unnoticed. Each docstring says what went wrong. (Bugs already covered elsewhere are
listed in tests/README_REGRESSIONS.md with the test that guards them.)"""

import ctypes
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pytest

from turing.skills import Context, normalize

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "turing" / "control_center" / "web"


def ctx(**kw):
    return Context(config={}, say=print, **kw)


# --- windows and pages ---------------------------------------------------------------

def test_orb_background_is_glass_not_a_colour_key(monkeypatch):
    """Orb on a grey square (pywebview transparency raced), then a colour key that let
    every click fall through. The background must be DWM glass, and never a colour key."""
    from turing.control_center import floating

    calls = []
    u = ctypes.windll.user32
    monkeypatch.setattr(u, "GetWindowLongW", lambda h, i: 0)
    monkeypatch.setattr(u, "SetWindowLongW", lambda h, i, v: calls.append(("style", v)))
    monkeypatch.setattr(u, "SetLayeredWindowAttributes", lambda *a: calls.append(("colorkey",)))
    monkeypatch.setattr(ctypes.windll.dwmapi, "DwmExtendFrameIntoClientArea", lambda h, m: calls.append(("glass",)))
    floating.set_tool_style(1234)
    assert ("glass",) in calls and ("colorkey",) not in calls
    style = next(v for k, v in calls if k == "style")
    assert style & 0x80 and not style & 0x80000  # tool window, not layered
    src = Path(floating.__file__).read_text(encoding="utf-8")
    assert "BackColor = Color.Black" in src  # black is what glass draws as clear


def test_restyling_our_windows_never_uses_pywin32():
    """Startup deadlock: pywin32 calls on our own windows from a background thread."""
    from turing.control_center import floating
    import inspect

    assert "win32gui." not in inspect.getsource(floating.set_tool_style)


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def wait(self, timeout=None):
        return True


class _Window:
    def __init__(self, title):
        self.title, self.hidden = title, False
        self.events = type("E", (), {})()
        for name in ("before_show", "closing", "loaded"):
            setattr(self.events, name, _Event())
        self.x = self.y = 0

    def hide(self):
        self.hidden = True

    def evaluate_js(self, script):
        return None


def test_orb_and_bubble_never_get_a_taskbar_button_and_the_bubble_starts_hidden(monkeypatch):
    """A flashing taskbar icon (style set too late), and the transparent bubble showing
    itself on load although created hidden."""
    from turing.control_center import floating

    windows = []
    fake_webview = type("W", (), {"create_window": lambda self, title, **kw: windows.append(_Window(title)) or windows[-1]})()
    f = floating.Floating(type("Eng", (), {"watchers": [], "state": "waiting"})())
    main = _Window("图灵")
    f.create(fake_webview, WEB, api=None, main=main)
    orb, bubble = windows
    assert floating.as_tool_window in orb.events.before_show.handlers
    assert floating.as_tool_window in bubble.events.before_show.handlers
    f.started()
    assert bubble.hidden


def test_main_page_address_has_no_query():
    """ERR_FILE_NOT_FOUND: '?background' on the page's file address became part of the file name."""
    src = (ROOT / "turing" / "control_center" / "__init__.py").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if 'index.html").as_uri()' in l)
    assert "?" not in line.split("as_uri()", 1)[1]


def test_long_pages_scroll():
    """The settings and persona pages couldn't scroll."""
    css = (WEB / "app.css").read_text(encoding="utf-8")
    rule = next(l for l in css.splitlines() if "overflow-y: auto" in l and "#view-settings" in l)
    assert "#view-persona" in rule and "#view-test" in rule


def test_page_script_only_uses_elements_that_exist():
    """The old test panel code kept using ids removed from the page (a dead settings page)."""
    js = (WEB / "app.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([\w-]+)"', html)) | set(re.findall(r'id="([\w-]+)"', js))
    used = set(re.findall(r'getElementById\("([\w-]+)"\)', js)) | set(re.findall(r'\$\("([\w-]+)"\)', js))
    assert not used - ids, f"missing in the page: {used - ids}"


class _Texts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found, self.skip, self.no = [], 0, []  # no: open tags marked translate="no"

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        if a.get("translate") == "no":
            self.no.append(tag)
        for k in ("placeholder", "aria-label", "title"):
            if a.get(k) and re.search(r"[\u4e00-\u9fff]", a[k]) and not self.no:
                self.found.append(a[k])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self.skip -= 1
        if self.no and tag == self.no[-1]:
            self.no.pop()

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data).strip()
        if text and not self.skip and not self.no and re.search(r"[\u4e00-\u9fff]", text):
            self.found.append(text)


def test_every_chinese_text_on_the_pages_has_an_english_version():
    """English mode must not leave Chinese behind when someone adds text to a page."""
    js = (WEB / "i18n.js").read_text(encoding="utf-8")
    keys = {k.replace('\\"', '"') for k in re.findall(r'"((?:[^"\\]|\\.)*)"\s*:', js)}
    patterns = [re.compile(p) for p in re.findall(r"\[/(\^.*?\$)/,", js)]  # "5 秒" etc.
    missing = []
    for page in ("index.html", "bubble.html", "orb.html"):
        p = _Texts()
        p.feed((WEB / page).read_text(encoding="utf-8"))
        missing += [t for t in p.found if t not in keys and not any(r.match(t) for r in patterns)]
    assert not missing, f"add these to i18n.js: {missing}"


# --- speech --------------------------------------------------------------------------

def test_name_mid_sentence_does_not_wake():
    """False wakes: "图灵" in the middle of a sentence ("关于图灵的电影") woke Turing."""
    from turing.wakeword import WakeWord

    w = WakeWord.__new__(WakeWord)
    import collections
    w._levels = collections.deque([0.03] * 20 + [0.05] * 10, maxlen=30)   # talking, then the name
    assert not w._paused_before()
    w._levels = collections.deque([0.001] * 20 + [0.05] * 10, maxlen=30)  # quiet, then the name
    assert w._paused_before()


def test_a_pause_after_then_does_not_cut_the_sentence():
    """"打开微信然后…(pause)…发消息" was cut in two at the pause after 然后."""
    from turing.stt import Transcriber

    t = Transcriber.__new__(Transcriber)
    t._cfg = {"end_silence_seconds": 0.8}
    assert t.end_pause("打开微信然后", 2.0) >= 2.0
    assert t.end_pause("打开微信", 2.0) == 0.8


def test_messages_are_rechecked_by_the_accurate_recognizer(monkeypatch):
    """"给土豆发 Where are you" was heard as "不要语": English in a message needs Qwen3."""
    from turing import stt

    t = stt.Transcriber.__new__(stt.Transcriber)
    t.mode = "auto"
    t._fast = lambda s: "给土豆发不要语"
    t._accurate = type("A", (), {"loaded": True, "__call__": lambda self, s: "给土豆发 Where are you"})()
    monkeypatch.setattr(stt, "memory_to_spare", lambda: True)
    assert t._recognize(np.zeros(1600, dtype=np.float32)) == "给土豆发 Where are you"


def test_big_recognizer_is_let_go_when_listening_stops():
    """After a settings change restarted listening, the old 1.4 GB model stayed in memory
    until an unload timer fired, so models piled up."""
    from turing.stt import OnDemand

    od = OnDemand(lambda: (lambda s: "x"), idle_seconds=600)
    od(np.zeros(10, dtype=np.float32))
    assert od.loaded and od._timer is not None
    od.close()
    assert not od.loaded and od._timer is None


def test_numpy_does_not_reserve_memory_per_cpu_thread():
    """Importing numpy reserved ~750 MB (an OpenBLAS buffer per CPU thread)."""
    out = subprocess.run([sys.executable, "-c", "import turing, os; print(os.environ.get('OPENBLAS_NUM_THREADS'))"],
                         cwd=ROOT, capture_output=True, text=True, timeout=60, env={**os.environ, "OPENBLAS_NUM_THREADS": ""})
    assert out.stdout.strip() in ("1", "")  # set unless the user set it on purpose
    src = (ROOT / "turing" / "__init__.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")' in src


# --- acting on the PC ----------------------------------------------------------------

def test_window_actions_use_calls_that_exist():
    """Maximize crashed: win32gui has no IsZoomed."""
    from turing.skills import windows
    import inspect

    assert "win32gui.IsZoomed" not in inspect.getsource(windows)
    assert hasattr(ctypes.windll.user32, "IsZoomed")


def test_saving_works_when_windows_refuses_the_swap(tmp_path, monkeypatch):
    """Notes failed to save: "can't move the file to a different drive" (AppData virtualized)."""
    from turing import paths

    def refuse(self, target):
        raise OSError(17, "The system cannot move the file to a different disk drive")
    monkeypatch.setattr(Path, "replace", refuse)
    target = tmp_path / "notes.json"
    paths.write_text_safely(target, '{"ok": 1}')
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_english_names_find_windows_own_apps():
    """"open notepad" failed: on Chinese Windows Notepad is listed as 记事本."""
    from turing.skills import apps

    listed = [apps.App(n, n, apps._key(n), apps._pinyin(n)) for n in ("记事本", "计算器", "微信")]
    assert apps.find_app("notepad", listed, {}).name == "记事本"
    assert apps.find_app("calculator", listed, {}).name == "计算器"


def test_qq_requests_never_go_out_on_wechat(monkeypatch):
    """"用QQ给张三发消息" was sent through WeChat."""
    from turing.skills import messaging

    sent = []
    monkeypatch.setattr(messaging, "send_wechat", lambda c, m: sent.append((c, m)))
    c = ctx(confirm=lambda q: True)
    c.state["command"] = "用QQ给张三发消息说明天见"
    reply = messaging.Messaging({}).send("张三", "明天见", c)
    assert sent == [] and "只能用微信" in reply


def test_keys_never_go_into_turings_own_window(monkeypatch):
    """The AI typed a profile name into Turing's own bubble and pressed Enter."""
    import win32gui
    import win32process

    from turing.skills import keys

    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda: 5)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda h: (0, os.getpid()))
    tool = next(t for t in keys.Keys({}).tools() if t.name == "type_text")
    assert tool.run({"text": "Alex Chen [Student]"}, ctx()).startswith("Error")


class _FakeUser32:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args):
            self.calls.append(name)
            return 1
        return call


def test_bringing_a_window_forward_does_not_tap_alt(monkeypatch):
    """Tapping Alt put the window in menu mode: the first typed key was lost and WeChat
    seemed to ignore the keyboard."""
    import win32gui

    from turing import keyboard

    fake = _FakeUser32()
    monkeypatch.setattr(keyboard, "_user32", fake)
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda h: True)
    monkeypatch.setattr(win32gui, "IsIconic", lambda h: False)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda: 9)
    keyboard.focus(9)
    assert "keybd_event" not in fake.calls and "SendInput" not in fake.calls


def test_typing_leaves_the_clipboard_alone(monkeypatch):
    """Typing pasted via the clipboard and lost a copied image or file."""
    from turing import keyboard

    fake = _FakeUser32()
    monkeypatch.setattr(keyboard, "_user32", fake)
    monkeypatch.setattr(keyboard, "_set_clipboard", lambda t: pytest.fail("clipboard touched"))
    monkeypatch.setattr(keyboard, "_get_clipboard", lambda: pytest.fail("clipboard read"))
    monkeypatch.setattr(keyboard, "press", lambda k: fake.calls.append(k))
    keyboard.real_type_text("你好\n世界😀")
    assert "SendInput" in fake.calls and "shift+enter" in fake.calls  # a line break never sends a chat


def test_ollama_is_not_started_twice(monkeypatch):
    """Two Ollama servers fought for the port while Ollama's own one kept restarting."""
    from turing.control_center import ollama

    started = []
    monkeypatch.setattr(ollama, "executable", lambda: r"C:\Ollama\ollama.exe")
    monkeypatch.setattr(ollama, "server_process_running", lambda: True)
    monkeypatch.setattr(ollama.subprocess, "Popen", lambda *a, **k: started.append(a))
    ollama.start()
    assert started == []


def test_model_download_unpacks_on_a_redirected_drive_but_refuses_escapes(tmp_path):
    """Qwen3 failed to unpack: "Paths don't have the same drive" (AppData on another drive)."""
    from turing import models

    src = tmp_path / "m"
    src.mkdir()
    (src / "model.onnx").write_bytes(b"x")
    good = tmp_path / "good.tar.bz2"
    with tarfile.open(good, "w:bz2") as tar:
        tar.add(src / "model.onnx", arcname="pkg/model.onnx")
    models._extract(good, tmp_path / "out")
    assert (tmp_path / "out" / "pkg" / "model.onnx").exists()
    bad = tmp_path / "bad.tar.bz2"
    with tarfile.open(bad, "w:bz2") as tar:
        tar.add(src / "model.onnx", arcname="../evil.onnx")
    with pytest.raises(RuntimeError):
        models._extract(bad, tmp_path / "out2")


# --- understanding ---------------------------------------------------------------------

def test_this_week_is_not_sunday():
    """"这周天气怎么样" answered with Sunday only: "这周天气" contains "周天"."""
    from turing.skills import weather

    assert weather.parse("这周天气怎么样")[1] == weather.WEEK


def test_date_question_with_xianzai():
    """"现在是几月几号" wasn't understood."""
    from turing.skills import clock

    assert clock.Clock({}).handle(normalize("现在是几月几号"), ctx()).startswith("今天是")


def test_alarms_are_listed_by_their_time():
    """A 7 am alarm was listed as "16小时23分钟4秒"."""
    from turing.skills import clock

    c, skill = ctx(), clock.Clock({})
    skill.handle(normalize("定一个明天早上7点的闹钟"), c)
    try:
        assert "7点00分的闹钟" in skill.list_timers(c)
    finally:
        skill.handle(normalize("取消所有提醒"), c)


def test_ai_must_not_state_unfounded_facts_or_use_chatgpt_unasked():
    """The AI made up an exchange rate (7.24), and sent the clipboard to ChatGPT to translate."""
    from turing import ai
    from turing.skills import web

    assert "Never state facts" in ai.SYSTEM_PROMPT
    tool = next(t for t in web.Web({}).tools() if t.name == "ask_chatbot")
    assert "ONLY when the user names" in tool.description


# --- test harness and tests themselves -------------------------------------------------

def test_dry_run_harness_changes_nothing_real():
    """A dry run once really muted the PC, changed the voice to female, saved a name and
    'reply in English', and read the real clipboard."""
    code = (
        "import sys; sys.path.insert(0, 'scripts'); sys.path.insert(0, '.')\n"
        "import scenario_eval as s\n"
        "from turing import config, keyboard\n"
        "from turing.skills import volume, notes, device, desktops\n"
        "orig = config.save_section\n"
        "s.intercept()\n"
        "assert config.save_section is not orig, 'settings'\n"
        "assert type(volume._endpoint()).__name__ == 'FakeEndpoint', 'mute'\n"
        "assert keyboard._get_clipboard().startswith('（测试'), 'clipboard'\n"
        "assert '.scratch' in str(notes.FILE) and '.scratch' in str(notes.PROFILE), 'notes'\n"
        "assert device.set_dark_mode.__name__ == 'fake' and desktops.switch_to.__name__ == 'fake', 'device'\n"
        "print('isolated')\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", timeout=120)
    assert "isolated" in out.stdout, out.stderr[-800:]


def test_pythonw_without_a_console_still_logs(tmp_path):
    """"开始聆听" did nothing under pythonw: sys.stdout was None and the listener died silently."""
    code = ("import sys; sys.stdout = None; sys.stderr = None\n"
            "import turing.desktop\n"
            "open(sys.argv[1], 'w').write(str(sys.stdout is not None and sys.stderr is not None))\n")
    out = tmp_path / "ok.txt"
    subprocess.run([sys.executable, "-c", code, str(out)], cwd=ROOT, timeout=60,
                   env={**os.environ, "TURING_DATA_DIR": str(tmp_path)})
    assert out.read_text() == "True"


@pytest.mark.parametrize("body", ["This model is not in the Free plan.",
                                  {"error": "This model is not in the Free plan."},
                                  {"error": {"message": "This model is not in the Free plan."}}])
def test_provider_error_text_is_found_whatever_the_sdk_version(body):
    """openai 3.39 stopped putting the server's sentence in e.message and hands it over as
    a plain string in e.body: a paid-plan model was reported as "out of credit"."""
    from turing import ai

    class Err(Exception):
        message = "Error code: 402"

    e = Err()
    e.body = body
    assert ai.provider_message(e) == "This model is not in the Free plan."
    assert ai.status_error(402, ai.provider_message(e)).kind == "plan"


@pytest.mark.parametrize("text, skill", [
    ("亮度调高", "device"), ("调高屏幕亮度", "device"), ("把亮度调低", "device"), ("连上蓝牙耳机", "device"),
    ("春节还有几天", "calendar"), ("100美元换人民币", "info"), ("200加元兑人民币", "info")])
def test_everyday_wordings_from_the_readme_are_understood(text, skill, monkeypatch):
    """Examples shown in the README fell through to "这个我还不会" without an AI."""
    from turing.skills import calendar, device, info

    monkeypatch.setattr(device, "get_brightness", lambda: 50)
    monkeypatch.setattr(device, "set_brightness", lambda v: None)
    monkeypatch.setattr(device, "open_settings", lambda page: None)
    monkeypatch.setattr(info, "rate", lambda a, b: (7.0, ""))
    s = {"device": device.Device({}), "calendar": calendar.Calendar({}), "info": info.Info({})}[skill]
    assert s.handle(normalize(text), ctx()) is not None
