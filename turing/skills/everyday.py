"""Playing things, maps and email.

- "播放周杰伦的晴天" / "在YouTube上放lofi" / "B站播放影视飓风最新的视频": find the video and
  open it, so it actually plays (not just a list of results).
- "附近有什么好吃的" / "去多伦多怎么走": Google Maps search or directions.
- "给老师发邮件说我明天请假": a ready email draft; the user checks it and sends it.
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request
import webbrowser
import winreg

from . import Context, Skill, Tool, schema

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/141.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def _get(url: str, **headers) -> str:
    req = urllib.request.Request(url, headers={**_HEADERS, **headers})
    return urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")


def youtube_first(query: str, newest: bool = False) -> tuple[str, str] | None:
    """(watch URL, title) of the top YouTube result."""
    sort = "&sp=CAI%253D" if newest else ""
    page = _get(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}{sort}")
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', page)
    if not m:
        return None
    try:
        title = json.loads(f'"{m.group(2)}"')  # the title is JSON-escaped (& …)
    except ValueError:
        title = m.group(2)
    return f"https://www.youtube.com/watch?v={m.group(1)}", title


def bilibili_first(query: str, newest: bool = False) -> tuple[str, str] | None:
    order = "&order=pubdate" if newest else ""
    page = _get(f"https://search.bilibili.com/all?keyword={urllib.parse.quote(query)}{order}",
                Referer="https://www.bilibili.com")
    m = re.search(r"(BV[0-9A-Za-z]{10})", page)
    if not m:
        return None
    t = re.search(re.escape(m.group(1)) + r'.{0,400}?title="([^"]+)"', page, re.S)
    return f"https://www.bilibili.com/video/{m.group(1)}", html.unescape(t.group(1)) if t else ""


_SITE = r"(?:在|用|上|去)?\s*(youtube|油管|b站|哔哩哔哩|bilibili)\s*(?:上|里)?"
_PLAY_VERB = r"(?:播放|放一?首|放一?个|放一下|放点|放|看一?下|看|来一?首|听一?下|听)"
_PLAY_ON = re.compile(rf"^(?:打开)?{_SITE}\s*(?:然后|再)?\s*(?:帮我)?\s*{_PLAY_VERB}\s*(.+)$|"
                      rf"^(?:帮我)?\s*{_PLAY_VERB}\s*(.+?)\s*(?:在|用)\s*(youtube|油管|b站|哔哩哔哩|bilibili)(?:上|里)?$|"
                      r"^play\s+(.+?)\s+on\s+(youtube|bilibili)$", re.I)
_PLAY = re.compile(rf"^(?:帮我|给我)?\s*(?:播放|放一首|放首|放点|放一些|来一首|来点|我想听|听一首|听点)\s*(.+)$|^play (?:some |me )?(.+)$", re.I)
# Plain "play"/"pause" etc. belong to the media keys, and music apps by name to their own search.
_NOT_A_TITLE = re.compile(r"^(?:音乐|歌|视频|一下|吧|下一首|上一首|music|it|the music|again)$|网易云|qq音乐|spotify|酷狗|酷我", re.I)

_NEAR = re.compile(r"^(?:我)?(?:附近|周围|离我最近)(?:有)?(?:什么|哪些|的)?(?:好吃的|吃的|餐厅|饭店)(?:吗|呢)?$|"
                   r"^(?:离我最近|附近)的(.+?)(?:在哪(?:里|儿)?)?$|^(.+?)\s*near me$|^(?:find )?(?:a |the nearest )?(.+?) nearby$", re.I)
_ROUTE = re.compile(r"^(?:去|到)(.+?)怎么走$|^怎么(?:去|到)(.+)$|^(?:导航|带我)(?:去|到)(.+)$|"
                    r"^(?:how (?:do i|can i|to) get to|directions to|navigate to)\s+(.+)$", re.I)
_EMAIL = re.compile(r"^(?:帮我)?(?:给|向)(.+?)(?:发|写)(?:一封)?(?:邮件|电子邮件|email)(?:[，,]?\s*(?:说|告诉他|告诉她|内容是)\s*(.+))?$|"
                    r"^(?:帮我)?(?:写|发)(?:一封)?(?:邮件|email)(?:给|to)\s*(.+?)(?:[，,]?\s*(?:说|内容是)\s*(.+))?$|"
                    r"^(?:send|write) an? email to\s+(.+?)(?:\s+(?:saying|about)\s+(.+))?$", re.I)
_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def mail_app() -> bool:
    """Is a mail program set up for email links?"""
    key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return bool(winreg.QueryValueEx(k, "ProgId")[0])
    except OSError:
        return False


class Everyday(Skill):
    name = "everyday"

    def handle(self, text: str, ctx: Context) -> str | None:
        if m := _PLAY_ON.match(text):
            g = [x for x in m.groups() if x]
            site, query = (g[0], g[1]) if g[0].lower() in ("youtube", "油管", "b站", "哔哩哔哩", "bilibili") else (g[1], g[0])
            return self.play(query, "bilibili" if site.lower() in ("b站", "哔哩哔哩", "bilibili") else "youtube", ctx)
        if (m := _PLAY.match(text)) and not _NOT_A_TITLE.search(next(g for g in m.groups() if g).strip()):
            return self.play(next(g for g in m.groups() if g), "youtube", ctx)
        if m := _ROUTE.match(text):
            return self.directions(next(g for g in m.groups() if g), ctx)
        if m := _NEAR.match(text):
            what = next((g for g in m.groups() if g), None) or ctx.reply("餐厅", "restaurants")
            return self.nearby(what, ctx)
        if m := _EMAIL.match(text):
            g = m.groups()
            pairs = [(g[i], g[i + 1]) for i in (0, 2, 4) if g[i]]
            return self.email(*pairs[0], ctx) if pairs else None
        return None

    def play(self, query: str, site: str, ctx: Context) -> str:
        query = re.sub(r"^(?:一首|一个|一下|点|些)|(?:的视频|的歌|这首歌)$", "", query.strip(" 。.")).strip()
        newest = bool(re.search(r"最新|latest|newest", query, re.I))
        query = re.sub(r"最新(?:的)?|(?:the )?latest|newest", "", query, flags=re.I).strip() or query
        try:
            found = bilibili_first(query, newest) if site == "bilibili" else youtube_first(query, newest)
        except Exception:
            found = None
        name = "B站" if site == "bilibili" else "YouTube"
        if not found:
            return ctx.reply(f"在{name}上没找到“{query}”。", f"Nothing found on {name} for \"{query}\".")
        url, title = found
        webbrowser.open(url)
        shown = f"《{title}》" if title else ctx.reply(f"“{query}”", f"\"{query}\"")
        return ctx.reply(f"正在{name}播放{shown}", f"Playing {title or query} on {name}")

    def nearby(self, what: str, ctx: Context) -> str:
        webbrowser.open(f"https://www.google.com/maps/search/{urllib.parse.quote(what + ' near me')}")
        return ctx.reply(f"已在谷歌地图里打开附近的{what}", f"Opened {what} near you in Google Maps")

    def directions(self, place: str, ctx: Context) -> str:
        place = place.strip(" 。.?？")
        webbrowser.open(f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(place)}")
        return ctx.reply(f"已在谷歌地图里打开去{place}的路线", f"Opened directions to {place} in Google Maps")

    def email(self, to: str, body: str | None, ctx: Context) -> str:
        found = _ADDRESS.search(to)
        address = found.group(0) if found else ""
        body = (body or "").strip(" 。.")
        subject = body[:20] if body else ""
        if mail_app():
            os.startfile("mailto:" + urllib.parse.quote(address) + "?" + urllib.parse.urlencode(
                {"subject": subject, "body": body}, quote_via=urllib.parse.quote))
            where = ctx.reply("邮件程序", "your mail app")
        else:
            webbrowser.open("https://mail.google.com/mail/?view=cm&" + urllib.parse.urlencode(
                {"to": address, "su": subject, "body": body}, quote_via=urllib.parse.quote))
            where = "Gmail"
        who = address or to
        missing = ctx.reply("，收件人地址请你填上" if not address else "", " (add the recipient's address)" if not address else "")
        return ctx.reply(f"已在{where}里写好给{who}的邮件草稿{missing}，你检查一下再点发送。",
                         f"Drafted an email to {who} in {where}{missing}; check it and press Send.")

    def tools(self) -> list[Tool]:
        return [
            Tool("play_video", "Play a song or video (by title, artist or topic) on YouTube or bilibili: finds "
                 "it and opens it playing. site: youtube or bilibili. newest: the latest upload.",
                 schema({"query": {"type": "string"}, "site": {"type": "string", "enum": ["youtube", "bilibili"]},
                         "newest": {"type": "boolean"}}, ["query"]),
                 lambda a, ctx: self.play(a["query"] + (" 最新" if a.get("newest") else ""), a.get("site") or "youtube", ctx)),
            Tool("maps", "Google Maps: places near the user (`nearby`), or directions to a place (`to`).",
                 schema({"nearby": {"type": "string"}, "to": {"type": "string"}}),
                 lambda a, ctx: self.directions(a["to"], ctx) if a.get("to") else self.nearby(a.get("nearby") or "restaurants", ctx)),
            Tool("email_draft", "Open a ready email draft (the user checks it and sends it themselves).",
                 schema({"to": {"type": "string"}, "body": {"type": "string"}}, ["to"]),
                 lambda a, ctx: self.email(a["to"], a.get("body"), ctx)),
        ]
