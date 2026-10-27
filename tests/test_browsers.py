"""Opening Chrome / Edge straight into the account the user names."""

import json

import pytest

from turing.skills import Context, apps, browsers, normalize

LOCAL_STATE = {"profile": {"info_cache": {
    "Default": {"name": "Your Chrome", "gaia_name": "Alex Chen (Alex)",
                "shortcut_name": "Alex (Your Chrome)", "user_name": "alex@example.com",
                "hosted_domain": "NO_HOSTED_DOMAIN"},
    "Profile 2": {"name": "Person 1", "gaia_name": "Alex Chen [Student]",
                  "shortcut_name": "Alex (Person 1)", "user_name": "123456@school.example",
                  "hosted_domain": "school.example"},
    "Profile 3": {"name": "sam", "gaia_name": "Sam Lee", "user_name": "sam@example.com"},
}}}


@pytest.fixture
def chrome(tmp_path, monkeypatch):
    folder = tmp_path / "Google" / "Chrome" / "User Data"
    folder.mkdir(parents=True)
    (folder / "Local State").write_text(json.dumps(LOCAL_STATE), encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return browsers.profiles("chrome")


@pytest.mark.parametrize("text, app, profile", [
    ("谷歌浏览器，使用student那个账号", "谷歌浏览器", "student"),
    ("chrome 用学生账号", "chrome", "学生"),
    ("chrome with my student account.", "chrome", "student"),
    ("edge as sam", "edge", "sam"),
    ("记事本", "记事本", ""),
])
def test_split_profile(text, app, profile):
    assert browsers.split_profile(text) == (app, profile)


def test_account_named_first():
    assert browsers.split_leading("用student账号打开chrome") == ("打开chrome", "student")
    assert browsers.split_leading("打开chrome") is None


@pytest.mark.parametrize("query, directory", [
    ("student", "Profile 2"), ("学生", "Profile 2"), ("Person 1", "Profile 2"),
    ("school.example", "Profile 2"), ("sam", "Profile 3"), ("your chrome", "Default"),
])
def test_find_profile(chrome, query, directory):
    assert browsers.find(query, chrome).directory == directory


def test_unclear_or_unknown_profile_is_not_guessed(chrome):
    assert browsers.find("alex chen", chrome) is None  # two profiles are Alex Chen's
    assert browsers.find("work", chrome) is None


def test_label_says_whose_account(chrome):
    assert [p.label for p in chrome][1] == "Person 1（Alex Chen [Student]）"


def test_open_chrome_in_student_profile(chrome, monkeypatch):
    launched = []
    monkeypatch.setattr(browsers, "launch", lambda kind, p: launched.append((kind, p.directory)) or True)
    skill = apps.Apps.__new__(apps.Apps)
    skill.aliases = {apps._key("谷歌浏览器"): "Google Chrome"}
    skill._apps = [apps.App("Google Chrome", "Chrome", apps._key("Google Chrome"),
                            apps._pinyin("Google Chrome"))]
    skill._ready = __import__("threading").Event()
    skill._ready.set()
    ctx = Context(config={}, say=print)
    for text in ("打开谷歌浏览器，使用student那个账号", "用学生账号打开Chrome",
                 "Open Chrome with my student account."):
        reply = skill.handle(normalize(text), ctx)
        assert "Person 1" in reply
    assert launched == [("chrome", "Profile 2")] * 3
    # Asking for an account that isn't there lists the real ones instead of guessing.
    reply = skill.handle(normalize("打开chrome，用工作账号"), ctx)
    assert "Your Chrome" in reply and launched == [("chrome", "Profile 2")] * 3
