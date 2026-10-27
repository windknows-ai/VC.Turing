"""The everyday commands found missing or mishandled in the scenario run, parsed to the
right ability. Effects on the PC are covered by the live checks; these test the words."""

import datetime as dt

import pytest

from turing.skills import Context, clock, desktops, device, files, info, normalize, weather, windows


def match(pattern, text):
    return pattern.match(normalize(text))


@pytest.mark.parametrize("text, pattern", [
    ("把Chrome最小化", windows._MIN), ("最小化当前窗口", windows._MIN), ("minimize this window", windows._MIN),
    ("最大化当前窗口", windows._MAX), ("把微信最大化", windows._MAX), ("还原窗口", windows._RESTORE),
    ("把这个窗口放到屏幕左边", windows._SNAP), ("snap chrome to the right", windows._SNAP),
    ("显示桌面", windows._DESKTOP), ("minimize all windows", windows._DESKTOP),
    ("关闭当前窗口", windows._CLOSE), ("切换到微信", windows._SWITCH),
])
def test_window_commands(text, pattern):
    assert match(pattern, text)


@pytest.mark.parametrize("text, action", [
    ("在浏览器里新建一个标签页", "new"), ("关掉这个标签页", "close"), ("刷新一下页面", "refresh"),
    ("返回上一页", "back"), ("new tab", "new"), ("reopen the closed tab", "reopen"),
])
def test_tab_commands(text, action):
    assert next(a for a, p in windows._TABS if p.match(normalize(text))) == action


@pytest.mark.parametrize("query, index", [("学习", 0), ("ai", 1), ("2", 1), ("第一个", 0), ("雪习", 0)])
def test_desktop_by_name_number_or_sound(query, index):
    assert desktops.find(query, ["学习", "AI"]) == index


def test_desktop_sentences():
    assert desktops._SWITCH.match("帮我切换到学习那个桌面").group(1) == "学习"
    assert desktops._NEXT.match("切到下一个桌面") and desktops._NEW.match("新建一个桌面")
    assert desktops._SWITCH_EN.match("switch to the study desktop")


@pytest.mark.parametrize("text, pattern", [
    ("把屏幕调亮一点", device._BRIGHT_UP), ("屏幕暗一点", device._BRIGHT_DOWN), ("亮度调到50", device._BRIGHT_SET),
    ("打开深色模式", device._DARK), ("切换到浅色模式", device._LIGHT), ("截个图", device._SCREENSHOT),
    ("take a screenshot", device._SCREENSHOT), ("关机", device._SHUTDOWN), ("重启电脑", device._RESTART),
    ("取消关机", device._CANCEL_SHUTDOWN), ("让电脑睡眠", device._SLEEP), ("清空回收站", device._RECYCLE),
])
def test_device_commands(text, pattern):
    assert match(pattern, text)


def test_volume_words_are_not_brightness():
    assert not device._BRIGHT_UP.match("大声点") and not device._BRIGHT_UP.match("把音量调大一点")


def test_bluetooth_opens_its_settings_page(monkeypatch):
    opened = []
    monkeypatch.setattr(device, "open_settings", opened.append)
    reply = device.Device({}).handle(normalize("打开蓝牙"), Context(config={}, say=print))
    assert opened == ["bluetooth"] and "没法直接" in reply


def test_shutdown_asks_first_and_can_be_declined(monkeypatch):
    calls = []
    monkeypatch.setattr(device, "shutdown", lambda restart: calls.append(restart))
    ctx = Context(config={}, say=print, confirm=lambda q: False)
    assert "不操作" in device.Device({}).handle("关机", ctx) and calls == []


@pytest.mark.parametrize("text", ["在桌面新建一个文件夹", "在文档里新建一个叫作业的文件夹", "create a new folder called notes"])
def test_new_folder(text):
    assert files._NEW.match(normalize(text))


def test_find_and_latest():
    assert files._FIND.match("找一下桌面上的合同文件").group(2) == "合同"
    assert files._LATEST.match("打开最近下载的文件")


def test_downloaded_programs_are_never_run(tmp_path, monkeypatch):
    (tmp_path / "setup.exe").write_bytes(b"MZ")
    shown, started = [], []
    monkeypatch.setattr(files, "latest_download", lambda: str(tmp_path / "setup.exe"))
    monkeypatch.setattr(files, "show_in_explorer", shown.append)
    monkeypatch.setattr(files.os, "startfile", started.append)
    reply = files.Files({}).latest(Context(config={}, say=print))
    assert started == [] and shown and "没有运行" in reply


@pytest.mark.parametrize("text, src, dst", [("一美元等于多少人民币", "USD", "CNY"),
                                            ("100加元换多少人民币", "CAD", "CNY"),
                                            ("how much is 20 usd in cad", "USD", "CAD")])
def test_exchange_rate_question(text, src, dst, monkeypatch):
    seen = []
    monkeypatch.setattr(info, "rate", lambda a, b: (seen.append((a, b)), (2.0, ""))[1])
    reply = info.Info({}).handle(normalize(text), Context(config={}, say=print))
    assert seen == [(src, dst)] and reply


def test_news_is_not_a_web_search():
    assert info._NEWS.match("今天有什么新闻")


@pytest.mark.parametrize("text, hour, minute, days", [
    ("定一个明天早上7点的闹钟", 7, 0, 1), ("明天下午3点半提醒我开会", 15, 30, 1),
    ("晚上十点二十叫我", 22, 20, None), ("remind me at 7:30 pm tomorrow", 19, 30, 1),
])
def test_reminder_at_a_time(text, hour, minute, days):
    now = dt.datetime(2026, 10, 19, 21, 0)
    when = clock.parse_time_of_day(text, now)
    assert (when.hour, when.minute) == (hour, minute)
    if days is not None:
        assert (when.date() - now.date()).days == days


def test_reminder_says_what_for():
    assert clock.Clock._what("10分钟后提醒我喝水") == "喝水"


@pytest.mark.parametrize("text, city", [("奥克维尔周末会下雨吗", "奥克维尔"), ("北京星期六天气怎么样", "北京"),
                                        ("周末天气怎么样", None)])
def test_weather_city_without_time_words(text, city):
    found, day = weather.parse(text)
    assert found == city


def test_a_call_request_never_becomes_a_text(monkeypatch):
    from turing.skills import messaging

    sent = []
    monkeypatch.setattr(messaging, "send_wechat", lambda c, m: sent.append((c, m)))
    ctx = Context(config={}, say=print, confirm=lambda q: True)
    ctx.state["command"] = "给妈妈打个微信视频电话"
    reply = messaging.Messaging({}).send("妈妈", "视频电话", ctx)
    assert sent == [] and "什么都没有发" in reply
    ctx.state["command"] = "给土豆发微信说晚上打电话给你"  # a message that mentions a call is fine
    messaging.Messaging({}).send("土豆", "晚上打电话给你", ctx)
    assert sent == [("土豆", "晚上打电话给你")]
