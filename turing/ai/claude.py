"""Claude through the official Anthropic SDK, with a manual tool-use loop.

A manual loop (rather than the SDK's beta tool runner) keeps one tool format shared
with the OpenAI-compatible providers and lets us cap the number of tool rounds.
"""

import base64

import anthropic

from ..skills import ToolImage
from . import (MAX_TOOL_ROUNDS, SYSTEM_PROMPT, AIError, Brain, credit_error, out_of_credit,
               provider_message, run_tool, status_error)

# Models that accept server-side refusal fallbacks (not Haiku: it has none).
FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")
# Claude 5 family models take `effort`; low keeps voice replies quick.
EFFORT_MODELS = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5", "claude-haiku-5")


def tool_specs(tools) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools.values()]


class ClaudeBrain(Brain):
    def __init__(self, tools, model: str, api_key: str | None, system: str = SYSTEM_PROMPT,
                 memory=None):
        # api_key=None lets the SDK use ANTHROPIC_API_KEY or an `ant auth login` profile.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=2)
        self.model = model
        super().__init__(tools, system=system, memory=memory)

    def reset(self):
        # Append-only history: we only ever add turns, and start over instead of trimming.
        self.messages: list[dict] = []

    def _create(self):
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=self.system,
            messages=self.messages,
            cache_control={"type": "ephemeral"},
        )
        if self.tools:
            kwargs["tools"] = tool_specs(self.tools)
        if self.model.startswith(EFFORT_MODELS):
            kwargs["output_config"] = {"effort": "low"}
        try:
            if self.model.startswith(FALLBACK_MODELS):
                return self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            return self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise AIError("Claude 的 API Key 无效，请在 AI 连接里重新填写。",
                          "The Claude API key was rejected. Enter it again in AI settings.", provider_message(e))
        except anthropic.PermissionDeniedError as e:
            raise AIError("这个 API Key 没有使用该模型的权限。",
                          "This API key isn't allowed to use that model.", provider_message(e))
        except anthropic.NotFoundError as e:
            raise AIError(f"找不到模型 {self.model}，请在 AI 连接里换一个。",
                          f"Model {self.model} wasn't found. Pick another in AI settings.", provider_message(e))
        except anthropic.RateLimitError as e:
            raise AIError("请求太频繁了，请过一会儿再试。",
                          "Too many requests. Try again in a bit.", provider_message(e))
        except anthropic.BadRequestError as e:
            # An empty account comes back as a 400 ("credit balance is too low").
            if out_of_credit(e):
                raise credit_error(provider_message(e))
            raise status_error(e.status_code, provider_message(e))
        except anthropic.APIStatusError as e:
            raise status_error(e.status_code, provider_message(e))
        except anthropic.APIConnectionError:
            raise AIError("连不上 Claude，请检查网络。",
                          "Couldn't reach Claude. Check your internet connection.")

    def _turn(self, text, ctx) -> str:
        self.messages.append({"role": "user", "content": text})
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create()
            if ctx.cancelled():
                return ""
            # Keep the full content (thinking blocks included) so later turns stay valid.
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                self.reset()
                return ctx.reply("这个我帮不了你。", "Sorry, I can't help with that.")
            calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                return " ".join(b.text for b in response.content if b.type == "text")
            results = []
            for call in calls:
                output, is_error = run_tool(self.tools, call.name, call.input, ctx)
                if isinstance(output, ToolImage):
                    self.saw_image = True  # start a fresh history next time
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": _content(output), "is_error": is_error})
            # All results for one turn go back in a single user message.
            self.messages.append({"role": "user", "content": results})
        self.reset()
        return ctx.reply("这个任务步骤太多了，我先停下。", "That took too many steps, so I stopped.")


def _content(output):
    """Tool result content: plain text, or text plus the picture (e.g. a screenshot)."""
    if isinstance(output, ToolImage):
        return [
            {"type": "image", "source": {"type": "base64", "media_type": output.media_type,
                                         "data": base64.b64encode(output.data).decode()}},
            {"type": "text", "text": output.text},
        ]
    return output


def list_models(api_key: str | None) -> list[str]:
    client = anthropic.Anthropic(api_key=api_key, timeout=15.0)
    return [m.id for m in client.models.list()]
