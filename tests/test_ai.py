"""AI layer tests against fake local servers. No real API calls, no keys, no cost."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from turing import ai, config
from turing.ai.claude import ClaudeBrain
from turing.ai.openai_compat import OpenAIBrain
from turing.skills import Context, Skill, Tool, load_skills, route, schema
from turing.skills.web import Web, search_url


class FakeServer:
    """Replies to POSTs with queued (status, json) responses and records request bodies."""

    def __init__(self):
        self.replies, self.requests, self.headers = [], [], []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(200, {"object": "list", "data": [
                    {"id": "model-b", "object": "model", "created": 0, "owned_by": "x"},
                    {"id": "model-a", "object": "model", "created": 0, "owned_by": "x"}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests.append(body)
                server.headers.append(dict(self.headers))
                self._send(*server.replies.pop(0))

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


@pytest.fixture
def calls():
    return []


@pytest.fixture
def tools(calls):
    return [Tool("set_thing", "Set the thing.", schema({"x": {"type": "integer"}}, ["x"]),
                 lambda args, ctx: calls.append(args) or f"thing={args['x']}")]


def ctx():
    return Context(config={}, say=print, zh=True)


# --- OpenAI-compatible providers ------------------------------------------------

def chat_reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return 200, {"id": "c1", "object": "chat.completion", "created": 0, "model": "m",
                 "choices": [{"index": 0, "message": msg,
                              "finish_reason": "tool_calls" if tool_calls else "stop"}]}


def test_openai_tool_loop(server, tools, calls):
    server.replies = [
        chat_reply(tool_calls=[{"id": "call_1", "type": "function",
                                "function": {"name": "set_thing", "arguments": '{"x": 7}'}}]),
        chat_reply("好了，设成 7 了。"),
    ]
    brain = OpenAIBrain(tools, model="m", api_key="k", base_url=server.url + "/v1")
    assert brain.ask("把东西设成七", ctx()) == "好了，设成 7 了。"
    assert calls == [{"x": 7}]
    first, second = server.requests
    assert first["messages"][0]["role"] == "system"
    assert first["tools"][0]["function"]["name"] == "set_thing"
    assert first["messages"][-1]["content"].endswith("把东西设成七")  # after the time stamp
    assert second["messages"][-2]["tool_calls"][0]["id"] == "call_1"
    assert second["messages"][-1] == {"role": "tool", "tool_call_id": "call_1", "content": "thing=7"}


def test_interrupted_command_runs_no_tools(server, tools, calls):
    # The user talked over Turing while the AI was deciding to call a tool.
    server.replies = [chat_reply(tool_calls=[{"id": "c1", "type": "function",
                                              "function": {"name": "set_thing", "arguments": '{"x": 1}'}}])]
    brain = OpenAIBrain(tools, model="m", api_key="k", base_url=server.url + "/v1")
    cancelled = Context(config={}, say=print, cancelled=lambda: True)
    assert brain.ask("设成一", cancelled) == ""
    assert calls == []
    assert len(brain.messages) == 1  # conversation reset for the next command


def test_run_tool_refuses_after_interrupt(tools, calls):
    out, is_error = ai.run_tool({t.name: t for t in tools}, "set_thing", {"x": 1},
                                Context(config={}, say=print, cancelled=lambda: True))
    assert is_error and calls == []


def test_openai_model_without_tool_support(server, tools):
    server.replies = [
        (400, {"error": {"message": "registry.ollama.ai/library/gemma does not support tools"}}),
        chat_reply("你好"),
    ]
    brain = OpenAIBrain(tools, model="gemma", api_key="none", base_url=server.url + "/v1")
    assert brain.ask("你好", ctx()) == "你好"
    assert "tools" in server.requests[0] and "tools" not in server.requests[1]


def test_openai_bad_key_is_spoken(server, tools):
    server.replies = [(401, {"error": {"message": "invalid key"}})]
    brain = OpenAIBrain(tools, model="m", api_key="bad", base_url=server.url + "/v1")
    assert "API Key 无效" in brain.ask("你好", ctx())


@pytest.mark.parametrize("status,body", [
    (402, {"error": {"message": "Insufficient Balance", "type": "unknown_error"}}),  # DeepSeek
    (429, {"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}),
    (400, {"error": {"message": "Arrearage: account is in arrears", "code": "Arrearage"}}),  # Qwen
])
def test_openai_out_of_credit_is_explained(server, tools, status, body):
    server.replies = [(status, body)] * 3  # the SDK retries 429s
    brain = OpenAIBrain(tools, model="m", api_key="k", base_url=server.url + "/v1")
    with pytest.raises(ai.AIError) as err:
        brain.ask("你好", ctx(), raise_errors=True)
    assert "余额不足" in err.value.zh and err.value.kind == "credit"
    assert err.value.detail


def test_paid_plan_model_is_explained(server, tools):
    # What Ollama says for a cloud model a free account can't use.
    server.replies = [(402, {"error": "This model is not in the Free plan. Pro is $20/month. "
                                      "Try gemma4:31b-cloud, which is in the Free plan."})]
    brain = OpenAIBrain(tools, model="glm-5.3-flash:cloud", api_key="none",
                        base_url=server.url + "/v1")
    with pytest.raises(ai.AIError) as err:
        brain.ask("你好", ctx(), raise_errors=True)
    assert err.value.kind == "plan" and "付费会员" in err.value.zh


def test_openai_server_trouble_is_explained(server, tools):
    server.replies = [(503, {"error": {"message": "overloaded"}})] * 3
    brain = OpenAIBrain(tools, model="m", api_key="k", base_url=server.url + "/v1")
    assert "暂时出故障" in brain.ask("你好", ctx())


def test_claude_out_of_credit_is_explained(server, claude):
    server.replies = [(400, {"type": "error", "error": {
        "type": "invalid_request_error",
        "message": "Your credit balance is too low to access the Anthropic API."}})]
    assert "余额不足" in claude().ask("你好", ctx())


def test_openai_list_models(server):
    from turing.ai.openai_compat import list_models

    assert list_models("k", server.url + "/v1") == ["model-a", "model-b"]


# --- Claude ---------------------------------------------------------------------

def claude_reply(content, stop_reason):
    return 200, {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                 "content": content, "stop_reason": stop_reason, "stop_sequence": None,
                 "usage": {"input_tokens": 10, "output_tokens": 5}}


@pytest.fixture
def claude(server, tools, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url)
    return lambda model="claude-opus-5-5": ClaudeBrain(tools, model=model, api_key="k")


def test_claude_tool_loop(server, claude, calls):
    server.replies = [
        claude_reply([{"type": "text", "text": "好的"},
                      {"type": "tool_use", "id": "toolu_1", "name": "set_thing", "input": {"x": 3}}],
                     "tool_use"),
        claude_reply([{"type": "text", "text": "已经设成 3。"}], "end_turn"),
    ]
    assert claude().ask("设成三", ctx()) == "已经设成 3。"
    assert calls == [{"x": 3}]
    first, second = server.requests
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in server.headers[0].get("anthropic-beta", "")
    assert first["output_config"] == {"effort": "low"}
    assert first["tools"][0]["name"] == "set_thing"
    # The assistant turn is replayed as-is, then all tool results in one user message.
    assert second["messages"][1]["content"][1]["id"] == "toolu_1"
    results = second["messages"][2]["content"]
    assert results == [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "thing=3",
                        "is_error": False}]


def test_claude_haiku_has_no_fallbacks(server, claude):
    server.replies = [claude_reply([{"type": "text", "text": "嗨"}], "end_turn")]
    assert claude("claude-haiku-5-5").ask("你好", ctx()) == "嗨"
    assert "fallbacks" not in server.requests[0]
    assert server.requests[0]["output_config"] == {"effort": "low"}


def test_claude_tool_error_is_reported(server, claude):
    server.replies = [
        claude_reply([{"type": "tool_use", "id": "t1", "name": "no_such_tool", "input": {}}], "tool_use"),
        claude_reply([{"type": "text", "text": "做不到"}], "end_turn"),
    ]
    assert claude().ask("做点什么", ctx()) == "做不到"
    result = server.requests[1]["messages"][2]["content"][0]
    assert result["is_error"] is True


def test_claude_refusal(server, claude):
    server.replies = [claude_reply([], "refusal")]
    brain = claude()
    assert brain.ask("...", ctx()) == "这个我帮不了你。"
    assert brain.messages == []


def test_claude_bad_key(server, claude):
    server.replies = [(401, {"type": "error", "error": {"type": "authentication_error",
                                                        "message": "invalid x-api-key"}})]
    assert "API Key 无效" in claude().ask("你好", ctx())


# --- looking at the screen ------------------------------------------------------

@pytest.fixture
def screenshot_tool():
    from turing.skills import ToolImage

    return [Tool("look_at_screen", "Look.", schema(),
                 lambda args, ctx: ToolImage("Screenshot.", b"\xff\xd8fakejpeg"))]


def test_claude_gets_screenshot_as_image_block(server, screenshot_tool, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url)
    server.replies = [
        claude_reply([{"type": "tool_use", "id": "t1", "name": "look_at_screen", "input": {}}], "tool_use"),
        claude_reply([{"type": "text", "text": "屏幕上是一个文档。"}], "end_turn"),
    ]
    brain = ClaudeBrain(screenshot_tool, model="claude-opus-5-5", api_key="k")
    assert brain.ask("屏幕上是什么", ctx()) == "屏幕上是一个文档。"
    content = server.requests[1]["messages"][2]["content"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(content[0]["source"]["data"]) == b"\xff\xd8fakejpeg"
    assert content[1] == {"type": "text", "text": "Screenshot."}


def test_openai_gets_screenshot_after_tool_results(server, screenshot_tool):
    server.replies = [
        chat_reply(tool_calls=[{"id": "c1", "type": "function",
                                "function": {"name": "look_at_screen", "arguments": "{}"}}]),
        chat_reply("是一个网页。"),
    ]
    brain = OpenAIBrain(screenshot_tool, model="m", api_key="k", base_url=server.url + "/v1")
    assert brain.ask("屏幕上是什么", ctx()) == "是一个网页。"
    *_, tool_msg, image_msg = server.requests[1]["messages"]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert image_msg["role"] == "user"
    url = image_msg["content"][1]["image_url"]["url"]
    assert url == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8fakejpeg").decode()


def test_model_without_vision_is_explained(server, screenshot_tool):
    server.replies = [
        chat_reply(tool_calls=[{"id": "c1", "type": "function",
                                "function": {"name": "look_at_screen", "arguments": "{}"}}]),
        (400, {"error": {"message": "this model does not support image input"}}),
    ]
    brain = OpenAIBrain(screenshot_tool, model="m", api_key="k", base_url=server.url + "/v1")
    assert "看不了图片" in brain.ask("屏幕上是什么", ctx())


def test_screen_requests_need_ai():
    from turing.skills.screen import Screen

    skills = load_skills({"apps": {"aliases": {}}})
    assert "能看图的 AI" in route(skills, "屏幕上是什么", ctx(), None)
    assert "能看图的 AI" in route(skills, "用浏览器查一下当前界面", ctx(), None)
    brain = FakeBrain()
    assert route(skills, "这个报错是什么意思", ctx(), brain) == "AI 回答"
    assert Screen({}).handle("打开微信", ctx()) is None


def test_screenshot_is_shrunk():
    from PIL import Image

    from turing.screen import MAX_SIDE, shrink, to_jpeg

    big = shrink(Image.new("RGB", (3840, 2160), "white"))
    assert max(big.size) == MAX_SIDE and big.size[0] / big.size[1] == pytest.approx(16 / 9, 0.01)
    assert to_jpeg(big)[:2] == b"\xff\xd8"


# --- routing, tools, config -----------------------------------------------------

class FakeBrain:
    model = "fake"

    def __init__(self):
        self.asked = []

    def ask(self, text, ctx):
        self.asked.append(text)
        return "AI 回答"


def test_local_rules_win_over_ai():
    brain = FakeBrain()

    class Echo(Skill):
        def handle(self, text, ctx):
            return "local" if text == "暂停" else None

    assert route([Echo({})], "暂停", ctx(), brain) == "local"
    assert route([Echo({})], "太吵了", ctx(), brain) == "AI 回答"
    assert brain.asked == ["太吵了"]


def test_rule_that_cannot_finish_hands_over_to_ai():
    from turing.skills import Fallback

    class Picky(Skill):
        def handle(self, text, ctx):
            return Fallback("没找到")

    brain = FakeBrain()
    assert route([Picky({})], "打开那个修图软件", ctx(), brain) == "AI 回答"
    assert route([Picky({})], "打开那个修图软件", ctx(), None) == "没找到"


def test_open_folder_phrases(monkeypatch):
    from turing.skills.apps import Apps

    opened = []
    monkeypatch.setattr("subprocess.Popen", lambda cmd, **kw: opened.append(cmd))
    apps = Apps.__new__(Apps)  # skip the Start-menu scan
    for text in ("open my folder", "打开我的文件资源管理器", "打开文件夹"):
        apps.handle(text, ctx())
    assert opened == [["explorer.exe"]] * 3


def test_no_ai_reply():
    assert "设置" in route([], "太吵了", ctx(), None)


def test_skill_tools_are_well_formed():
    skills = load_skills({"apps": {"aliases": {}}})
    tools = [t for s in skills for t in s.tools()]
    names = [t.name for t in tools]
    assert len(names) == len(set(names))
    assert {"open_app", "media_control", "volume", "start_timer", "web_search", "lock_screen"} <= set(names)
    for t in tools:
        assert t.parameters["type"] == "object"
        assert set(t.parameters["required"]) <= set(t.parameters["properties"])


@pytest.mark.parametrize("text,query", [
    ("搜索周杰伦", "周杰伦"), ("用浏览器搜一下今天的新闻", "今天的新闻"), ("百度一下天气", "天气"),
    ("search for python tutorials", "python tutorials"), ("google cheap flights", "cheap flights"),
])
def test_web_search_commands(text, query, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    Web({}).handle(text, ctx())
    assert opened == [search_url("https://www.bing.com/search?q={query}", query)]


def test_screen_questions_go_to_ai(monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("should not open"))
    assert Web({}).handle("搜索当前屏幕上的内容", ctx()) is None


def test_save_section_keeps_comments(tmp_path):
    path = tmp_path / "config.toml"
    config.load(path)
    config.save_section("ai", {"provider": "deepseek", "model": "deepseek-flash"}, path)
    text = path.read_text(encoding="utf-8")
    assert "# 唤醒词" in text and 'provider = "deepseek"' in text
    assert config.load(path)["ai"]["model"] == "deepseek-flash"


def test_speakable_strips_markdown():
    text = "您希望怎么做：\n1. **完全静音**\n2. 调到 30%\n- 或者别的"
    assert ai.speakable(text) == "您希望怎么做： 完全静音 调到 30% 或者别的"
    assert ai.speakable("3.5 版本更快") == "3.5 版本更快"


def test_create_brain_respects_choice(monkeypatch):
    monkeypatch.setattr("turing.secrets.get_api_key", lambda p: "k")
    assert ai.create_brain({"ai": {"provider": "none"}}, []) is None
    brain = ai.create_brain({"ai": {"provider": "deepseek", "model": "", "base_url": ""}}, [])
    assert isinstance(brain, OpenAIBrain) and brain.model == "deepseek-flash"
    assert brain.base_url == "https://api.deepseek.com"
