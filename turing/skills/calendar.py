"""Time in other cities, and date questions: "北京现在几点", "离圣诞节还有几天",
"下周五是几号", "12月25号是星期几"."""

import datetime as dt
import re

from ..numbers import parse_number
from . import Context, Skill, Tool, schema

# city -> (UTC offset in hours, daylight saving rule)
CITIES = {
    "北京": (8, None), "上海": (8, None), "广州": (8, None), "深圳": (8, None), "成都": (8, None), "中国": (8, None),
    "香港": (8, None), "台北": (8, None), "新加坡": (8, None), "东京": (9, None), "日本": (9, None),
    "首尔": (9, None), "韩国": (9, None), "曼谷": (7, None), "新德里": (5.5, None), "印度": (5.5, None),
    "迪拜": (4, None), "莫斯科": (3, None), "伦敦": (0, "eu"), "英国": (0, "eu"), "巴黎": (1, "eu"),
    "柏林": (1, "eu"), "罗马": (1, "eu"), "马德里": (1, "eu"), "多伦多": (-5, "na"), "奥克维尔": (-5, "na"),
    "纽约": (-5, "na"), "蒙特利尔": (-5, "na"), "温哥华": (-8, "na"), "洛杉矶": (-8, "na"), "旧金山": (-8, "na"),
    "西雅图": (-8, "na"), "芝加哥": (-6, "na"), "卡尔加里": (-7, "na"), "悉尼": (10, "au"), "墨尔本": (10, "au"),
    "澳洲": (10, "au"), "奥克兰": (12, "nz"),
    "beijing": (8, None), "shanghai": (8, None), "hong kong": (8, None), "singapore": (8, None),
    "tokyo": (9, None), "seoul": (9, None), "delhi": (5.5, None), "dubai": (4, None), "moscow": (3, None),
    "london": (0, "eu"), "paris": (1, "eu"), "berlin": (1, "eu"), "toronto": (-5, "na"), "oakville": (-5, "na"),
    "new york": (-5, "na"), "montreal": (-5, "na"), "vancouver": (-8, "na"), "los angeles": (-8, "na"),
    "san francisco": (-8, "na"), "chicago": (-6, "na"), "sydney": (10, "au"), "melbourne": (10, "au"),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th weekday (0=Mon) of a month; n=-1 is the last."""
    if n > 0:
        first = dt.date(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _dst(rule: str | None, utc: dt.datetime) -> bool:
    if rule is None:
        return False
    y = utc.year
    if rule == "na":   # 2nd Sunday of March to 1st Sunday of November, 2 am local (~7-10 UTC)
        start = dt.datetime.combine(_nth_weekday(y, 3, 6, 2), dt.time(10))
        end = dt.datetime.combine(_nth_weekday(y, 11, 6, 1), dt.time(9))
        return start <= utc < end
    if rule == "eu":   # last Sunday of March to last Sunday of October, 1 am UTC
        start = dt.datetime.combine(_nth_weekday(y, 3, 6, -1), dt.time(1))
        end = dt.datetime.combine(_nth_weekday(y, 10, 6, -1), dt.time(1))
        return start <= utc < end
    if rule in ("au", "nz"):  # southern summer: from 1st (NZ last) Sunday of Sep/Oct to 1st Sunday of April
        end = dt.datetime.combine(_nth_weekday(y, 4, 6, 1), dt.time(16))
        start = dt.datetime.combine(_nth_weekday(y, 10, 6, 1) if rule == "au" else _nth_weekday(y, 9, 6, -1), dt.time(16))
        return utc < end or utc >= start
    return False


def time_in(city: str, utc: dt.datetime | None = None) -> dt.datetime | None:
    entry = CITIES.get(city.strip().lower())
    if entry is None:
        return None
    utc = utc or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    offset, rule = entry
    return utc + dt.timedelta(hours=offset + (1 if _dst(rule, utc) else 0))


# Chinese holidays follow the lunar calendar: their dates for the next years.
_LUNAR = {"春节": ["2027-02-06", "2028-01-26", "2029-02-13"], "元宵节": ["2027-02-20", "2028-02-09"],
          "端午节": ["2027-06-09", "2028-05-28"], "七夕": ["2027-08-08", "2028-08-26"],
          "中秋节": ["2027-09-15", "2028-10-03"], "重阳节": ["2027-10-08", "2028-10-26"]}
_FIXED = {"元旦": (1, 1), "新年": (1, 1), "情人节": (2, 14), "愚人节": (4, 1), "劳动节": (5, 1),
          "儿童节": (6, 1), "加拿大国庆": (7, 1), "国庆节": (10, 1), "万圣节": (10, 31), "平安夜": (12, 24),
          "圣诞节": (12, 25), "圣诞": (12, 25), "christmas": (12, 25), "new year": (1, 1), "halloween": (10, 31),
          "valentine's day": (2, 14)}
_FLOATING = {"感恩节": (10, 0, 2), "thanksgiving": (10, 0, 2), "母亲节": (5, 6, 2), "mother's day": (5, 6, 2),
             "父亲节": (6, 6, 3), "father's day": (6, 6, 3)}  # month, weekday, n-th (Canada)


def holiday(name: str, today: dt.date) -> dt.date | None:
    name = name.strip().lower()
    if name in _LUNAR:
        return next((d for d in map(dt.date.fromisoformat, _LUNAR[name]) if d >= today), None)
    for table in (_FIXED, _FLOATING):
        if name in table:
            for year in (today.year, today.year + 1):
                if table is _FIXED:
                    d = dt.date(year, *table[name])
                else:
                    m, wd, n = table[name]
                    d = _nth_weekday(year, m, wd, n)
                if d >= today:
                    return d
    return None


_WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_CITY_TIME = re.compile(r"^(.+?)(?:现在|那边|那里)?(?:是)?几点(?:了|钟)?$|^what time is it in\s+(.+)$|^(?:the )?time in\s+(.+)$", re.I)
_UNTIL = re.compile(r"^(?:今天)?(?:离|距离|到)?(.+?)(?:还有|还剩)(?:几|多少)天$|^how many days (?:until|till|to)\s+(.+)$", re.I)
_WEEKDAY_DATE = re.compile(r"^(这|本|下|下下)(?:个)?(?:周|星期|礼拜)([一二三四五六日天])(?:是)?几号$")
_DATE_WEEKDAY = re.compile(r"^(\d{1,2}|[一二三四五六七八九十]+)月(\d{1,2}|[一二三四五六七八九十]+)(?:号|日)(?:是)?(?:星期|周|礼拜)几$")
_DATE_UNTIL = re.compile(r"^(?:离|距离|到)(\d{1,2}|[一二三四五六七八九十]+)月(\d{1,2}|[一二三四五六七八九十]+)(?:号|日)(?:还有|还剩)(?:几|多少)天$")


class Calendar(Skill):
    name = "calendar"

    def handle(self, text: str, ctx: Context) -> str | None:
        today = dt.date.today()
        if m := _UNTIL.match(text):
            name = next(g for g in m.groups() if g)
            when = holiday(name, today)
            return self.days_until(name, when, today, ctx) if when else None
        if m := _DATE_UNTIL.match(text):
            when = self._date(m.group(1), m.group(2), today)
            return self.days_until(f"{when.month}月{when.day}日", when, today, ctx) if when else None
        if m := _WEEKDAY_DATE.match(text):
            weeks = {"这": 0, "本": 0, "下": 1, "下下": 2}[m.group(1)]
            monday = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=weeks)
            d = monday + dt.timedelta(days=_WEEK[m.group(2)])
            return ctx.reply(f"{m.group(1)}周{m.group(2)}是{d.month}月{d.day}日", f"That's {d:%B} {d.day}")
        if m := _DATE_WEEKDAY.match(text):
            d = self._date(m.group(1), m.group(2), today, future=False)
            if d:
                return ctx.reply(f"{d.year}年{d.month}月{d.day}日是星期{'一二三四五六日'[d.weekday()]}", f"{d:%B} {d.day}, {d.year} is a {d:%A}")
        if m := _CITY_TIME.match(text):
            city = next(g for g in m.groups() if g).strip()
            t = time_in(city)
            if t:
                return ctx.reply(f"{city}现在是{t.hour}点{t.minute:02d}分（{t.month}月{t.day}日）",
                                 f"It's {t:%H:%M} in {city.title()} ({t:%b} {t.day})")
        return None

    @staticmethod
    def _date(month: str, day: str, today: dt.date, future: bool = True) -> dt.date | None:
        try:
            d = dt.date(today.year, int(parse_number(month)), int(parse_number(day)))
        except (ValueError, TypeError):
            return None
        return d.replace(year=d.year + 1) if future and d < today else d

    def days_until(self, name: str, when: dt.date, today: dt.date, ctx: Context) -> str:
        days = (when - today).days
        if days == 0:
            return ctx.reply(f"今天就是{name}！", f"{name.title()} is today!")
        return ctx.reply(f"离{name}还有 {days} 天（{when.year}年{when.month}月{when.day}日，星期{'一二三四五六日'[when.weekday()]}）",
                         f"{days} days until {name} ({when:%A, %B} {when.day})")

    def tools(self) -> list[Tool]:
        return [Tool("time_in_city", "Current local time in a big city (Beijing, London, Tokyo, Toronto…).",
                     schema({"city": {"type": "string"}}, ["city"]),
                     lambda a, ctx: (lambda t: f"{t:%Y-%m-%d %H:%M}" if t else "Error: unknown city")(time_in(a["city"])))]
