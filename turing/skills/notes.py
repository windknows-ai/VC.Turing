"""Notes and to-dos kept on this PC ("帮我记一下…", "加一个待办…", "我记了什么"), and what
Turing should call the user ("以后叫我小明")."""

import datetime as dt
import json
import re
import threading

from ..paths import DATA_DIR, write_text_safely
from . import Context, Skill, Tool, schema

FILE = DATA_DIR / "notes.json"
PROFILE = DATA_DIR / "profile.json"
_lock = threading.Lock()

_NOTE = re.compile(r"^(?:帮我|给我)?(?:记一下|记下|记住|记个笔记|做个笔记|备忘一下|备忘)[：:，,\s]*(.+)$"
                   r"|^(?:take a note|note down|remember)[:,]?\s*(?:that\s+)?(.+)$", re.I)
_TODO = re.compile(r"^(?:加|添加|新增|记)(?:一个|一条|个)?(?:待办|待办事项|任务|to-?do)[：:，,\s]*(.+)$"
                   r"|^add (?:a )?(?:to-?do|task)[:,]?\s*(.+)$", re.I)
_DONE = re.compile(r"^(?:完成|做完|划掉|删掉)(?:了)?(?:待办)?[：:，,\s]*(.+?)(?:这个待办|这件事)?$|^(?:mark|cross off)\s+(.+?)(?: as done)?$", re.I)
_LIST_NOTES = re.compile(r"^(?:我)?(?:记了|写了)(?:什么|哪些)|^(?:把)?(?:我的)?笔记(?:读给我听|念给我听|有哪些|是什么)|"
                         r"^(?:read|what are) my notes|^what did i note", re.I)
_LIST_TODOS = re.compile(r"^(?:我的)?(?:待办|待办事项|任务)(?:有哪些|有什么|是什么|清单)?$|^(?:我)?还有(?:什么|哪些)(?:事|待办)(?:没做)?|"
                         r"^(?:what are |read )?my (?:to-?dos|tasks)$", re.I)
_CLEAR = re.compile(r"^(?:清空|删除全部|删掉所有)(?:的)?(?:笔记|待办)$|^clear (?:all )?(?:my )?(?:notes|to-?dos)$", re.I)
_CALL_ME = re.compile(r"^(?:以后|今后)?(?:你)?(?:就)?(?:叫我|称呼我|喊我)\s*(.+?)(?:吧|就行|就好)?$|^call me\s+(.+)$", re.I)
_WHO_AM_I = re.compile(r"^我叫什么(?:名字)?$|^你(?:知道|记得)我(?:是谁|叫什么)|^what'?s my name$|^who am i$", re.I)


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(items: list[dict]):
    with _lock:
        write_text_safely(FILE, json.dumps(items, ensure_ascii=False, indent=1))


def profile() -> dict:
    """What Turing knows about the user: name, reply_language ('zh', 'en' or '')."""
    try:
        return json.loads(PROFILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_profile(**values):
    data = {**profile(), **values}
    write_text_safely(PROFILE, json.dumps(data, ensure_ascii=False))


def user_name() -> str:
    return profile().get("name", "")


def set_user_name(name: str):
    set_profile(name=name)


class Notes(Skill):
    name = "notes"

    def handle(self, text: str, ctx: Context) -> str | None:
        if m := _TODO.match(text):
            return self.add(next(g for g in m.groups() if g), "todo", ctx)
        if m := _NOTE.match(text):
            return self.add(next(g for g in m.groups() if g), "note", ctx)
        if _LIST_TODOS.match(text):
            return self.show("todo", ctx)
        if _LIST_NOTES.match(text):
            return self.show("note", ctx)
        if _CLEAR.match(text):
            return self.clear("todo" if re.search(r"待办|to-?do", text, re.I) else "note", ctx)
        if (m := _DONE.match(text)) and re.search(r"待办|to-?do|task", text, re.I) or (m and self._find(m)):
            return self.done(next(g for g in m.groups() if g), ctx)
        if m := _CALL_ME.match(text):
            name = next(g for g in m.groups() if g).strip(" 。.")
            if name.isascii():
                name = name.title()  # what was heard comes in lower case: "alex" -> "Alex"
            set_user_name(name)
            return ctx.reply(f"好的，以后叫你{name}", f"OK, I'll call you {name}")
        if _WHO_AM_I.match(text):
            name = user_name()
            return ctx.reply(f"你叫{name}。" if name else "你还没告诉我你叫什么。可以说“以后叫我……”。",
                             f"You're {name}." if name else "You haven't told me your name yet. Say \"call me …\".")
        return None

    def _find(self, m) -> bool:
        what = next(g for g in m.groups() if g)
        return any(i["kind"] == "todo" and what in i["text"] for i in load())

    def add(self, text: str, kind: str, ctx: Context) -> str:
        text = text.strip(" 。.")
        if not text:
            return ctx.reply("要记什么？", "What should I note down?")
        items = load()
        items.append({"text": text, "kind": kind, "time": dt.datetime.now().isoformat(timespec="minutes")})
        save(items)
        if not any(i["text"] == text for i in load()):
            return ctx.reply("没能记下来。", "That wasn't saved.")
        return ctx.reply(f"记下了：{text}" if kind == "note" else f"已加到待办：{text}",
                         f"Noted: {text}" if kind == "note" else f"Added to your to-dos: {text}")

    def show(self, kind: str, ctx: Context) -> str:
        items = [i for i in load() if i["kind"] == kind]
        if not items:
            return ctx.reply("还没有笔记。" if kind == "note" else "没有待办事项。",
                             "No notes yet." if kind == "note" else "Nothing on your to-do list.")
        recent = items[-5:]
        lines = "；".join(f"{n}. {i['text']}" for n, i in enumerate(recent, 1))
        head = ctx.reply(f"一共 {len(items)} 条，" if len(items) > 5 else "", f"{len(items)} in all, " if len(items) > 5 else "")
        what = ctx.reply("笔记" if kind == "note" else "待办",
                         ("notes" if kind == "note" else "to-dos") if len(items) > 5 else ("Notes" if kind == "note" else "To-dos"))
        return ctx.reply(f"{head}{'最近的' if len(items) > 5 else ''}{what}：{lines}。",
                         f"{head}{'latest ' if len(items) > 5 else ''}{what}: {lines}.")

    def done(self, what: str, ctx: Context) -> str:
        items = load()
        hit = [i for i in items if i["kind"] == "todo" and what.strip() in i["text"]]
        if not hit:
            return ctx.reply(f"待办里没有“{what}”。", f"There's no to-do like \"{what}\".")
        save([i for i in items if i is not hit[0]])
        return ctx.reply(f"已划掉：{hit[0]['text']}", f"Crossed off: {hit[0]['text']}")

    def clear(self, kind: str, ctx: Context) -> str:
        if not ctx.confirm(ctx.reply("确定要清空全部笔记吗？" if kind == "note" else "确定要清空全部待办吗？",
                                     "Clear all your notes?" if kind == "note" else "Clear all your to-dos?")):
            return ctx.reply("好的，不清空。", "OK, keeping them.")
        save([i for i in load() if i["kind"] != kind])
        return ctx.reply("已清空。", "Cleared.")

    def tools(self) -> list[Tool]:
        return [
            Tool("add_note", "Save a note or a to-do on this PC (kind: note or todo).",
                 schema({"text": {"type": "string"}, "kind": {"type": "string", "enum": ["note", "todo"]}}, ["text"]),
                 lambda a, ctx: self.add(a["text"], a.get("kind") or "note", ctx)),
            Tool("list_notes", "Read back the user's notes or to-dos.",
                 schema({"kind": {"type": "string", "enum": ["note", "todo"]}}),
                 lambda a, ctx: self.show(a.get("kind") or "note", ctx)),
            Tool("set_user_name", "Remember what the user wants to be called.",
                 schema({"name": {"type": "string"}}, ["name"]),
                 lambda a, ctx: (set_user_name(a["name"].strip()), f"Saved: the user is called {a['name']}")[1]),
        ]
