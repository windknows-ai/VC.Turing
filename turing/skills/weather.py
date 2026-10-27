"""Weather, answered out loud straight away: "今天天气怎么样", "明天北京会下雨吗", "weather tomorrow".

Uses Open-Meteo (free, no key). Without a city in the command it uses the city set in
config ([weather] city), or else where the internet connection appears to be.
"""

import datetime
import json
import re
import urllib.parse
import urllib.request

from . import Context, Skill, Tool, schema

# Specific phrasings only: "放一首下雨天的歌" mentions rain but isn't a weather question.
_ASK = re.compile(
    r"天气|气温|多少度|冷不冷|热不热|会不会下[雨雪]|会下[雨雪]|下[雨雪]吗|要不要带伞|带伞吗|"
    r"空气质量|空气怎么样|空气好不好|pm2\.?5|雾霾|日出|日落|天黑|太阳(?:几点)?(?:升起|落山)|"
    r"air quality|sunrise|sunset"
    r"|weather|temperature|forecast|will it (rain|snow)|is it (raining|snowing)", re.I)
_EXPLICIT_SEARCH = re.compile(r"^(搜索|搜一下|百度|谷歌|用浏览器|在浏览器|在网上搜|search|google)", re.I)
_DAY = {"今天": 0, "今日": 0, "现在": 0, "明天": 1, "明日": 1, "后天": 2,
        "today": 0, "now": 0, "tomorrow": 1}
# A city named before 的/天气, e.g. "北京明天天气", "上海的天气", "weather in Toronto".
_CITY_ZH = re.compile(r"^(?:今天|明天|后天|现在)?(?P<city>[一-鿿]{2,8}?)(?:今天|明天|后天|现在)?(?:的)?(?:天气|气温|会|下雨|冷|热)")
_CITY_EN = re.compile(r"\b(?:in|for|at)\s+(?P<city>[a-z][a-z .'-]+?)(?:\s+(?:today|tomorrow|now))?$", re.I)
# Words before the question that aren't a place: "查一下明天的天气".
_LEAD_IN = re.compile(r"^(?:查一下|查查|查|看一下|看看|告诉我|说说|问一下|请问)")
_NOT_CITY = {"今天", "明天", "后天", "现在", "外面", "这边", "这里", "我们这", "我这", "最近", "这周", "周末"}
# When-words that can trail a city: "奥克维尔周末", "北京星期六".
_WHEN = re.compile(r"(?:这个?|本|下个?)?(?:周末|礼拜天|周[一二三四五六日天]|星期[一二三四五六日天]|礼拜[一二三四五六日天])"
                   r"|今天|明天|后天|早上|上午|中午|下午|晚上|这几天|最近$")
_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_WEEKDAY_EN = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
WEEKEND = "weekend"
WEEK = "week"
AIR, SUN = "air", "sun"
_WEEK_WORDS = re.compile(r"这周|本周|这个星期|这几天|未来几天|接下来几天|最近几天|一周|这礼拜|this week|next few days|the week", re.I)
_AIR_WORDS = re.compile(r"空气|pm2\.?5|雾霾|air quality", re.I)
_SUN_WORDS = re.compile(r"日出|日落|天黑|太阳|sunrise|sunset", re.I)

# WMO weather codes -> (Chinese, English)
CODES = {
    0: ("晴", "clear"), 1: ("大致晴朗", "mostly clear"), 2: ("多云", "partly cloudy"),
    3: ("阴", "overcast"), 45: ("有雾", "foggy"), 48: ("有雾", "foggy"),
    51: ("毛毛雨", "light drizzle"), 53: ("毛毛雨", "drizzle"), 55: ("毛毛雨", "heavy drizzle"),
    56: ("冻雨", "freezing drizzle"), 57: ("冻雨", "freezing drizzle"),
    61: ("小雨", "light rain"), 63: ("中雨", "rain"), 65: ("大雨", "heavy rain"),
    66: ("冻雨", "freezing rain"), 67: ("冻雨", "freezing rain"),
    71: ("小雪", "light snow"), 73: ("中雪", "snow"), 75: ("大雪", "heavy snow"), 77: ("小雪", "snow grains"),
    80: ("阵雨", "showers"), 81: ("阵雨", "showers"), 82: ("强阵雨", "heavy showers"),
    85: ("阵雪", "snow showers"), 86: ("阵雪", "snow showers"),
    95: ("雷阵雨", "thunderstorms"), 96: ("雷阵雨伴冰雹", "thunderstorms with hail"),
    99: ("雷阵雨伴冰雹", "thunderstorms with hail"),
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Turing voice assistant"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def locate(city: str | None, zh: bool = True) -> tuple[str, float, float] | None:
    """(name, latitude, longitude) for a city name, or for this connection if None.
    The name comes back in Chinese or English to match the question."""
    if city:
        q = urllib.parse.quote(city)
        found = _get("https://geocoding-api.open-meteo.com/v1/search"
                     f"?name={q}&count=1&language={'zh' if zh else 'en'}")
        hits = found.get("results") or []
        return (hits[0]["name"], hits[0]["latitude"], hits[0]["longitude"]) if hits else None
    here = _get(f"http://ip-api.com/json/?lang={'zh-CN' if zh else 'en'}&fields=status,city,lat,lon")
    return (here["city"], here["lat"], here["lon"]) if here.get("status") == "success" else None


def forecast(lat: float, lon: float) -> dict:
    return _get(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
        "&timezone=auto&forecast_days=7"
    )


def air(place: str, lat: float, lon: float, zh: bool) -> str:
    now = _get(f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}"
               "&current=us_aqi,pm2_5")["current"]
    aqi = round(now["us_aqi"])
    level = next((v for limit, v in ((50, ("优", "good")), (100, ("良", "moderate")), (150, ("对敏感人群不健康", "unhealthy for sensitive groups")),
                                     (200, ("不健康", "unhealthy")), (300, ("很不健康", "very unhealthy")))
                  if aqi <= limit), ("危险", "hazardous"))
    if zh:
        return f"{place}现在空气质量{level[0]}，AQI {aqi}，PM2.5 {now['pm2_5']:.0f}。"
    return f"Air quality in {place} is {level[1]}: AQI {aqi}, PM2.5 {now['pm2_5']:.0f}."


def week(place: str, data: dict, zh: bool) -> str:
    """The next five days, briefly."""
    daily = data["daily"]
    parts = []
    for d in range(min(5, len(daily["weather_code"]))):
        sky_zh, sky_en = CODES.get(daily["weather_code"][d], ("多变", "changeable"))
        lo, hi = round(daily["temperature_2m_min"][d]), round(daily["temperature_2m_max"][d])
        weekday = (datetime.date.today() + datetime.timedelta(days=d)).weekday()
        if zh:
            name = ["今天", "明天"][d] if d < 2 else "周" + "一二三四五六日"[weekday]
            parts.append(f"{name}{sky_zh}{lo}到{hi}度")
        else:
            name = ["today", "tomorrow"][d] if d < 2 else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][weekday]
            parts.append(f"{name} {sky_en} {lo}-{hi}")
    return (f"{place}这几天：" + "，".join(parts) + "。") if zh else (f"{place} this week: " + "; ".join(parts) + ".")


def describe(place: str, data: dict, day: int, zh: bool) -> str:
    daily = data["daily"]
    code = daily["weather_code"][day]
    sky_zh, sky_en = CODES.get(code, ("天气多变", "changeable"))
    low, high = round(daily["temperature_2m_min"][day]), round(daily["temperature_2m_max"][day])
    rain = daily.get("precipitation_probability_max", [None] * 7)[day]
    weekday = (datetime.date.today() + datetime.timedelta(days=day)).weekday()
    if zh:
        when = ["今天", "明天", "后天"][day] if day < 3 else "周" + "一二三四五六日"[weekday]
        text = f"{place}{when}{sky_zh}，{low}到{high}度"
        if day == 0 and data.get("current"):
            text += f"，现在{round(data['current']['temperature_2m'])}度"
        if rain is not None:
            text += f"，下雨概率{rain}%"
        return text + "。"
    when = (["today", "tomorrow", "the day after tomorrow"][day] if day < 3
            else ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday])
    text = f"{place} {when}: {sky_en}, {low} to {high} degrees"
    if day == 0 and data.get("current"):
        text += f", {round(data['current']['temperature_2m'])} now"
    if rain is not None:
        text += f", {rain}% chance of rain"
    return text + "."


def parse(text: str) -> tuple[str | None, int] | None:
    """(city or None, day offset) if this asks about the weather."""
    if not _ASK.search(text) or _EXPLICIT_SEARCH.match(text):
        return None  # "百度一下天气" asks for the browser, not an answer
    day = next((d for word, d in _DAY.items() if word in text.lower()), 0)
    today = datetime.date.today().weekday()
    if _AIR_WORDS.search(text):
        day = AIR
    elif _SUN_WORDS.search(text):
        day = SUN
    elif re.search(r"周末|weekend", text, re.I):
        day = WEEKEND
    elif _WEEK_WORDS.search(text):
        day = WEEK
    elif m := re.search(r"(?:周|星期|礼拜)([一二三四五六日天])(?!气)", text):  # "这周天气" isn't Sunday
        day = (_WEEKDAY[m.group(1)] - today) % 7
    elif m := re.search("|".join(_WEEKDAY_EN), text, re.I):
        day = (_WEEKDAY_EN[m.group(0).lower()] - today) % 7
    text = _LEAD_IN.sub("", text)
    city = None
    m = _CITY_ZH.match(text) or _CITY_EN.search(text)
    if m:
        name = _WHEN.sub("", m.group("city")).strip()
        if len(name) >= 2 and name not in _NOT_CITY:
            city = name
    return city, day


class Weather(Skill):
    name = "weather"

    def handle(self, text: str, ctx: Context) -> str | None:
        parsed = parse(text)
        if parsed is None:
            return None
        return self.report(*parsed, ctx)

    def report(self, city: str | None, day: int, ctx: Context) -> str:
        city = city or self.config.get("weather", {}).get("city") or None
        try:
            place = locate(city, ctx.zh)
            if place is None:
                return ctx.reply(f"没找到叫{city}的地方。", f"I couldn't find a place called {city}.")
            name, lat, lon = place
            if day == AIR:
                return air(name, lat, lon, ctx.zh)
            data = forecast(lat, lon)
            if day == SUN:
                rise, sset = data["daily"]["sunrise"][0][-5:], data["daily"]["sunset"][0][-5:]
                return ctx.reply(f"{name}今天 {rise} 日出，{sset} 日落。", f"In {name} the sun rises at {rise} and sets at {sset} today.")
            if day == WEEK:
                return week(name, data, ctx.zh)
            if day == WEEKEND:
                today = datetime.date.today().weekday()
                days = [0, 1] if today == 5 else [0] if today == 6 else [5 - today, 6 - today]
                return " ".join(describe(name if i == 0 else "", data, d, ctx.zh) for i, d in enumerate(days))
            return describe(name, data, min(max(int(day), 0), 6), ctx.zh)
        except OSError:
            return ctx.reply("现在查不到天气，请检查网络。", "I can't get the weather right now. Check the internet.")

    def tools(self) -> list[Tool]:
        return [Tool(
            "get_weather",
            "Current weather and the forecast for today, tomorrow or the day after. Answer "
            "from this; don't open a browser for the weather. Leave `city` empty for where "
            "the user is.",
            schema({"city": {"type": "string"},
                    "day": {"type": "integer", "minimum": 0, "maximum": 6,
                            "description": "days from today: 0 today, 1 tomorrow … 6"}}),
            lambda args, ctx: self.report((args.get("city") or "").strip() or None,
                                          int(args.get("day") or 0), ctx),
        )]
