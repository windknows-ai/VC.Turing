"""Time, date, and countdown timers."""

import datetime as dt
import re
import threading

from ..numbers import NUMBER, parse_number
from . import Context, Skill, Tool, schema

_TIME = re.compile(r"^((现在)?(几点(了|钟)?|什么时间|时间是?多少)|报时|"
                   r"what time is it|what('s| is) the time( now)?)$")
_DATE = re.compile(r"^((今天|现在)?(是)?(几号|几月几号|星期几|周几|礼拜几|什么日子|日期)|"
                   r"what('s| is) (the date|today('s date)?)|what day is (it|today))$")
# "10分钟", "一个半小时", "半个小时", "5 minutes"
_DURATION = re.compile(
    rf"{NUMBER}\s*(?:个)?(半)?(?:个)?\s*(小时|钟头|分钟|分|秒钟|秒|hours?|minutes?|mins?|seconds?|secs?)(?![a-z])"
)
_TIMER_WORD = re.compile(r"计时|倒计时|定时|提醒|叫我|叫醒|闹钟|番茄钟|timer|remind|wake me|alarm|pomodoro")
_LIST = re.compile(r"^(?:计时器?|倒计时|提醒|闹钟)?(?:还剩|还有)(?:多久|多少时间)|^有(?:哪些|什么|几个)(?:提醒|计时器?|闹钟)|"
                   r"^(?:how (?:much|long) (?:time )?(?:is )?left|what (?:timers|reminders) (?:are|do i have))", re.I)
_POMODORO = re.compile(r"番茄钟|pomodoro", re.I)
_CANCEL_ALL = re.compile(r"^取消所有(?:的)?(?:提醒|计时器?|闹钟)$|^cancel all (?:timers|reminders|alarms)$", re.I)
# "明天早上7点", "下午3点半", "晚上十点二十", "at 7:30 am tomorrow"
_AT = re.compile(rf"(今天|明天|后天)?\s*(凌晨|早上|早晨|上午|中午|下午|傍晚|晚上)?\s*{NUMBER}\s*[点:：]\s*"
                 rf"(半|一刻|三刻|{NUMBER}\s*分?)?")
_AT_EN = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.I)
_WHAT = re.compile(r"(?:提醒我|叫我|remind me to)\s*(?:去|要|该)?\s*(.+)$", re.I)
_CANCEL = re.compile(r"^(取消|关掉|停止)(计时器?|倒计时|定时器?|提醒)$|^cancel (the )?timers?$")

_WEEKDAYS_ZH = "一二三四五六日"


def _unit_seconds(unit: str) -> int:
    if unit.startswith(("小时", "钟头", "hour")):
        return 3600
    if unit.startswith(("分", "min")):
        return 60
    return 1


def parse_duration(text: str) -> float | None:
    """Total seconds in a phrase like "1小时30分钟" or "5 minutes", or None."""
    total, found = 0.0, False
    for m in _DURATION.finditer(text):
        amount, half, unit = parse_number(m.group(1)), m.group(2), m.group(3)
        total += (amount + (0.5 if half else 0)) * _unit_seconds(unit)
        found = True
    return total if found else None


def parse_time_of_day(text: str, now: dt.datetime) -> dt.datetime | None:
    """When "明天早上7点" / "下午3点半" / "at 7 pm tomorrow" is, or None."""
    english = re.search(r"[a-z]{2}", text, re.I) and _AT_EN.search(text)
    if not english and (m := _AT.search(text)):
        day, part, hour, minute = m.group(1), m.group(2), parse_number(m.group(3)), m.group(4)
        mins = {"半": 30, "一刻": 15, "三刻": 45}.get(minute or "", None)
        if mins is None:
            mins = int(parse_number(re.sub(r"\s*分$", "", minute))) if minute else 0
        hour = int(hour)
        if part in ("下午", "傍晚", "晚上") and hour < 12:
            hour += 12
        elif part == "中午" and hour < 6:
            hour += 12
        offset = {"明天": 1, "后天": 2}.get(day or "", 0)
    elif m := (english or _AT_EN.search(text)):
        hour, mins, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ampm.startswith("p") and hour < 12:
            hour += 12
        if ampm.startswith("a") and hour == 12:
            hour = 0
        offset = 1 if "tomorrow" in text.lower() else 0
    else:
        return None
    if not (0 <= hour < 24 and 0 <= mins < 60):
        return None
    when = (now + dt.timedelta(days=offset)).replace(hour=hour, minute=mins, second=0, microsecond=0)
    if when <= now and offset == 0:
        when += dt.timedelta(days=1)  # 7点 said at 9 pm means tomorrow
    return when


def describe(seconds: float, zh: bool) -> str:
    h, rest = divmod(round(seconds), 3600)
    m, s = divmod(rest, 60)
    if zh:
        return "".join(f"{v}{u}" for v, u in ((h, "小时"), (m, "分钟"), (s, "秒")) if v)
    return " ".join(f"{v} {u}{'s' if v > 1 else ''}"
                    for v, u in ((h, "hour"), (m, "minute"), (s, "second")) if v)


class Clock(Skill):
    name = "clock"

    def __init__(self, config):
        super().__init__(config)
        self._timers: list[threading.Timer] = []
        self._ends: dict[threading.Timer, tuple[dt.datetime, str]] = {}  # when each ends, and what for

    def handle(self, text: str, ctx: Context) -> str | None:
        now = dt.datetime.now()
        if _TIME.match(text):
            ampm = "AM" if now.hour < 12 else "PM"
            return ctx.reply(f"现在是{now.hour}点{now.minute:02d}分",
                             f"It's {now.hour % 12 or 12}:{now.minute:02d} {ampm}")
        if _DATE.match(text):
            return ctx.reply(f"今天是{now.month}月{now.day}日，星期{_WEEKDAYS_ZH[now.weekday()]}",
                             f"Today is {now:%A, %B} {now.day}")
        if _LIST.match(text):
            return self.list_timers(ctx)
        if _CANCEL.match(text) or _CANCEL_ALL.match(text):
            self._timers = [t for t in self._timers if t.is_alive()]
            if not self._timers:
                return ctx.reply("现在没有计时器", "There's no timer running")
            for t in self._timers:
                t.cancel()
            self._timers.clear()
            return ctx.reply("计时器已取消", "Timer cancelled")
        if _TIMER_WORD.search(text) and (when := parse_time_of_day(text, now)):
            return self._start_timer((when - now).total_seconds(), ctx, at=when, what=self._what(text))
        if _TIMER_WORD.search(text) and (seconds := parse_duration(text)):
            return self._start_timer(seconds, ctx, what=self._what(text) or
                                     (ctx.reply("番茄钟结束，休息一下吧", "pomodoro done, take a break")
                                      if _POMODORO.search(text) else ""))
        if _POMODORO.search(text):
            return self._start_timer(25 * 60, ctx, what=ctx.reply("番茄钟结束，休息一下吧", "pomodoro done, take a break"))
        return None

    @staticmethod
    def _what(text: str) -> str:
        m = _WHAT.search(text)
        what = m.group(1).strip(" 。.") if m else ""
        return "" if parse_duration(what) or _AT.search(what) else what

    def tools(self) -> list[Tool]:
        return [
            Tool("start_timer", "Start a countdown; Turing speaks up when it ends. `what` is what "
                 "to remind the user of.",
                 schema({"seconds": {"type": "integer", "minimum": 1}, "what": {"type": "string"}}, ["seconds"]),
                 lambda args, ctx: self._start_timer(int(args["seconds"]), ctx, what=args.get("what") or "")),
            Tool("set_alarm", "Remind the user at a time of day, e.g. \"明天早上7点\" or \"7:30 pm\".",
                 schema({"time": {"type": "string"}, "what": {"type": "string"}}, ["time"]),
                 lambda args, ctx: self._alarm(args["time"], args.get("what") or "", ctx)),
            Tool("list_timers", "Running timers and reminders, with the time left.", schema(),
                 lambda args, ctx: self.list_timers(ctx)),
            Tool("cancel_timers", "Cancel all running timers.", schema(),
                 lambda args, ctx: self.handle("取消计时器" if ctx.zh else "cancel timers", ctx)),
        ]

    def list_timers(self, ctx: Context) -> str:
        now = dt.datetime.now()
        live = sorted((end, what) for t, (end, what) in self._ends.items() if t.is_alive())
        if not live:
            return ctx.reply("现在没有计时器或提醒。", "No timers or reminders are running.")
        parts = []
        for end, what in live[:4]:
            left = describe(max(1, (end - now).total_seconds()), ctx.zh)
            parts.append(ctx.reply(f"“{what}”还剩{left}（{end:%H:%M}）", f"\"{what}\" in {left} ({end:%H:%M})"))
        return ctx.reply("；".join(parts) + "。", "; ".join(parts) + ".")

    def _alarm(self, spoken: str, what: str, ctx: Context) -> str:
        now = dt.datetime.now()
        when = parse_time_of_day(spoken, now)
        if when is None:
            return f"Error: couldn't read the time \"{spoken}\"; nothing was set."
        return self._start_timer((when - now).total_seconds(), ctx, at=when, what=what)

    def _start_timer(self, seconds: float, ctx: Context, at: dt.datetime | None = None, what: str = "") -> str:
        label = describe(seconds, ctx.zh)
        if what:
            done = ctx.reply(f"提醒你：{what}。", f"Reminder: {what}.")
        elif at:
            done = ctx.reply(f"{at.hour}点{at.minute:02d}分到了！", f"It's {at:%H:%M}!")
        else:
            done = ctx.reply(f"{label}的计时到了！", f"Your {label} timer is done!")
        timer = threading.Timer(seconds, ctx.say, args=(done,))
        timer.daemon = True
        timer.start()
        self._timers.append(timer)
        named = what or (ctx.reply(f"{at.hour}点{at.minute:02d}分的闹钟", f"{at:%H:%M} alarm") if at else label)
        self._ends[timer] = (dt.datetime.now() + dt.timedelta(seconds=seconds), named)
        if at:
            day = {0: "今天", 1: "明天", 2: "后天"}.get((at.date() - dt.date.today()).days, f"{at.month}月{at.day}日")
            day_en = {0: "today", 1: "tomorrow"}.get((at.date() - dt.date.today()).days, f"{at:%b %d}")
            return ctx.reply(f"好的，{day}{at.hour}点{at.minute:02d}分提醒你（图灵要一直开着才能提醒）",
                             f"OK, I'll remind you {day_en} at {at:%H:%M} (Turing needs to keep running)")
        return ctx.reply(f"好的，{label}后提醒你", f"OK, {label} timer started")
