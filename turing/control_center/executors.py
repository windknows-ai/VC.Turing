"""Claude Code and Codex: the user's own subscription tools, used to carry out tasks.

Turing never reads or stores their logins. It only checks whether they're installed and
signed in, so it can hand a task to the official tool the user already uses.
"""

import json
import shutil
import subprocess

EXECUTORS = {
    "claude_code": {
        "label": "Claude Code",
        "command": "claude",
        "plan": "Claude Pro / Max 订阅",
        "install_url": "https://code.claude.com/docs/en/setup",
        "login_hint": "在终端运行 claude，按提示登录你的 Claude 账户。",
        "why_not_daily": "Anthropic 不允许其他程序借用 Claude 订阅额度当自己的 AI，",
    },
    "codex": {
        "label": "Codex",
        "command": "codex",
        "plan": "ChatGPT Plus / Pro 订阅",
        "install_url": "https://developers.openai.com/codex/cli",
        "login_hint": "在终端运行 codex login，用 ChatGPT 账户登录。",
        "why_not_daily": "OpenAI 建议其他程序调用时使用 API Key，而不是 ChatGPT 订阅，",
    },
}


def _run(args: list[str]) -> str:
    try:
        r = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "") + (r.stderr or "")


def detect(key: str) -> dict:
    info = EXECUTORS[key]
    exe = shutil.which(info["command"])
    result = {"installed": bool(exe), "version": "", "logged_in": False, "account": ""}
    if not exe:
        return result
    result["version"] = _run([exe, "--version"]).strip().splitlines()[0] if exe else ""
    if key == "claude_code":
        try:
            status = json.loads(_run([exe, "auth", "status"]))
            result["logged_in"] = bool(status.get("loggedIn"))
            # Only the kind of account, never the email or org.
            plan = status.get("subscriptionType") or ""
            result["account"] = f"Claude {plan.capitalize()} 账户" if plan else "Claude 账户"
        except json.JSONDecodeError:
            pass
    else:
        out = _run([exe, "login", "status"])
        result["logged_in"] = "Logged in" in out
        result["account"] = ("ChatGPT 账户" if "ChatGPT" in out
                             else "API Key" if "API key" in out else "")
    return result
