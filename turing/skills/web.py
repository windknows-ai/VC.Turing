"""The web: look things up quietly for the AI, or open a search in the browser when asked."""

import re
import urllib.parse
import urllib.request
import webbrowser
from html.parser import HTMLParser

from . import Context, Skill, Tool, schema, sites

# Only explicit requests open the browser ("搜索…", "百度一下…", "用浏览器查…"). Plain
# questions ("查一下明天的天气") are answered by Turing itself instead.
_SEARCH = re.compile(
    r"^(?:用浏览器|在浏览器里?|在网上|上网)(?:搜索|搜一搜|搜一下|搜|查一下|查查|查)(?:一下)?\s*(.+)$"
    r"|^(?:搜索|搜一搜|搜一下|百度一下|百度|谷歌一下)\s*(.+)$"
    r"|^(?:search(?: the web| online| google)? for|google|search)\s+(.+)$"
)
# Asking about the screen is a different feature; leave those to the AI.
_SCREEN = re.compile(r"屏幕|界面|这个页面|当前页面|screen|this page")

DEFAULT_SEARCH = "https://www.bing.com/search?q={query}"
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def search_url(template: str, query: str) -> str:
    return template.replace("{query}", urllib.parse.quote(query))


class _BingResults(HTMLParser):
    """Pulls (title, snippet, url) out of a Bing results page."""

    def __init__(self):
        super().__init__()
        self.results: list[list[str]] = []
        self._in_result = 0      # depth inside <li class="b_algo">
        self._field = None       # "title" or "snippet" while inside one

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class") or ""
        if tag == "li" and "b_algo" in cls.split():
            self._in_result = 1
            self.results.append(["", "", ""])
        elif self._in_result:
            if tag == "li":
                self._in_result += 1
            elif tag == "h2":
                self._field = "title"
            elif tag == "a" and self._field == "title" and not self.results[-1][2]:
                self.results[-1][2] = attrs.get("href") or ""
            elif tag == "p" and not self.results[-1][1]:
                self._field = "snippet"

    def handle_endtag(self, tag):
        if not self._in_result:
            return
        if tag in ("h2", "p"):
            self._field = None
        elif tag == "li":
            self._in_result -= 1

    def handle_data(self, data):
        if self._in_result and self._field:
            i = 0 if self._field == "title" else 1
            self.results[-1][i] += data


def look_up(query: str, limit: int = 6) -> str:
    """Search results as plain text (titles and snippets), without opening a browser."""
    req = urllib.request.Request(search_url(DEFAULT_SEARCH + "&setlang=zh-CN", query),
                                 headers=_BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        page = r.read().decode("utf-8", errors="replace")
    parser = _BingResults()
    parser.feed(page)
    lines = [f"- {' '.join(t.split())}: {' '.join(s.split())} ({u})"
             for t, s, u in parser.results if t.strip() or s.strip()][:limit]
    return "\n".join(lines)[:3500] or "No results found."


class _PageText(HTMLParser):
    """Visible text of a page, skipping scripts, styles and navigation."""

    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(" ".join(data.split()))


def read_page(url: str, limit: int = 6000) -> str:
    """The main text of a web page, fetched in the background."""
    if not re.match(r"^https?://", url):
        raise ValueError("only http(s) pages")
    req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        page = r.read(2_000_000).decode(charset, errors="replace")
    parser = _PageText()
    parser.feed(page)
    # Keep lines long enough to be content rather than menu items.
    text = "\n".join(p for p in parser.parts if len(p) > 20)
    return text[:limit] or "The page has no readable text."


class Chatbots(Skill):
    """"问一下 ChatGPT …": checked before every other skill, since the question itself
    may be about the weather, the time, music…"""

    name = "chatbots"

    def handle(self, text: str, ctx: Context) -> str | None:
        if asked := sites.parse_ask(text):
            return Web(self.config)._ask_bot(asked[0], asked[1], ctx)
        return None


class Web(Skill):
    name = "web"

    @property
    def _template(self) -> str:
        return self.config.get("web", {}).get("search_url") or DEFAULT_SEARCH

    def handle(self, text: str, ctx: Context) -> str | None:
        if found := sites.parse(text):
            return self._search_site(found[0], found[1], ctx)
        m = _SEARCH.match(text)
        if not m or _SCREEN.search(text):
            return None
        query = next(g for g in m.groups() if g).strip()
        if not query:
            return None
        return self._search(query, ctx)

    def _search(self, query: str, ctx: Context) -> str:
        webbrowser.open(search_url(self._template, query))
        return ctx.reply(f"已在浏览器里搜索{query}", f"Searching the web for {query}")

    def _search_site(self, site: sites.Site, query: str, ctx: Context) -> str:
        import os

        url, in_app = sites.link(site, query)
        if in_app:
            os.startfile(url)
        else:
            webbrowser.open(url)
        if site.no_app_search:
            return ctx.reply(f"{site.name}电脑版没法直接让我搜索，已在浏览器里打开{site.name}搜索“{query}”的结果",
                             f"The {site.english} desktop app can't be searched from outside, so I opened "
                             f"its search results for {query} in the browser")
        where = "" if in_app else "在浏览器里"
        # Music: be clear it's a list of results, not playing yet.
        tail = ("，点一下就能播放" if ctx.zh else "; click one to play it") if site.name in sites.MUSIC else ""
        return ctx.reply(f"已{where}打开{site.name}搜索“{query}”的结果{tail}",
                         f"Opened {site.english} search results for {query}{tail}")

    def _ask_bot(self, bot: sites.Site, question: str, ctx: Context) -> str:
        url, _ = sites.link(bot, question)
        webbrowser.open(url)
        return ctx.reply(f"已在浏览器里打开 {bot.name}，问了“{question}”，答案会显示在网页上",
                         f"Asked {bot.name} \"{question}\" in the browser; the answer will be on the page")

    def _search_in(self, app: str, query: str, ctx: Context) -> str:
        site = sites.find_site(app)
        if site is None:
            known = "、".join(s.name for s in sites.SITES)
            return (f"Error: can't search inside {app} directly (nothing was done). It works "
                    f"for: {known}. Otherwise offer web_search, or open the app and let the "
                    f"user type the search.")
        return self._search_site(site, query, ctx)

    def _open(self, url: str, ctx: Context) -> str:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        if not re.match(r"^https?://[^\s/]+\.[^\s]+", url):
            raise ValueError(f"not a web address: {url}")
        webbrowser.open(url)
        return ctx.reply("已打开网页", "Opened the page")

    def tools(self) -> list[Tool]:
        return [
            Tool("look_up",
                 "Search the web quietly and get back result titles and snippets, to answer "
                 "questions that need current information (news, prices, scores, opening "
                 "hours, facts you're unsure of). Nothing opens on the user's screen. Prefer "
                 "this over web_search, and answer the user directly from what you find.",
                 schema({"query": {"type": "string"}}, ["query"]),
                 lambda args, ctx: look_up(args["query"])),
            Tool("read_web_page",
                 "Read the text of a web page in the background (e.g. a result from look_up "
                 "whose snippet wasn't enough). Nothing opens on the user's screen.",
                 schema({"url": {"type": "string"}}, ["url"]),
                 lambda args, ctx: read_page(args["url"].strip())),
            Tool("web_search",
                 "Open a search in the user's browser. Only when the user asks to see results "
                 "in the browser (\"搜索…\", \"用浏览器查…\", \"open a search for…\").",
                 schema({"query": {"type": "string"}}, ["query"]),
                 lambda args, ctx: self._search(args["query"], ctx)),
            Tool("search_in_app",
                 "Search inside a particular app or site and show the results: 抖音, B站, "
                 "YouTube, 小红书, 淘宝, 京东, 知乎, 微博, 网易云音乐, QQ音乐, Spotify, Steam, "
                 "百度, 谷歌, GitHub. Use this, not open_app + type_text, for \"打开抖音搜X\".",
                 schema({"app": {"type": "string"}, "query": {"type": "string"}}, ["app", "query"]),
                 lambda args, ctx: self._search_in(args["app"], args["query"].strip(), ctx)),
            Tool("ask_chatbot",
                 "Ask ChatGPT, Claude or Perplexity a question in the user's browser: it opens "
                 "the site with the question already sent. ONLY when the user names one of these "
                 "chatbots; otherwise answer (translate, explain…) yourself. Never open_website + type_text.",
                 schema({"bot": {"type": "string"}, "question": {"type": "string"}},
                        ["bot", "question"]),
                 lambda args, ctx: (self._ask_bot(bot, args["question"].strip(), ctx)
                                    if (bot := sites.find_bot(args["bot"]))
                                    else f"Error: can only ask {', '.join(b.name for b in sites.BOTS)}.")),
            Tool("open_website", "Open a website (http/https address) in the default browser.",
                 schema({"url": {"type": "string"}}, ["url"]),
                 lambda args, ctx: self._open(args["url"].strip(), ctx)),
        ]
