"""Conversation recap and personas."""

import json

from turing import personas
from turing.memory import Memory
from turing.skills import Context


def test_recap_survives_a_restart(tmp_path):
    path = tmp_path / "memory.json"
    m = Memory(path)
    m.add("帮我写一个周报的提纲", "好的，提纲分三部分：完成的工作、遇到的问题、下周计划。")
    again = Memory(path)  # e.g. after Turing restarted or crashed
    recap = again.recap()
    assert "周报" in recap and "下周计划" in recap


def test_recap_keeps_only_recent_exchanges(tmp_path):
    m = Memory(tmp_path / "memory.json")
    for i in range(20):
        m.add(f"问题{i}", f"回答{i}")
    recap = m.recap()
    assert "问题19" in recap and "问题11" not in recap


def test_fresh_history_starts_with_the_recap(tmp_path):
    from turing.ai import Brain

    class Echo(Brain):
        sent = []

        def reset(self):
            pass

        def _turn(self, text, ctx):
            self.sent.append(text)
            return "好的"

    memory = Memory(tmp_path / "memory.json")
    memory.add("帮我写一个周报的提纲", "提纲分三部分。")
    brain = Echo([], memory=memory)
    brain.ask("继续刚才那个任务", Context(config={}, say=print))
    assert "周报" in Echo.sent[0] and "继续刚才那个任务" in Echo.sent[0]
    brain.ask("再详细一点", Context(config={}, say=print))
    assert "周报" not in Echo.sent[1]  # same history: no need to repeat the recap


def test_screenshot_turn_starts_a_fresh_history(tmp_path):
    from turing.ai import Brain

    resets = []

    class Shot(Brain):
        def reset(self):
            resets.append(1)

        def _turn(self, text, ctx):
            self.saw_image = True
            return "屏幕上是一个网页。"

    brain = Shot([], memory=Memory(tmp_path / "memory.json"))
    before = len(resets)
    brain.ask("屏幕上是什么", Context(config={}, say=print))
    brain.ask("那个按钮是干嘛的", Context(config={}, say=print))
    assert len(resets) > before  # the picture isn't carried into the next request


def test_personas(tmp_path, monkeypatch):
    monkeypatch.setattr(personas, "FILE", tmp_path / "personas.json")
    data = personas.load()
    assert data["active"] == "默认" and personas.instructions(data) == ""
    data["presets"].append({"name": "海盗", "role": "a cheerful pirate", "style": "talk like a pirate",
                            "rules": ""})
    data["active"] = "海盗"
    personas.save(data)
    text = personas.instructions()
    assert "pirate" in text and "海盗" in text
    saved = json.loads((tmp_path / "personas.json").read_text(encoding="utf-8"))
    assert saved["active"] == "海盗"


def test_persona_saved_without_a_valid_active_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(personas, "FILE", tmp_path / "personas.json")
    personas.save({"active": "不存在", "presets": [{"name": "甲"}, {"name": ""}]})
    data = personas.load()
    assert data["active"] == "甲" and [p["name"] for p in data["presets"]] == ["甲"]
