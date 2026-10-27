"""Parse numbers the way people say them: "30", "三十", "二十五", "两", "半"."""

import re

_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000}
_EN = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
       "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
       "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
       "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}

NUMBER = r"(\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千]+|半|" + "|".join(_EN) + r")"


def cn_to_int(s: str) -> int:
    total, current = 0, 0
    for ch in s:
        if ch in _DIGITS:
            current = _DIGITS[ch]
        elif ch in _UNITS:
            total += (current or 1) * _UNITS[ch]
            current = 0
        else:
            raise ValueError(s)
    return total + current


def parse_number(s: str) -> float:
    s = s.strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    if s == "半":
        return 0.5
    if s in _EN:
        return float(_EN[s])
    return float(cn_to_int(s))
