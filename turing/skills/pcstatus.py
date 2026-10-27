"""How the PC is doing, read straight from the system: memory, CPU, disk space, network,
IP address, uptime, and which programs use the most memory."""

import datetime as dt
import json
import os
import re
import socket
import string
import urllib.request

import psutil

from . import Context, Skill, Tool, schema

_MEM = re.compile(r"内存|memory|ram", re.I)
_CPU = re.compile(r"cpu|处理器", re.I)
_DISK = re.compile(r"([a-zA-Z])\s*盘|硬盘|磁盘|空间|disk|drive|storage", re.I)
_NET = re.compile(r"^(?:现在)?有(?:没有)?网(?:络)?(?:吗|没)?$|^网(?:络)?(?:通|好)(?:了)?(?:吗|不通)?$|^(?:能|可以)上网吗$|^(?:am i|are we|is the (?:pc|computer)) (?:online|connected)", re.I)
_IP = re.compile(r"\bip\b|ip地址", re.I)
_UPTIME = re.compile(r"开机(?:了)?多久|开了多久|运行了多久|uptime|been on for", re.I)
_TOP = re.compile(r"(?:什么|哪个|哪些)(?:程序|软件|进程)(?:最)?(?:占|吃|用)(?:内存|cpu|资源)|最占内存|最吃内存|what(?:'s| is) using (?:the most )?(?:memory|ram|cpu)", re.I)
_ASK = re.compile(r"多少|几|还剩|多大|怎么样|吗|how much|how many|what", re.I)


def gb(n: float) -> str:
    return f"{n / 2**30:.1f}"


def online() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return True
    except OSError:
        return False


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packet is sent; just picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def public_ip() -> str | None:
    try:
        return json.load(urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5))["ip"]
    except Exception:
        return None


def top_memory(n: int = 3) -> list[tuple[str, float]]:
    """Programs by total memory (all their processes together), in GB."""
    totals: dict[str, float] = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (p.info["name"] or "").removesuffix(".exe")
            totals[name] = totals.get(name, 0) + p.info["memory_info"].rss
        except (psutil.Error, AttributeError):
            continue
    return [(k, v / 2**30) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])[:n]]


class PCStatus(Skill):
    name = "pcstatus"

    def handle(self, text: str, ctx: Context) -> str | None:
        if len(text) > (24 if re.search(r"[\u4e00-\u9fff]", text) else 60):
            return None
        if _TOP.search(text):
            return self.top(ctx)
        if _NET.search(text):
            return self.network(ctx)
        if _IP.search(text):
            return self.ip(ctx)
        if _UPTIME.search(text):
            return self.uptime(ctx)
        if not _ASK.search(text):
            return None
        if _MEM.search(text):
            return self.memory(ctx)
        if _CPU.search(text):
            return self.cpu(ctx)
        if m := _DISK.search(text):
            return self.disk(m.group(1), ctx)
        return None

    def memory(self, ctx: Context) -> str:
        v = psutil.virtual_memory()
        return ctx.reply(f"内存用了 {v.percent:.0f}%（{gb(v.used)} / {gb(v.total)} GB），还剩 {gb(v.available)} GB。",
                         f"Memory is {v.percent:.0f}% used ({gb(v.used)} of {gb(v.total)} GB); {gb(v.available)} GB free.")

    def cpu(self, ctx: Context) -> str:
        p = psutil.cpu_percent(interval=1.0)
        return ctx.reply(f"CPU 现在占用 {p:.0f}%。", f"The CPU is at {p:.0f}%.")

    def disk(self, letter: str | None, ctx: Context) -> str:
        drives = [f"{letter.upper()}:\\"] if letter else [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        parts = []
        for d in drives:
            try:
                u = psutil.disk_usage(d)
            except OSError:
                continue
            parts.append(ctx.reply(f"{d[0]} 盘还剩 {gb(u.free)} GB（共 {gb(u.total)} GB）", f"{d[0]}: {gb(u.free)} GB free of {gb(u.total)} GB"))
        if not parts:
            return ctx.reply(f"没有找到 {letter.upper()} 盘。" if letter else "没读到磁盘信息。",
                             f"There's no {letter.upper()}: drive." if letter else "Couldn't read the drives.")
        return ctx.reply("，".join(parts) + "。", "; ".join(parts) + ".")

    def network(self, ctx: Context) -> str:
        return ctx.reply("网络是通的。", "You're online.") if online() else ctx.reply("现在连不上网。", "You're offline right now.")

    def ip(self, ctx: Context) -> str:
        pub = public_ip()
        return ctx.reply(f"本机局域网 IP 是 {local_ip()}" + (f"，外网 IP 是 {pub}。" if pub else "。"),
                         f"Your local IP is {local_ip()}" + (f", public IP {pub}." if pub else "."))

    def uptime(self, ctx: Context) -> str:
        up = dt.datetime.now() - dt.datetime.fromtimestamp(psutil.boot_time())
        h, m = divmod(int(up.total_seconds()) // 60, 60)
        d, h = divmod(h, 24)
        zh = (f"{d} 天 " if d else "") + f"{h} 小时 {m} 分钟"
        en = (f"{d} days " if d else "") + f"{h} h {m} min"
        return ctx.reply(f"电脑已经开了 {zh}。", f"The PC has been on for {en}.")

    def top(self, ctx: Context) -> str:
        rows = top_memory()
        return ctx.reply("最占内存的是：" + "，".join(f"{n} {g:.1f} GB" for n, g in rows) + "。",
                         "Using the most memory: " + ", ".join(f"{n} {g:.1f} GB" for n, g in rows) + ".")

    def tools(self) -> list[Tool]:
        what = {"memory": self.memory, "cpu": self.cpu, "network": self.network, "ip": self.ip,
                "uptime": self.uptime, "top_programs": self.top}
        return [
            Tool("pc_status", "Read the PC's state: memory, cpu, network, ip, uptime, top_programs (by memory).",
                 schema({"what": {"type": "string", "enum": list(what)}}, ["what"]),
                 lambda a, ctx: what[a["what"]](ctx)),
            Tool("disk_space", "Free space on a drive letter, or all drives if empty.",
                 schema({"drive": {"type": "string"}}), lambda a, ctx: self.disk((a.get("drive") or "")[:1] or None, ctx)),
        ]
