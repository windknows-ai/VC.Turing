"""Facts that must come from a real source, never from the AI's memory: exchange rates
and today's news headlines."""

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ..numbers import parse_number
from . import Context, Skill, Tool, schema

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CURRENCIES = {"美元": "USD", "美金": "USD", "刀": "USD", "人民币": "CNY", "块钱": "CNY", "元": "CNY",
              "加元": "CAD", "加币": "CAD", "加拿大元": "CAD", "欧元": "EUR", "英镑": "GBP", "日元": "JPY",
              "港币": "HKD", "港元": "HKD", "韩元": "KRW", "澳元": "AUD", "新台币": "TWD", "台币": "TWD",
              "dollar": "USD", "dollars": "USD", "usd": "USD", "rmb": "CNY", "yuan": "CNY", "cny": "CNY",
              "cad": "CAD", "euro": "EUR", "euros": "EUR", "pound": "GBP", "pounds": "GBP", "yen": "JPY"}
NAMES = {"USD": ("美元", "US dollars"), "CNY": ("人民币", "yuan"), "CAD": ("加元", "Canadian dollars"),
         "EUR": ("欧元", "euros"), "GBP": ("英镑", "pounds"), "JPY": ("日元", "yen"), "HKD": ("港币", "HK dollars"),
         "KRW": ("韩元", "won"), "AUD": ("澳元", "Australian dollars"), "TWD": ("新台币", "NT dollars")}
_CUR = "|".join(sorted(map(re.escape, CURRENCIES), key=len, reverse=True))
_RATE = re.compile(rf"^(?:现在)?([\d.一二三四五六七八九十百千万两]+)?\s*({_CUR})\s*(?:(?:等于|换|能换|兑换?|是|合)\s*多少|换成?|兑(?:换)?成?)\s*"
                   rf"({_CUR})|^({_CUR})(?:兑|对|换)?({_CUR})?(?:的)?汇率", re.I)
_RATE_EN = re.compile(rf"^(?:how much is |convert )?([\d.]+)?\s*({_CUR})\s*(?:in|to)\s*({_CUR})", re.I)
_NEWS = re.compile(r"^(?:今天|最近|最新)?(?:有)?(?:什么|哪些)?(.*?)(?:的)?(?:新闻|头条)(?:吗|呢)?$|^(?:what'?s (?:in )?the )?(?:latest )?(.*?)\s*news(?: today)?$", re.I)


def rate(src: str, dst: str) -> tuple[float, str]:
    """(rate, update time) from open.er-api.com."""
    data = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://open.er-api.com/v6/latest/{src}", headers=_HEADERS), timeout=10))
    if data.get("result") != "success" or dst not in data.get("rates", {}):
        raise RuntimeError("no rate")
    return data["rates"][dst], data.get("time_last_update_utc", "")


STOCKS = {"苹果": "AAPL", "apple": "AAPL", "特斯拉": "TSLA", "tesla": "TSLA", "微软": "MSFT", "microsoft": "MSFT",
          "谷歌": "GOOGL", "google": "GOOGL", "亚马逊": "AMZN", "amazon": "AMZN", "英伟达": "NVDA", "nvidia": "NVDA",
          "meta": "META", "脸书": "META", "奈飞": "NFLX", "netflix": "NFLX", "阿里巴巴": "BABA", "阿里": "BABA",
          "腾讯": "0700.HK", "tencent": "0700.HK", "京东": "JD", "百度": "BIDU", "拼多多": "PDD", "小米": "1810.HK",
          "比亚迪": "1211.HK", "茅台": "600519.SS", "贵州茅台": "600519.SS", "台积电": "TSM", "amd": "AMD",
          "英特尔": "INTC", "intel": "INTC", "可口可乐": "KO", "迪士尼": "DIS", "shopify": "SHOP", "加拿大皇家银行": "RY"}
COINS = {"比特币": "bitcoin", "bitcoin": "bitcoin", "btc": "bitcoin", "以太坊": "ethereum", "以太币": "ethereum",
         "ethereum": "ethereum", "eth": "ethereum", "狗狗币": "dogecoin", "dogecoin": "dogecoin",
         "索拉纳": "solana", "solana": "solana", "瑞波币": "ripple", "xrp": "ripple"}


_STOCK_NAMES = "|".join(sorted(map(re.escape, STOCKS), key=len, reverse=True))
_COIN_NAMES = "|".join(sorted(map(re.escape, COINS), key=len, reverse=True))
_STOCK = re.compile(rf"({_STOCK_NAMES})(?:公司)?(?:的)?(?:股票|股价)|^(?:what(?:'s| is) )?({_STOCK_NAMES})(?:'s)? (?:stock|share) price", re.I)
_COIN = re.compile(rf"({_COIN_NAMES})(?:现在)?(?:的)?(?:价格|多少钱|值多少|涨了|跌了)|^(?:what(?:'s| is) the price of |how much is )({_COIN_NAMES})", re.I)

COIN_NAMES = {"bitcoin": ("比特币", "Bitcoin"), "ethereum": ("以太坊", "Ethereum"), "dogecoin": ("狗狗币", "Dogecoin"),
              "solana": ("Solana", "Solana"), "ripple": ("瑞波币", "XRP")}


def stock(symbol: str) -> dict:
    meta = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1d",
        headers=_HEADERS), timeout=10))["chart"]["result"][0]["meta"]
    return {"name": meta.get("longName") or meta.get("shortName") or symbol, "price": meta["regularMarketPrice"],
            "currency": meta.get("currency", ""), "previous": meta.get("chartPreviousClose")}


def coin(coin_id: str) -> dict:
    data = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,cny&include_24hr_change=true",
        headers=_HEADERS), timeout=10))
    return data[coin_id]


def headlines(topic: str = "", zh: bool = True, limit: int = 5) -> list[str]:
    q = topic.strip() or ("新闻" if zh else "news")
    url = (f"https://www.bing.com/news/search?q={urllib.parse.quote(q)}&format=rss"
           f"&setlang={'zh-CN' if zh else 'en-CA'}")
    data = urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=10).read()
    titles = [re.sub(r"\s+", " ", i.findtext("title") or "").strip() for i in ET.fromstring(data).findall(".//item")]
    return [t for t in titles if t][:limit]


class Info(Skill):
    name = "info"

    def handle(self, text: str, ctx: Context) -> str | None:
        if m := (_RATE.match(text) or _RATE_EN.match(text)):
            g = m.groups()
            if len(g) == 5 and g[3]:
                amount, src, dst = 1, g[3], g[4] or "人民币"
            else:
                amount, src, dst = g[0], g[1], g[2]
            value = parse_number(str(amount)) if amount else 1
            return self.convert(value or 1, CURRENCIES[src.lower()], CURRENCIES[dst.lower()], ctx)
        if m := _STOCK.search(text):
            return self.quote(STOCKS[next(g for g in m.groups() if g).lower()], ctx)
        if m := _COIN.search(text):
            return self.crypto(COINS[next(g for g in m.groups() if g).lower()], ctx)
        if (m := _NEWS.match(text)) and len(text) <= 20:
            topic = next((g for g in m.groups() if g), "") or ""
            return self.news(re.sub(r"^(?:关于|有关)", "", topic), ctx)
        return None

    def convert(self, amount: float, src: str, dst: str, ctx: Context) -> str:
        if src == dst:
            return ctx.reply("这是同一种货币。", "That's the same currency.")
        try:
            r, when = rate(src, dst)
        except Exception:
            return ctx.reply("现在查不到汇率，可能是网络问题。", "I can't get the exchange rate right now.")
        n = f"{amount:g}"
        total = f"{amount * r:,.2f}"
        (zs, es), (zd, ed) = NAMES.get(src, (src, src)), NAMES.get(dst, (dst, dst))
        return ctx.reply(f"{n} {zs} 约等于 {total} {zd}（按今天的汇率）。", f"{n} {es} is about {total} {ed} at today's rate.")

    def quote(self, symbol: str, ctx: Context) -> str:
        try:
            q = stock(symbol)
        except Exception:
            return ctx.reply(f"现在查不到 {symbol} 的股价。", f"I can't get {symbol}'s price right now.")
        change = ""
        if q["previous"]:
            pct = (q["price"] - q["previous"]) / q["previous"] * 100
            change = ctx.reply(f"，比上个收盘{'涨' if pct >= 0 else '跌'}了 {abs(pct):.1f}%",
                               f", {'up' if pct >= 0 else 'down'} {abs(pct):.1f}% from the last close")
        return ctx.reply(f"{q['name']} 现在 {q['price']:,.2f} {q['currency']}{change}（行情可能有延迟）。",
                         f"{q['name']} is at {q['price']:,.2f} {q['currency']}{change} (quotes may be delayed).")

    def crypto(self, coin_id: str, ctx: Context) -> str:
        try:
            c = coin(coin_id)
        except Exception:
            return ctx.reply("现在查不到币价。", "I can't get that price right now.")
        ch = c.get("usd_24h_change") or 0
        zh_name, en_name = COIN_NAMES.get(coin_id, (coin_id, coin_id.title()))
        return ctx.reply(f"{zh_name} 现在约 {c['usd']:,.0f} 美元（{c['cny']:,.0f} 人民币），24 小时{'涨' if ch >= 0 else '跌'}了 {abs(ch):.1f}%。",
                         f"{en_name} is about ${c['usd']:,.0f}, {'up' if ch >= 0 else 'down'} {abs(ch):.1f}% in 24 hours.")

    def news(self, topic: str, ctx: Context) -> str:
        try:
            titles = headlines(topic, ctx.zh)
        except Exception:
            return ctx.reply("现在拿不到新闻，可能是网络问题。", "I can't get the news right now.")
        if not titles:
            return ctx.reply("没找到相关新闻。", "No news found.")
        return ctx.reply("最新的几条：" + "；".join(titles[:3]) + "。", "Top stories: " + "; ".join(titles[:3]) + ".")

    def tools(self) -> list[Tool]:
        return [
            Tool("exchange_rate", "Convert money between currencies at today's rate (ISO codes like USD, CNY, CAD).",
                 schema({"amount": {"type": "number"}, "from": {"type": "string"}, "to": {"type": "string"}},
                        ["from", "to"]),
                 lambda a, ctx: self.convert(float(a.get("amount") or 1), a["from"].upper()[:3], a["to"].upper()[:3], ctx)),
            Tool("stock_price", "Current stock price by ticker symbol (AAPL, TSLA, 0700.HK, 600519.SS…).",
                 schema({"symbol": {"type": "string"}}, ["symbol"]), lambda a, ctx: self.quote(a["symbol"].strip().upper(), ctx)),
            Tool("crypto_price", "Current price of a cryptocurrency by CoinGecko id (bitcoin, ethereum, dogecoin…).",
                 schema({"coin": {"type": "string"}}, ["coin"]), lambda a, ctx: self.crypto(a["coin"].strip().lower(), ctx)),
            Tool("news", "Today's news headlines, optionally about a topic.",
                 schema({"topic": {"type": "string"}}), lambda a, ctx: self.news(a.get("topic") or "", ctx)),
        ]
