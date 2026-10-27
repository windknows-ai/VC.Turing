"""Any OpenAI-compatible chat API: DeepSeek, Qwen, Kimi, GLM, local Ollama, and others."""

import base64
import json
import re
import threading
import time
import urllib.request

import openai

from ..skills import ToolImage
from . import (MAX_TOOL_ROUNDS, SYSTEM_PROMPT, AIError, Brain, credit_error, out_of_credit,
               provider_message, run_tool, status_error)


# How long a local model stays in graphics memory after its last use.
LOCAL_KEEP_ALIVE = "2m"


def _reachable(root: str) -> bool:
    try:
        urllib.request.urlopen(root + "/api/version", timeout=2).read()
        return True
    except OSError:
        return False


def tool_specs(tools) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools.values()]


def _has_image(messages) -> bool:
    return any(isinstance(m.get("content"), list) for m in messages)


def _assistant_entry(msg) -> dict:
    entry = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        entry["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls
        ]
    # DeepSeek-style thinking models want their reasoning echoed back during tool calls.
    reasoning = (msg.model_extra or {}).get("reasoning_content")
    if reasoning:
        entry["reasoning_content"] = reasoning
    return entry


def _client(api_key: str, base_url: str, timeout: float = 60.0) -> openai.OpenAI:
    return openai.OpenAI(api_key=api_key or "none", base_url=base_url, timeout=timeout, max_retries=1)


class OpenAIBrain(Brain):
    def __init__(self, tools, model: str, api_key: str, base_url: str,
                 system: str = SYSTEM_PROMPT, memory=None):
        self.client = _client(api_key, base_url)
        self.model = model
        self.base_url = base_url
        self._use_tools = True
        super().__init__(tools, system=system, memory=memory)

    def reset(self):
        self.messages: list[dict] = [{"role": "system", "content": self.system}]

    def _strip_images(self):
        self.messages = [m for m in self.messages if not isinstance(m.get("content"), list)]

    @property
    def _local(self) -> bool:
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def warm_up(self):
        """Load a local model before it's needed (it can take a while), and make it
        leave graphics memory after LOCAL_KEEP_ALIVE idle, so other apps don't stutter."""
        if not self._local:
            return
        root = re.sub(r"/v1/?$", "", self.base_url)
        if not _reachable(root):
            # Ollama doesn't start with Windows; bring it up now, while the user talks.
            from ..control_center import ollama

            try:
                ollama.start()
            except RuntimeError:
                return
            for _ in range(30):
                time.sleep(0.5)
                if _reachable(root):
                    break
        body = json.dumps({"model": self.model, "keep_alive": LOCAL_KEEP_ALIVE}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(root + "/api/generate", data=body),
                                   timeout=180).read()
        except OSError:
            pass

    def _create(self):
        kwargs = dict(model=self.model, messages=self.messages)
        if self._use_tools and self.tools:
            kwargs["tools"] = tool_specs(self.tools)
        try:
            return self.client.chat.completions.create(**kwargs)
        except openai.BadRequestError as e:
            if out_of_credit(e):
                raise credit_error(provider_message(e))
            if _has_image(self.messages) and re.search(r"image|vision|multimodal|多模态|图片", str(e), re.I):
                # Drop the picture so the conversation can go on, and say why.
                self._strip_images()
                raise AIError("这个模型看不了图片。请在 AI 连接里换一个能看图的模型。",
                              "This model can't look at pictures. Pick one that can in AI settings.")
            # Some local models can't do tool calls; carry on as a plain chatbot.
            if self._use_tools and "tool" in str(e).lower():
                self._use_tools = False
                return self._create()
            raise AIError("AI 服务拒绝了这个请求，请检查模型名。",
                          "The AI service rejected the request. Check the model name.", provider_message(e))
        except openai.AuthenticationError as e:
            raise AIError("API Key 无效，请在 AI 连接里重新填写。",
                          "The API key was rejected. Enter it again in AI settings.", provider_message(e))
        except openai.NotFoundError as e:
            raise AIError(f"找不到模型 {self.model}，请在 AI 连接里换一个。",
                          f"Model {self.model} wasn't found. Pick another in AI settings.", provider_message(e))
        except openai.RateLimitError as e:
            # OpenAI reports an empty account as a rate limit (insufficient_quota).
            if out_of_credit(e):
                raise credit_error(provider_message(e))
            raise AIError("请求太频繁了，请过一会儿再试。",
                          "Too many requests. Try again in a bit.", provider_message(e))
        except openai.APIStatusError as e:
            raise status_error(e.status_code, provider_message(e))
        except openai.APIConnectionError:
            if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
                raise AIError("连不上本地模型，请确认 Ollama 已经启动。",
                              "Couldn't reach the local model. Is Ollama running?")
            raise AIError("连不上 AI 服务，请检查网络。",
                          "Couldn't reach the AI service. Check your internet connection.")

    def _turn(self, text, ctx) -> str:
        self.messages.append({"role": "user", "content": text})
        for _ in range(MAX_TOOL_ROUNDS):
            choice = self._create().choices[0]
            if ctx.cancelled():
                return ""
            msg = choice.message
            self.messages.append(_assistant_entry(msg))
            if not msg.tool_calls:
                if self._local:
                    # Chat requests reset Ollama's timer to its 5-minute default; shorten it.
                    threading.Thread(target=self.warm_up, daemon=True).start()
                return msg.content or ""
            images = []
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    output, _ = run_tool(self.tools, call.function.name, args, ctx)
                except json.JSONDecodeError:
                    output = "Error: arguments were not valid JSON"
                if isinstance(output, ToolImage):
                    images.append(output)
                    self.saw_image = True  # start a fresh history next time
                    output = f"{output.text} The picture follows in the next message."
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
            # Tool messages can only carry text here, so pictures (screenshots) go in a
            # user message right after all of this round's tool results.
            for image in images:
                b64 = base64.b64encode(image.data).decode()
                self.messages.append({"role": "user", "content": [
                    {"type": "text", "text": image.text},
                    {"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{b64}"}},
                ]})
        self.reset()
        return ctx.reply("这个任务步骤太多了，我先停下。", "That took too many steps, so I stopped.")


# Non-chat models some providers list alongside chat ones (notably OpenAI).
_NOT_CHAT = re.compile(r"embed|tts|whisper|transcribe|audio|realtime|image|dall-e|moderation|"
                       r"search|rerank|speech", re.I)


def list_models(api_key: str, base_url: str) -> list[str]:
    ids = (m.id for m in _client(api_key, base_url, timeout=15.0).models.list())
    return sorted(i for i in ids if not _NOT_CHAT.search(i))
