"""Local Ollama: is it installed and running, which models are there, which to get."""

import json
import os
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

# 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and can stall for seconds.
API = "http://127.0.0.1:11434"

# Local models that handle tool calls well, smartest first. Sizes are the download
# size of the default quantisation; `need_gb` is roughly what it takes to run smoothly.
LOCAL_MODELS = [
    {"name": "qwen3.5:27b", "size_gb": 17, "need_vram": 20, "need_total": 0,
     "note": "本地最聪明的一档，需要 20GB 以上显存的显卡。"},
    {"name": "qwen3.5:35b-a3b", "size_gb": 22, "need_vram": 6, "need_total": 36,
     "note": "比 9B 聪明很多。每次只用 3B 参数，显存放不下时借用内存也跑得动。"},
    {"name": "qwen3.5:9b", "size_gb": 6.6, "need_vram": 6, "need_total": 0,
     "note": "能整个放进 8GB 显存，反应快，但复杂指令有时会听错。"},
    {"name": "qwen3.5:4b", "size_gb": 3.3, "need_vram": 0, "need_total": 0,
     "note": "最省资源，适合没有独立显卡的电脑，比较笨。"},
]

# Run on Ollama's servers after signing in to an Ollama account. Not every cloud model is
# in the free plan; Ollama answers 402 "not in the Free plan" for the others.
CLOUD_MODELS = [
    {"name": "gemma4:31b-cloud", "paid": False,
     "note": "Google Gemma 4 31B：免费账户就能用，能看图，会操作电脑。"},
    {"name": "glm-5.3-flash:cloud", "paid": True, "note": "智谱 GLM 5.3 Flash：快，中文好。"},
    {"name": "deepseek-v4.1-flash:cloud", "paid": True, "note": "DeepSeek V4.1 Flash：快，中文好。"},
]


def executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(default) if default.exists() else None


def _get(path: str, timeout: float = 3.0):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read())


def status() -> dict:
    exe = executable()
    info = {"installed": bool(exe), "running": False, "version": "", "models": []}
    try:
        info["version"] = _get("/api/version")["version"]
        info["running"] = True
        for m in _get("/api/tags").get("models", []):
            info["models"].append({
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / 1e9, 1),
                "cloud": m["name"].endswith(":cloud") or "-cloud" in m["name"],
            })
    except OSError:
        pass
    return info


def recommend(vram_gb: float, ram_gb: float) -> list[dict]:
    """Local models this PC can run, with the best fit marked."""
    out = []
    for m in LOCAL_MODELS:
        fits = vram_gb >= m["need_vram"] and (vram_gb + ram_gb) >= max(m["need_total"], m["size_gb"] + 6)
        out.append({**m, "fits": fits, "best": False})
    for m in out:
        if m["fits"]:
            m["best"] = True
            break
    return out


def server_process_running() -> bool:
    """Is an `ollama serve` (Turing's or the tray app's own) already running?"""
    import psutil

    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower().startswith("ollama") and "serve" in (p.info["cmdline"] or []):
                return True
        except psutil.Error:
            continue
    return False


def start():
    """Start the Ollama server in the background.

    Runs `ollama serve` directly: the tray app may already be open with its server
    stopped, and opening it again wouldn't bring the server back.
    """
    exe = executable()
    if not exe:
        raise RuntimeError("没有找到 Ollama")
    if server_process_running():
        # One is already there, perhaps still starting (or failing and restarting): a
        # second one would only fight it for the port, as happened when Ollama's model
        # folder was unwritable and its own server restarted every second.
        return
    # A hidden console, not DETACHED_PROCESS: the server starts helper processes, and
    # without a console to inherit, Windows opens a visible terminal window for each.
    subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)


def sign_in():
    """Open a console running `ollama signin`; it shows a link to finish signing in."""
    exe = executable()
    if not exe:
        raise RuntimeError("没有找到 Ollama")
    # The window waits for a key after signing in, then closes itself.
    subprocess.Popen(f'cmd /c ""{exe}" signin & pause"', creationflags=subprocess.CREATE_NEW_CONSOLE)


class Downloads:
    """Background `ollama pull`s with progress the UI can poll."""

    def __init__(self):
        self.progress: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, name: str):
        with self._lock:
            if self.progress.get(name, {}).get("active"):
                return
            self.progress[name] = {"active": True, "status": "准备下载…", "pct": 0, "error": ""}
        threading.Thread(target=self._pull, args=(name,), daemon=True).start()

    def _pull(self, name: str):
        state = self.progress[name]
        req = urllib.request.Request(API + "/api/pull", method="POST",
                                     data=json.dumps({"model": name, "stream": True}).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                for line in r:
                    event = json.loads(line)
                    if "error" in event:
                        raise RuntimeError(event["error"])
                    total, done = event.get("total"), event.get("completed")
                    if total and done:
                        state["pct"] = round(done * 100 / total)
                        state["status"] = f"{done / 1e9:.1f} / {total / 1e9:.1f} GB"
                    elif event.get("status"):
                        state["status"] = event["status"]
            state.update(status="完成", pct=100)
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["active"] = False

    def snapshot(self) -> dict:
        return {k: dict(v) for k, v in self.progress.items()}
