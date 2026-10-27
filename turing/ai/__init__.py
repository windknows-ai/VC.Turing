"""The AI layer: understands anything the local rules don't, and acts through skill tools.

Providers are switchable. Claude goes through the Anthropic SDK; DeepSeek, Qwen, Kimi,
GLM, local Ollama and any other OpenAI-compatible service go through the OpenAI SDK.
Each user brings their own API key, which is kept in Windows Credential Manager.
"""

import datetime as dt
import json
import re
import threading
import time
from dataclasses import dataclass, field

from .. import secrets
from ..skills import Context, Tool, ToolImage


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    kind: str  # "anthropic" or "openai"
    base_url: str
    models: tuple[str, ...]
    key_url: str = ""
    needs_key: bool = True
    note: str = ""
    model_notes: dict = field(default_factory=dict)


PROVIDERS = {p.key: p for p in [
    Provider(
        "claude", "Claude", "anthropic", "",
        ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
        "https://platform.claude.com/settings/keys",
        note="Anthropic 的 AI。理解力和操作电脑最强，中英文都好。国内需要能访问国外网络。",
        model_notes={
            "claude-opus-5-5": "最聪明；每条指令约 5–8 分钱",
            "claude-sonnet-5-5": "均衡；每条指令约 2–4 分钱",
            "claude-haiku-5-5": "最快最便宜；每条指令不到 1 分钱",
        },
    ),
    Provider(
        "openai", "OpenAI", "openai", "https://api.openai.com/v1", (),
        "https://platform.openai.com/api-keys",
        note="ChatGPT 背后的公司。API 按用量付费，和 ChatGPT 会员是分开的。国内需要能访问国外网络。",
    ),
    Provider(
        "muse", "Muse", "openai", "https://api.meta.ai/v1", ("muse-spark-1.1",),
        "https://dev.meta.ai/",
        note="Meta 的 AI（Muse Spark），能看图，会操作电脑。目前只对美国的开发者开放预览，"
             "国内需要能访问国外网络。",
    ),
    Provider(
        "deepseek", "DeepSeek", "openai", "https://api.deepseek.com",
        ("deepseek-flash", "deepseek-v4-pro"),
        "https://platform.deepseek.com/api_keys", note="国内直接能用，很便宜。",
    ),
    Provider(
        "qwen", "通义千问", "openai",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ("qwen-plus", "qwen-max", "qwen-turbo"),
        "https://bailian.console.aliyun.com/?apiKey=1", note="阿里云的 AI，国内直接能用，新用户有免费额度。",
    ),
    Provider(
        "kimi", "Kimi", "openai", "https://api.moonshot.cn/v1", ("kimi-k2.6",),
        "https://platform.moonshot.cn/console/api-keys", note="月之暗面的 AI，国内直接能用。",
    ),
    Provider(
        "glm", "智谱", "openai", "https://open.bigmodel.cn/api/paas/v4/",
        ("glm-5.3-flash", "glm-5.3"),
        "https://open.bigmodel.cn/usercenter/apikeys", note="智谱 GLM，国内直接能用，flash 模型很便宜。",
    ),
    Provider(
        "ollama", "Ollama", "openai", "http://127.0.0.1:11434/v1", (),
        "https://ollama.com/download", needs_key=False,
        note="在本机运行开源模型，不花钱、不联网。模型越大越聪明，但需要更好的显卡。"
             "登录免费的 Ollama 账户后，还能用有免费额度的云端模型。",
    ),
    Provider(
        "custom", "自定义", "openai", "", (),
        note="其他兼容 OpenAI 接口的服务。填上服务商给的接口地址、模型名和 API Key。",
    ),
]}

SYSTEM_PROMPT = """\
You are Turing (图灵), a voice assistant running on the user's Windows PC. The user talks to \
you through a microphone and everything you write is read aloud by text-to-speech.

- Reply in the language the user spoke (Chinese or English).
- Keep replies short and conversational: usually one or two sentences. No Markdown, lists, \
emoji, code or URLs, since they can't be read aloud.
- When the user wants something done on the computer, use the tools, then confirm briefly \
what happened. If a tool fails, say so plainly.
- The transcript comes from speech recognition and may contain homophone mistakes \
(for example "星七几" for "星期几"). Interpret it the most sensible way.
- If the request is ambiguous, ask one short question. If you can't do something with the \
tools you have, say so instead of pretending.
- Never state facts (numbers, prices, rates, news, names) that no tool result gave you; \
if a search didn't find it, say so.
- Only say something is done when a tool result shows it. type_text and press_keys just \
send keys to the window in front: say what you tried, and look at the screen if you need \
to know whether it worked. To open Chrome or Edge in a particular account, pass profile \
to open_app. To search inside an app or site (抖音, B站, YouTube…), use search_in_app; \
to ask ChatGPT, Claude or Perplexity something, use ask_chatbot.
- The user's message starts with the current local time in brackets; use it when relevant.
- You can see the user's screen with look_at_screen. Use it whenever they refer to what's \
in front of them: the screen, this page, this window, this error, this picture. To look \
something up from the screen, look first, then call look_up with a precise query (or \
web_search if they asked to see it in the browser). When \
describing the screen, give the gist in a sentence or two; don't read long text aloud \
unless asked.
- For questions that need fresh information, find the answer yourself and say it: \
get_weather for weather, look_up (then read_web_page if the snippets aren't enough) for \
anything else. Don't open the browser unless the user asks to see results there.
- To message someone on WeChat, use send_wechat; it asks the user to confirm before \
sending. For typing elsewhere, look at the screen if needed, then use type_text and \
press_keys.
- If you need an answer from the user, end your reply with a question: Turing keeps \
listening for the answer without the wake word.
"""

# Start a fresh conversation after this long without talking, so old context
# doesn't confuse new commands (and requests stay small).
IDLE_RESET_SECONDS = 180
MAX_TURNS = 8
# Enough for "open WeChat, look at the screen, find the group, type, send".
MAX_TOOL_ROUNDS = 10


class AIError(Exception):
    """A failure worth telling the user about, with a spoken explanation.

    `detail` is the provider's own wording, shown in the app but not read aloud.
    """

    def __init__(self, zh: str, en: str, detail: str = "", kind: str = ""):
        super().__init__(en)
        self.zh, self.en, self.detail, self.kind = zh, en, (detail or "")[:200], kind


_NO_CREDIT = re.compile(
    r"insufficient[ _]?(balance|quota|credit)|credit balance|exceeded your current quota|"
    r"余额不足|欠费|arrearage|billing", re.I)


def provider_message(e) -> str:
    """The provider's own error sentence, without the SDK's wrapping or request ids."""
    body = getattr(e, "body", None)
    msg = ""
    if isinstance(body, dict):
        inner = body.get("error")
        msg = str(inner.get("message") or "") if isinstance(inner, dict) else str(body.get("message") or inner or "")
    elif isinstance(body, str):
        # Newer SDKs (openai 3.39+) hand over a plain-text error as is, and leave it
        # out of e.message.
        msg = body
    msg = msg or str(getattr(e, "message", "") or e)
    return re.sub(r"\s*\(request[_ ]id:[^)]*\)", "", msg).strip()


def out_of_credit(e) -> bool:
    """True if a provider error (or its text) says the account has no money left.
    Looks at the error code too: OpenAI puts "insufficient_quota" only there."""
    text = e if isinstance(e, str) else f"{provider_message(e)} {getattr(e, 'body', '')}"
    return bool(_NO_CREDIT.search(text or ""))


def credit_error(detail: str = "") -> AIError:
    return AIError("这个 AI 账户余额不足。请到服务商网站充值后再试。",
                   "This AI account is out of credit. Top it up on the provider's website.",
                   detail, kind="credit")


_PAID_PLAN = re.compile(r"not in the free plan|requires? a (paid|pro) (plan|subscription)|upgrade to", re.I)


def status_error(status: int, detail: str = "") -> AIError:
    """Plain-language explanation for an HTTP error from an AI provider."""
    if _PAID_PLAN.search(detail or ""):
        # e.g. an Ollama cloud model that free accounts can't use (also a 402).
        return AIError("这个模型需要付费会员，你的免费账户用不了。请换一个免费的模型。",
                       "This model needs a paid plan. Pick a free one instead.", detail, kind="plan")
    if status == 402 or out_of_credit(detail):
        return credit_error(detail)
    if status >= 500:
        return AIError("AI 服务暂时出故障了，请过一会儿再试。",
                       "The AI service is having trouble. Try again in a bit.", detail)
    return AIError(f"AI 服务出错了（{status}）。", f"The AI service returned an error ({status}).", detail)


def stamp(text: str) -> str:
    from ..skills import notes

    now = dt.datetime.now()
    about = notes.profile()
    extra = ""
    if about.get("name"):
        extra += f" The user's name: {about['name']}."
    if about.get("reply_language") in ("zh", "en"):
        extra += f" Always reply in {'Chinese' if about['reply_language'] == 'zh' else 'English'}."
    return f"[{now:%Y-%m-%d %H:%M} {now:%A}]{extra} {text}"


def run_tool(tools: dict[str, Tool], name: str, args: dict, ctx: Context) -> tuple[str | ToolImage, bool]:
    """Run one tool call; returns (result text or picture, is_error)."""
    tool = tools.get(name)
    if ctx.cancelled():
        # The user talked over Turing to give a new command: don't act on the old one.
        result, is_error = "Cancelled: the user interrupted with a new request.", True
    elif tool is None:
        result, is_error = f"Unknown tool {name}", True
    elif not isinstance(args, dict):
        result, is_error = "Tool arguments must be a JSON object", True
    else:
        try:
            out = tool.run(args, ctx)
            result, is_error = (out if isinstance(out, ToolImage) else str(out)), False
        except Exception as e:
            result, is_error = f"{type(e).__name__}: {e}", True
    print(f"         🔧 {name}({json.dumps(args, ensure_ascii=False)}) → {result}", flush=True)
    ctx.state.setdefault("tool_log", []).append((name, str(result), is_error))
    return result, is_error


_MARKDOWN = [
    (re.compile(r"[*_`#>]+"), ""),                       # emphasis, code, headings, quotes
    (re.compile(r"^\s*(?:[-•]\s*|\d+(?:[.)]\s+|、))", re.M), ""),  # list markers, not "3.5"
    (re.compile(r"\s*\n+\s*"), " "),                      # one spoken paragraph
]


def speakable(text: str) -> str:
    """Strip Markdown some models add anyway, since it sounds odd read aloud."""
    for pattern, repl in _MARKDOWN:
        text = pattern.sub(repl, text)
    return text.strip()


class Brain:
    """Holds one conversation with the chosen provider.

    The working history (tool calls, screenshots) is restarted often so requests stay
    small and fast: after a few idle minutes, every MAX_TURNS turns, and right after a
    turn that included a screenshot (so the picture isn't uploaded again with every
    later message). `memory` keeps a short text recap of recent exchanges that each
    fresh history starts with, so the AI still knows what "that task" refers to.
    """

    def __init__(self, tools: list[Tool], system: str = SYSTEM_PROMPT, memory=None):
        self.tools = {t.name: t for t in tools}
        self.system = system
        self.memory = memory
        self._last = 0.0
        self._turns = 0
        self.saw_image = False  # set by the provider code when a tool returned a picture
        # One conversation, one request at a time: an interrupted request may still be
        # waiting on the provider when the user's next command arrives.
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        raise NotImplementedError

    def warm_up(self):
        """Optional: get the model ready before the first command (local models load slowly)."""

    def _turn(self, text: str, ctx: Context) -> str:
        raise NotImplementedError

    def ask(self, text: str, ctx: Context, raise_errors: bool = False) -> str:
        with self._lock:
            now = time.monotonic()
            if (now - self._last > IDLE_RESET_SECONDS or self._turns >= MAX_TURNS
                    or self.saw_image):
                self.reset()
                self._turns = 0
                self.saw_image = False
            self._last = now
            message = stamp(text)
            if self._turns == 0 and self.memory is not None:
                recap = self.memory.recap()
                if recap:
                    message = f"{recap}\n\nThe user now says: {message}"
            self._turns += 1
            try:
                reply = self._turn(message, ctx)
            except AIError as e:
                self.reset()
                self._turns = 0
                if raise_errors:
                    raise
                return ctx.reply(e.zh, e.en)
            if ctx.cancelled():
                # Interrupted: drop this exchange so the next command starts clean.
                self.reset()
                self._turns = 0
                return ""
            reply = speakable(reply) or ctx.reply("好的", "OK")
            if self.memory is not None:
                self.memory.add(text, reply)
            return reply


def configured(cfg: dict) -> bool:
    ai = cfg.get("ai", {})
    return ai.get("provider", "") in PROVIDERS


def create_brain(cfg: dict, tools: list[Tool], api_key: str | None = None,
                 memory=None) -> Brain | None:
    """Build the brain the user picked in setup, or None if AI is off.

    `api_key` overrides the saved key (the setup window tests a key before saving it).
    The system prompt includes the user's active persona.
    """
    from .. import personas

    ai = cfg.get("ai", {})
    provider = PROVIDERS.get(ai.get("provider", ""))
    if provider is None:
        return None
    model = ai.get("model") or (provider.models[0] if provider.models else "")
    base_url = ai.get("base_url") or provider.base_url
    api_key = api_key or secrets.get_api_key(provider.key)
    persona = personas.instructions()
    system = SYSTEM_PROMPT + ("\n" + persona if persona else "")
    if provider.kind == "anthropic":
        from .claude import ClaudeBrain

        return ClaudeBrain(tools, model=model, api_key=api_key, system=system, memory=memory)
    from .openai_compat import OpenAIBrain

    return OpenAIBrain(tools, model=model, api_key=api_key or "none", base_url=base_url,
                       system=system, memory=memory)
