"""Command parsing tests. These never touch the mic, speakers, volume or apps."""

import pytest

from turing.numbers import cn_to_int
from turing.skills import normalize
from turing.skills.apps import App, _key, _OPEN, _pinyin, find_app
from turing.skills.clock import _DATE, _TIME, parse_duration
from turing.skills.media import _PATTERNS
from turing.skills import volume
from turing.stt import clean
from turing.wakeword import keyword_tokens


@pytest.mark.parametrize("text,expected", [
    ("十", 10), ("十五", 15), ("三十", 30), ("二十五", 25), ("一百", 100), ("两", 2), ("一千二百", 1200),
])
def test_chinese_numbers(text, expected):
    assert cn_to_int(text) == expected


@pytest.mark.parametrize("raw,expected", [
    ("请帮我打开微信", "打开微信"),
    ("暂停一下", "暂停"),
    ("Please open Chrome", "open chrome"),
    ("谢谢", "谢谢"),
    ("你好", "你好"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("heard,command", [
    ("灵打开微信", "打开微信"), ("图灵现在几点了", "现在几点了"), ("嗨图灵暂停", "暂停"),
    ("Turing what time is it", "what time is it"), ("ring open chrome", "open chrome"),
    ("打开灵格斯", "打开灵格斯"), ("现在几点了", "现在几点了"),
    ("海图林打开微信", "打开微信"), ("嗨徒灵暂停", "暂停"), ("Hey touring, pause", "pause"),
    ("图联播放刚刚没放完的音乐", "播放刚刚没放完的音乐"),
    ("零点叫我", "零点叫我"), ("TOING WHAT TIME IS IT", "WHAT TIME IS IT"),
    ("hey what time is it", "what time is it"), ("bring me the news", "bring me the news"),
    ("thing one", "thing one"),
])
def test_strip_wake_word_tail(heard, command):
    from turing.stt import strip_wake

    assert strip_wake(heard) == command


def test_long_replies_are_shortened_for_speech():
    from turing.app import spoken

    assert spoken("现在是22点25分") == "现在是22点25分"
    long_zh = "这个错误的意思是你在空值上用了下标。" * 6 + "需要检查返回值。"
    out = spoken(long_zh)
    assert out.startswith("这个错误的意思是你在空值上用了下标。") and out.endswith("完整内容在图灵窗口里。")
    assert len(out) < len(long_zh)
    long_en = "This error means you indexed None. " * 8
    assert spoken(long_en).endswith("The rest is in the Turing window.")


def test_clean_transcript():
    assert clean("打开 微信。") == "打开微信"
    assert clean("Open Google Chrome.") == "Open Google Chrome"
    assert clean("打开 VS Code") == "打开VS Code"


@pytest.mark.parametrize("text,action", [
    ("播放", "play"), ("继续播放", "play"), ("play", "play"), ("resume", "play"),
    ("暂停", "pause"), ("停止播放", "pause"), ("pause", "pause"), ("stop", "pause"),
    ("下一首", "next"), ("切歌", "next"), ("next song", "next"), ("skip", "next"),
    ("上一首", "previous"), ("previous track", "previous"),
    ("这是什么歌", "now_playing"), ("what song is this", "now_playing"),
    # Said in real use, and missed before (they went to the AI, seconds slower):
    ("继续播放音乐", "play"), ("播放刚刚没放完的音乐", "play"), ("停止播放音乐", "pause"),
    ("stop the music", "pause"), ("resume the music", "play"), ("暂停一下音乐", "pause"),
])
def test_media_commands(text, action):
    assert next(k for k, p in _PATTERNS.items() if p.match(normalize(text))) == action


def test_media_does_not_steal_other_commands():
    for text in ("播放周杰伦的晴天", "打开音乐", "stop the timer"):
        assert not any(p.match(normalize(text)) for p in _PATTERNS.values()), text


@pytest.mark.parametrize("text,expected", [
    ("音量调整到五十", 50), ("音量调到30", 30), ("音量调到三十", 30), ("把音量设为百分之五十", 50), ("音量80", 80),
    ("set volume to 40", 40), ("volume 25", 25),
])
def test_volume_set(text, expected, monkeypatch):
    got = {}
    monkeypatch.setattr(volume, "set_volume", lambda v: got.setdefault("v", v))
    from turing.skills import Context

    volume.Volume({}).handle(normalize(text), Context(config={}, say=print))
    assert got["v"] == expected


@pytest.mark.parametrize("text", ["大声点", "声音大一点", "调大音量", "louder", "turn it up", "volume up"])
def test_volume_up(text):
    assert volume._UP.match(normalize(text))


@pytest.mark.parametrize("text", ["小声点", "音量调低一点", "quieter", "turn it down"])
def test_volume_down(text):
    assert volume._DOWN.match(normalize(text))


@pytest.mark.parametrize("text,seconds", [
    ("定一个10分钟的计时器", 600), ("五分钟后提醒我", 300), ("倒计时30秒", 30),
    ("一个半小时后提醒我", 5400), ("半小时后叫我", 1800), ("1小时30分钟后提醒我", 5400),
    ("set a timer for 5 minutes", 300), ("remind me in 2 hours", 7200),
])
def test_timer_duration(text, seconds):
    assert parse_duration(normalize(text)) == seconds


def test_time_and_date():
    for t in ("现在几点了", "几点了", "what time is it"):
        assert _TIME.match(normalize(t)), t
    for t in ("今天几号", "今天星期几", "what's the date"):
        assert _DATE.match(normalize(t)), t


def _app(name):
    return App(name, name, _key(name), _pinyin(name))


APPS = [_app(n) for n in ("微信", "微信开发者工具", "网易云音乐", "QQ音乐", "Google Chrome",
                          "Microsoft Edge", "Notepad", "Visual Studio Code")]


@pytest.mark.parametrize("spoken,expected", [
    ("微信", "微信"), ("网易云音乐", "网易云音乐"), ("网易运音乐", "网易云音乐"),
    ("qq音乐", "QQ音乐"), ("chrome", "Google Chrome"), ("谷歌浏览器", "Google Chrome"),
    ("记事本", "Notepad"), ("vscode", "Visual Studio Code"), ("edge", "Microsoft Edge"),
])
def test_find_app(spoken, expected):
    aliases = {_key(k): v for k, v in {"谷歌浏览器": "Google Chrome", "记事本": "Notepad",
                                       "vscode": "Visual Studio Code"}.items()}
    assert find_app(spoken, APPS, aliases).name == expected


def test_alias_falls_back_to_spoken_name():
    # Chinese Windows lists Notepad as 记事本, so the alias target won't be found.
    apps = [_app("记事本"), _app("计算器")]
    assert find_app("记事本", apps, {_key("记事本"): "Notepad"}).name == "记事本"


def test_unknown_app():
    assert find_app("原神", APPS, {}) is None


def test_open_pattern():
    assert _OPEN.match("打开微信").group(2) == "微信"
    assert _OPEN.match("open google chrome").group(2) == "google chrome"


def test_mixed_wake_word_tokens():
    lex = {"HEY": ["HH", "EY1"], "HI": ["HH", "AY1"]}
    assert keyword_tokens("Hey 图灵", lex) == [["HH", "EY1", "t", "ú", "l", "íng"]]
    assert keyword_tokens("Hi 图灵", lex) == [["HH", "AY1", "t", "ú", "l", "íng"]]


def test_old_wake_settings_are_upgraded(tmp_path):
    from turing import config

    path = tmp_path / "config.toml"
    path.write_text('[wake]\nkeywords = ["嗨图灵", "嘿图灵", "Hey Turing"]\nthreshold = 0.2\nboost = 2.0\n',
                    encoding="utf-8")
    wake = config.load(path)["wake"]
    assert "图灵" in wake["keywords"] and "Hey 图灵" in wake["keywords"]
    assert wake["sensitivity"] == 4 and "threshold" not in path.read_text(encoding="utf-8")


def test_custom_wake_words_are_kept(tmp_path):
    from turing import config

    path = tmp_path / "config.toml"
    path.write_text('[wake]\nkeywords = ["你好小图"]\nsensitivity = 2\n', encoding="utf-8")
    wake = config.load(path)["wake"]
    assert wake["keywords"] == ["你好小图"] and wake["sensitivity"] == 2


def test_wake_word_tokens():
    assert keyword_tokens("嗨图灵", {}) == [["h", "āi", "t", "ú", "l", "íng"]]
    lex = {"HEY": ["HH", "EY1"], "TURING": ["T", "UH1", "R", "IH0", "NG"]}
    spellings = keyword_tokens("Hey Turing", lex)
    assert spellings[0] == ["HH", "EY1", "T", "UH1", "R", "IH0", "NG"]
    assert ["HH", "EY1", "T", "UW1", "R", "IH0", "NG"] in spellings
