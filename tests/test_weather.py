"""Weather answered directly, and the browser opened only when asked. No network calls."""

import pytest

from turing.skills import Context, load_skills, normalize, route
from turing.skills import weather
from turing.skills.weather import Weather, describe, parse

FORECAST = {
    "current": {"temperature_2m": 13.6, "weather_code": 0},
    "daily": {"weather_code": [0, 61, 3], "temperature_2m_max": [17.9, 12.1, 14.4],
              "temperature_2m_min": [8.2, 6.0, 7.5], "precipitation_probability_max": [5, 80, 20]},
}


@pytest.mark.parametrize("text,expected", [
    ("今天天气怎么样", (None, 0)),
    ("明天北京会下雨吗", ("北京", 1)),
    ("北京明天天气", ("北京", 1)),
    ("上海的天气", ("上海", 0)),
    ("外面冷不冷", (None, 0)),
    ("现在多少度", (None, 0)),
    ("后天要不要带伞", (None, 2)),
    ("what's the weather tomorrow", (None, 1)),
    ("weather in toronto", ("toronto", 0)),
    ("查一下明天的天气", (None, 1)),
])
def test_parse_weather_questions(text, expected):
    assert parse(normalize(text)) == expected


@pytest.mark.parametrize("text", ["放一首下雨天的歌", "百度一下天气", "打开微信", "几点了"])
def test_not_weather_questions(text):
    assert parse(normalize(text)) is None


def test_describe_today_and_tomorrow():
    assert describe("北京", FORECAST, 0, True) == "北京今天晴，8到18度，现在14度，下雨概率5%。"
    assert describe("北京", FORECAST, 1, True) == "北京明天小雨，6到12度，下雨概率80%。"
    assert describe("Oakville", FORECAST, 1, False) == \
        "Oakville tomorrow: light rain, 6 to 12 degrees, 80% chance of rain."


@pytest.fixture
def offline(monkeypatch):
    asked = []
    monkeypatch.setattr(weather, "locate",
                        lambda city, zh=True: asked.append(city) or (city or "奥克维尔", 43.4, -79.7))
    monkeypatch.setattr(weather, "forecast", lambda lat, lon: FORECAST)
    return asked


def test_uses_city_from_settings(offline):
    reply = Weather({"weather": {"city": "北京"}}).handle("今天天气怎么样", Context(config={}, say=print))
    assert offline == ["北京"] and reply.startswith("北京今天晴")


def test_city_in_question_wins(offline):
    Weather({"weather": {"city": "北京"}}).handle("上海明天天气", Context(config={}, say=print))
    assert offline == ["上海"]


def test_no_internet(monkeypatch):
    def fail(city, zh=True):
        raise OSError("offline")

    monkeypatch.setattr(weather, "locate", fail)
    assert "查不到天气" in Weather({}).handle("天气怎么样", Context(config={}, say=print))


def test_weather_never_opens_the_browser(offline, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("opened the browser"))
    skills = load_skills({"apps": {"aliases": {}}})
    for text in ("查一下明天的天气", "今天天气怎么样", "明天会下雨吗"):
        assert "度" in route(skills, text, Context(config={}, say=print))


def test_explicit_search_still_opens_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    skills = load_skills({"apps": {"aliases": {}}})
    route(skills, "百度一下天气", Context(config={}, say=print))
    assert len(opened) == 1
