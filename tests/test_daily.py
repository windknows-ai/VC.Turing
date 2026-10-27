"""Round two of everyday commands: editing keys, notes, timers, world clock and dates, PC status,
quotes, maps, email, playing videos, and Turing's own settings. Words only; no effects."""

import datetime as dt

import pytest

from turing.skills import Context, calendar, clock, editing, everyday, info, normalize, notes, pcstatus, selfcontrol


def ctx():
    return Context(config={}, say=print)


@pytest.mark.parametrize("text, action", [
    ("保存一下", "save"), ("帮我把这个文件另存为", "save_as"), ("撤销", "undo"), ("全选", "select_all"),
    ("复制", "copy"), ("粘贴", "paste"), ("按一下回车", "enter"), ("放大一点", "zoom_in"), ("缩小一点", "zoom_out"),
    ("恢复默认大小", "zoom_reset"), ("往下翻一页", "page_down"), ("滚到最上面", "top"), ("全屏", "fullscreen"),
    ("视频全屏", "video_fullscreen"), ("退出全屏", "exit_fullscreen"), ("save this", "save"), ("zoom in", "zoom_in"),
    ("scroll down", "page_down"),
])
def test_editing_words(text, action):
    assert next(a for a, p in editing.PATTERNS if p.match(normalize(text))) == action


def test_previous_window_words():
    assert editing._PREVIOUS.match("回到上一个窗口") and editing._PREVIOUS.match("切换窗口")


def test_notes_and_todos(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "FILE", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "PROFILE", tmp_path / "profile.json")
    skill, c = notes.Notes({}), ctx()
    assert "化学作业" in skill.handle(normalize("帮我记一下明天要交化学作业"), c)
    assert "买牛奶" in skill.handle(normalize("加一个待办：买牛奶"), c)
    assert "化学作业" in skill.handle(normalize("我记了什么"), c)
    assert "买牛奶" in skill.handle(normalize("我的待办有哪些"), c)
    assert "划掉" in skill.handle(normalize("完成待办买牛奶"), c)
    assert "没有待办" in skill.handle(normalize("我的待办有哪些"), c)
    assert "小明" in skill.handle(normalize("以后叫我小明"), c) and "小明" in skill.handle(normalize("我叫什么名字"), c)
    assert "call mom" in skill.handle(normalize("take a note: call mom tonight"), c)


def test_timer_list_and_pomodoro():
    skill, c = clock.Clock({}), ctx()
    assert "没有计时器" in skill.handle(normalize("计时器还剩多久"), c)
    assert "25分钟" in skill.handle(normalize("设一个25分钟的番茄钟"), c)
    listed = skill.handle(normalize("有哪些提醒"), c)
    assert "番茄钟" in listed and "还剩" in listed
    skill.handle(normalize("取消所有提醒"), c)


@pytest.mark.parametrize("city, utc, local", [
    ("北京", dt.datetime(2026, 10, 26, 18, 0), (2, 0)), ("伦敦", dt.datetime(2026, 7, 1, 12, 0), (13, 0)),
    ("伦敦", dt.datetime(2026, 12, 1, 12, 0), (12, 0)), ("多伦多", dt.datetime(2026, 7, 1, 12, 0), (8, 0)),
    ("多伦多", dt.datetime(2026, 12, 1, 12, 0), (7, 0)), ("悉尼", dt.datetime(2026, 1, 1, 0, 0), (11, 0)),
    ("tokyo", dt.datetime(2026, 10, 26, 18, 30), (3, 30)),
])
def test_world_clock_with_daylight_saving(city, utc, local):
    t = calendar.time_in(city, utc)
    assert (t.hour, t.minute) == local


def test_holidays_and_weekdays():
    today = dt.date(2026, 10, 26)
    assert calendar.holiday("圣诞节", today) == dt.date(2026, 12, 25)
    assert calendar.holiday("春节", today) == dt.date(2027, 2, 6)
    assert calendar.holiday("感恩节", today) == dt.date(2027, 10, 11)  # Canada's: 2nd Monday of October
    assert calendar._WEEKDAY_DATE.match("下周五是几号")


@pytest.mark.parametrize("text, method", [
    ("电脑内存用了多少", "memory"), ("cpu占用多少", "cpu"), ("c盘还剩多少空间", "disk"), ("现在有网吗", "network"),
    ("我的ip地址是多少", "ip"), ("电脑开机多久了", "uptime"), ("什么程序最占内存", "top"),
    ("how much memory is the pc using", "memory"),
])
def test_pc_status_words(text, method, monkeypatch):
    called = []
    for name in ("memory", "cpu", "disk", "network", "ip", "uptime", "top"):
        monkeypatch.setattr(pcstatus.PCStatus, name, lambda self, *a, n=name: called.append(n) or "ok")
    pcstatus.PCStatus({}).handle(normalize(text), ctx())
    assert called == [method]


@pytest.mark.parametrize("text, symbol", [("苹果股票现在多少钱", "AAPL"), ("特斯拉股价", "TSLA"), ("腾讯的股价", "0700.HK"),
                                          ("what's apple's stock price", "AAPL")])
def test_stock_words(text, symbol):
    m = info._STOCK.search(normalize(text))
    assert info.STOCKS[next(g for g in m.groups() if g).lower()] == symbol


def test_crypto_words():
    m = info._COIN.search(normalize("比特币现在多少钱"))
    assert info.COINS[next(g for g in m.groups() if g)] == "bitcoin"


@pytest.mark.parametrize("text, site, query", [
    ("播放周杰伦的晴天", "youtube", "周杰伦的晴天"), ("在YouTube上放一首lofi", "youtube", "lofi"),
    ("B站播放影视飓风最新的视频", "bilibili", "影视飓风最新的视频"), ("放点轻音乐", "youtube", "轻音乐"),
    ("play some jazz on youtube", "youtube", "some jazz"),
])
def test_play_words(text, site, query, monkeypatch):
    played = []
    monkeypatch.setattr(everyday.Everyday, "play", lambda self, q, s, c: played.append((s, q)) or "ok")
    everyday.Everyday({}).handle(normalize(text), ctx())
    assert played == [(site, query)]


@pytest.mark.parametrize("text", ["播放", "继续播放", "播放音乐", "用网易云音乐放晴天"])
def test_plain_play_is_left_to_media_keys(text, monkeypatch):
    monkeypatch.setattr(everyday.Everyday, "play", lambda *a: pytest.fail("not a title"))
    assert everyday.Everyday({}).handle(normalize(text), ctx()) is None


def test_maps_and_email_words(monkeypatch):
    opened = []
    monkeypatch.setattr(everyday.webbrowser, "open", opened.append)
    monkeypatch.setattr(everyday, "mail_app", lambda: False)
    skill, c = everyday.Everyday({}), ctx()
    skill.handle(normalize("去多伦多怎么走"), c)
    skill.handle(normalize("附近有什么好吃的"), c)
    reply = skill.handle(normalize("给老师发邮件说我明天请假"), c)
    assert "maps/dir" in opened[0] and "maps/search" in opened[1] and "mail.google.com" in opened[2]
    assert "收件人地址请你填上" in reply and "点发送" in reply  # a draft: the user sends it


def test_turing_settings(monkeypatch):
    saved = {}
    monkeypatch.setattr(selfcontrol.config, "save_section", lambda s, v: saved.update({s: v}))
    monkeypatch.setattr(notes, "set_profile", lambda **kw: saved.update(kw))
    skill = selfcontrol.Selfcontrol if hasattr(selfcontrol, "Selfcontrol") else selfcontrol.SelfControl
    c = Context(config={"voice": {"engine": "edge", "rate": "+10%"}}, say=print)
    s = skill({})
    s.handle(normalize("说慢一点"), c)
    assert c.config["voice"]["rate"] == "-5%" and saved["voice"] == {"rate": "-5%"}
    s.handle(normalize("换成女声"), c)
    assert c.config["voice"]["zh"] == "zh-CN-XiaoxiaoNeural"
    s.handle(normalize("用英文回答我"), c)
    assert saved["reply_language"] == "en"
    assert "能" in s.handle(normalize("你能做什么"), Context(config={}, say=print))
    s.handle(normalize("暂停聆听"), c)
    assert c.state["stop_listening"] is True


def test_editing_keys_wait_for_the_app_just_opened(monkeypatch):
    """"Open Notepad, then press Enter": Enter mustn't land in some other window."""
    import time

    import win32gui
    import win32process

    from turing import keyboard

    pressed = []
    monkeypatch.setattr(editing.windows, "current_window", lambda: 7)
    monkeypatch.setattr(editing.windows, "label", lambda h: "Claude")
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda: 7)
    monkeypatch.setattr(win32gui, "GetWindowText", lambda h: "Claude")
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda h: (0, 999999))
    monkeypatch.setattr(keyboard, "press", pressed.append)
    c = ctx()
    c.state["opened"] = {"name": "记事本", "exe": "", "at": time.monotonic()}
    reply = editing.Editing({}).do("enter", c)
    assert pressed == [] and "没有在" in reply
    c.state["opened"]["at"] -= 60
    editing.Editing({}).do("enter", c)
    assert pressed == ["enter"]


def test_hidden_windows_are_never_shown_from_outside(monkeypatch):
    """Forcing WeChat's tray-hidden window visible froze it (it drew but ignored clicks)."""
    import win32gui

    from turing import keyboard

    shown = []
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda h: False)
    monkeypatch.setattr(win32gui, "ShowWindow", lambda h, how: shown.append(how))
    assert keyboard.focus(123) is False and shown == []


def test_wechat_in_the_tray_is_brought_back_by_its_own_shortcut(monkeypatch):
    import win32gui

    from turing import keyboard
    from turing.skills import apps, messaging

    state = {"visible": False}
    pressed, started = [], []
    monkeypatch.setattr(keyboard, "window_of_exe", lambda exe, title=None: 42)
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda h: state["visible"])
    monkeypatch.setattr(keyboard, "focus", lambda h: state["visible"])
    monkeypatch.setattr(apps.os, "startfile", started.append)

    def press(keys):
        pressed.append(keys)
        state["visible"] = True  # WeChat shows itself
    monkeypatch.setattr(keyboard, "press", press)
    wechat = apps.App("微信", r"D:\Program Files\Tencent\Weixin\Weixin.exe", "微信", "weixin")
    assert apps.switch_to_running(wechat) is True
    assert pressed == [messaging.WECHAT_SHOW_KEYS] and started == []  # never a second WeChat

    # WeChat's shortcut turned off: say so, don't freeze it or start another copy
    state["visible"] = False
    monkeypatch.setattr(keyboard, "press", lambda keys: None)
    monkeypatch.setattr(messaging.time, "sleep", lambda s: None)
    with pytest.raises(apps.TrayError):
        apps.switch_to_running(wechat)
    assert started == []


def test_other_tray_apps_are_asked_to_show_themselves(monkeypatch):
    import win32gui

    from turing import keyboard
    from turing.skills import apps

    started = []
    monkeypatch.setattr(keyboard, "window_of_exe", lambda exe, title=None: 7)
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda h: bool(started))
    monkeypatch.setattr(apps.os, "startfile", started.append)
    discord = apps.App("Discord", r"C:\Apps\Discord\Discord.exe", "discord", "discord")
    assert apps.switch_to_running(discord) is True and started == [r"C:\Apps\Discord\Discord.exe"]
