"""Searching inside a particular app or site ("在抖音搜张大仙", "search YouTube for lofi").

Many apps can't be driven from outside (the 抖音 desktop app hides its whole interface
from accessibility tools), and typing blindly lands in whatever window happens to be in
front. So a search opens the site's own results page instead: it works every time, and
Turing can say truthfully what it did. A few desktop apps take a search link directly.
"""

import re
import urllib.parse
import winreg
from dataclasses import dataclass


@dataclass
class Site:
    name: str           # what to call it
    url: str            # results page, {query} replaced
    aliases: tuple      # what users call it, lowercase
    app_url: str = ""   # link the desktop app itself handles, if installed
    app_protocol: str = ""
    no_app_search: bool = False  # the desktop app exists but can't be told to search


SITES = [
    Site("抖音", "https://www.douyin.com/search/{query}", ("抖音", "douyin"), no_app_search=True),
    Site("B站", "https://search.bilibili.com/all?keyword={query}", ("b站", "哔哩哔哩", "bilibili", "bili")),
    Site("YouTube", "https://www.youtube.com/results?search_query={query}", ("youtube", "油管")),
    Site("小红书", "https://www.xiaohongshu.com/search_result?keyword={query}",
         ("小红书", "rednote", "xiaohongshu")),
    Site("淘宝", "https://s.taobao.com/search?q={query}", ("淘宝", "taobao")),
    Site("京东", "https://search.jd.com/Search?keyword={query}", ("京东", "jd")),
    Site("知乎", "https://www.zhihu.com/search?q={query}", ("知乎", "zhihu")),
    Site("微博", "https://s.weibo.com/weibo?q={query}", ("微博", "weibo")),
    Site("百度", "https://www.baidu.com/s?wd={query}", ("百度", "baidu")),
    Site("谷歌", "https://www.google.com/search?q={query}", ("谷歌", "google")),
    Site("必应", "https://www.bing.com/search?q={query}", ("必应", "bing")),
    Site("GitHub", "https://github.com/search?q={query}", ("github",)),
    Site("网易云音乐", "https://music.163.com/#/search/m/?s={query}", ("网易云音乐", "网易云")),
    Site("QQ音乐", "https://y.qq.com/n/ryqq/search?w={query}", ("qq音乐", "qq music")),
    Site("Spotify", "https://open.spotify.com/search/{query}", ("spotify", "声破天"),
         app_url="spotify:search:{query}", app_protocol="spotify"),
    Site("Steam", "https://store.steampowered.com/search/?term={query}", ("steam",),
         app_url="steam://openurl/https://store.steampowered.com/search/?term={query}",
         app_protocol="steam"),
]

MUSIC = {"网易云音乐", "QQ音乐", "Spotify", "YouTube"}

# Chatbots whose web page takes the question in the link and sends it by itself.
BOTS = [
    Site("ChatGPT", "https://chatgpt.com/?q={query}", ("chatgpt", "chat gpt", "gpt")),
    Site("Claude", "https://claude.ai/new?q={query}", ("claude",)),
    Site("Perplexity", "https://www.perplexity.ai/search?q={query}", ("perplexity",)),
]
_BOT_NAMES = "|".join(sorted((re.escape(a) for s in BOTS for a in s.aliases), key=len, reverse=True))
_ASK = r"(?:问一下|问问|问|请教一下|请教)"
_BOT_PATTERNS = [
    # 帮我问一下ChatGPT今天出门要准备什么 / 问问 claude …
    re.compile(rf"^(?:.*?(?:用|打开|在|去))?.*?{_ASK}\s*(?:一下)?\s*({_BOT_NAMES})\s*[，,:：]?\s*(.+)$"),
    # 用ChatGPT问一下今天的天气 / 在浏览器里用 chatgpt 问…
    re.compile(rf"^.*?(?:用|打开|在|去)\s*({_BOT_NAMES})\s*(?:里|上|里面)?\s*(?:然后|并且|再)?\s*"
               rf"(?:帮我)?\s*{_ASK}\s*(?:一下|它|他)?\s*[，,:：]?\s*(.+)$"),
    # ChatGPT然后问一下他今天要准备什么
    re.compile(rf"^(?:打开|用)?\s*({_BOT_NAMES})\s*[，,]?\s*(?:然后|并且|再)?\s*(?:帮我)?\s*{_ASK}\s*"
               rf"(?:一下)?\s*[，,:：]?\s*(.+)$"),
    # ask chatgpt what to wear today
    re.compile(rf"^(?:please\s+)?ask\s+({_BOT_NAMES})\s*(?:about|whether|if|for)?\s*[,:]?\s*(.+)$"),
]


def parse_ask(text: str) -> tuple[Site, str] | None:
    """'帮我问一下ChatGPT今天出门要准备什么' -> (ChatGPT, '今天出门要准备什么')."""
    text = text.strip()
    for pattern in _BOT_PATTERNS:
        m = pattern.match(text)
        if m:
            question = re.sub(r"^(?:他|她|它|一下)\s*", "", m.group(2)).strip(" ，,。")
            bot = next(s for s in BOTS if m.group(1).lower() in s.aliases)
            return (bot, question) if question else None
    return None


def find_bot(name: str) -> Site | None:
    name = name.strip().lower()
    return next((s for s in BOTS if name in s.aliases or name == s.name.lower()), None)

_NAMES = "|".join(sorted((re.escape(a) for s in SITES for a in s.aliases), key=len, reverse=True))
_VERB = r"(?:帮我|给我|替我)?\s*(?:搜索|搜一搜|搜一下|搜搜|搜|查找|查一下|查|找一下|找)\s*(?:一下)?\s*"
_PATTERNS = [
    # 打开抖音然后搜索张大仙 / 抖音搜张大仙
    re.compile(rf"^(?:打开|开)?\s*({_NAMES})\s*(?:app|应用)?\s*[，,、]?\s*(?:然后|并且|再|并)?\s*{_VERB}(.+)$"),
    # 在抖音上搜张大仙 / 去B站找…
    re.compile(rf"^(?:在|去|到|用|上)\s*({_NAMES})\s*(?:上面|里面|上|里|中)?\s*{_VERB}(.+)$"),
    # open youtube and search for lofi / youtube search lofi
    re.compile(rf"^(?:open\s+)?({_NAMES})\s*,?\s*(?:and\s+)?(?:then\s+)?search(?:\s+for)?\s+(.+)$"),
    # search youtube for lofi
    re.compile(rf"^search\s+({_NAMES})\s+for\s+(.+)$"),
]
# search for lofi on youtube (query first)
_QUERY_FIRST = re.compile(rf"^(?:search|look)(?:\s+up)?(?:\s+for)?\s+(.+?)\s+(?:on|in)\s+({_NAMES})$")


def find_site(name: str) -> Site | None:
    name = name.strip().lower()
    return next((s for s in SITES if name in s.aliases or name == s.name.lower()), None)


def parse(text: str) -> tuple[Site, str] | None:
    """'打开抖音然后帮我搜索一下张大仙' -> (抖音, '张大仙')."""
    text = text.strip().rstrip("。.!！?？ ")
    for pattern in _PATTERNS:
        m = pattern.match(text)
        if m:
            site, query = m.group(1), m.group(2)
            break
    else:
        m = _QUERY_FIRST.match(text)
        if not m:
            return None
        query, site = m.group(1), m.group(2)
    query = query.strip(" ，,。")
    return (find_site(site), query) if query else None


def _registered(protocol: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, protocol))
        return True
    except OSError:
        return False


def link(site: Site, query: str) -> tuple[str, bool]:
    """The address to open, and whether it opens in the site's own desktop app."""
    q = urllib.parse.quote(query)
    if site.app_url and _registered(site.app_protocol):
        return site.app_url.replace("{query}", q), True
    return site.url.replace("{query}", q), False
