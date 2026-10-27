"""Everything the control center page can ask the Python side to do.

pywebview exposes this object to the page as `window.pywebview.api`. Each method runs on
its own thread and returns plain JSON-able data; failures come back as {"ok": False,
"error": "..."} so the page can show them in place.
"""

import re
import threading
import webbrowser

from .. import config, secrets
from ..ai import PROVIDERS, AIError, create_brain
from ..skills import Context
from . import executors, hardware, ollama

GROUPS = {
    "ollama": "local", "claude": "intl", "openai": "intl", "muse": "intl", "deepseek": "cn",
    "qwen": "cn", "kimi": "cn", "glm": "cn", "custom": "other",
}
CLAUDE_MODEL_NOTES = {
    "claude-opus-5-5": "最聪明，每条指令约 5–8 分钱",
    "claude-sonnet-5-5": "均衡，每条指令约 2–4 分钱",
    "claude-haiku-5-5": "最快最便宜，每条指令不到 1 分钱",
}
TEST_PROMPT = {"zh": "你好，请用一句话介绍你自己。", "en": "Hi! Introduce yourself in one sentence."}


def _ok(**data):
    return {"ok": True, **data}


def _fail(e):
    return {"ok": False, "error": getattr(e, "zh", None) or str(e),
            "detail": getattr(e, "detail", ""), "kind": getattr(e, "kind", "")}


class ControlCenterApi:
    def __init__(self, engine=None):
        self._downloads = ollama.Downloads()
        self._hardware = None
        self._engine = engine
        self._floating = None  # set by run() once the orb exists

    # --- the floating orb and its bubble ------------------------------------------

    def orb_clicked(self):
        self._floating.toggle_main()
        return _ok()

    def orb_moved(self):
        self._floating.save_position()
        return _ok()

    def orb_menu(self):
        self._floating.show_menu()
        return _ok()

    def bubble_close(self):
        self._floating.close_bubble()
        return _ok()

    def bubble_hover(self, inside):
        self._floating.hover(inside)
        return _ok()

    def open_main(self):
        self._floating.open_main()
        return _ok()

    def open_ai(self):
        self._floating.open_main("ai")
        return _ok()

    def quit_app(self):
        threading.Thread(target=self._floating.quit, daemon=True).start()
        return _ok()

    # --- Turing itself (home and test pages) ------------------------------------

    def engine_status(self, since=0):
        return _ok(**self._engine.status(int(since)))

    def ui_language(self):
        return config.ui_language()

    def live_text(self):
        return _ok(state=self._engine.state, text=self._engine.partial)

    def engine_start(self):
        self._engine.start()
        return _ok()

    def engine_stop(self):
        self._engine.stop()
        return _ok()

    def type_command(self, text):
        try:
            return _ok(reply=self._engine.type_command(text.strip()))
        except Exception as e:
            return _fail(e)

    def record_test(self):
        try:
            return _ok(**self._engine.record_test())
        except Exception as e:
            return _fail(e)

    def speak_test(self):
        try:
            self._engine.speak_test("你好，我是图灵。Hi, I'm Turing.")
            return _ok()
        except Exception as e:
            return _fail(e)

    # --- settings page ------------------------------------------------------------

    def settings(self):
        from .. import lifecycle, models
        from ..engine import microphones

        cfg = config.load()
        listen = cfg["listen"]
        return _ok(
            microphones=microphones(), microphone=str(listen["device"]).strip(),
            sensitivity=int(cfg["wake"].get("sensitivity", 4)),
            asr=listen.get("asr", "auto"),
            qwen3_installed=models.installed(models.QWEN3_ASR),
            end_silence=float(listen["end_silence_seconds"]),
            follow_up=float(listen.get("follow_up_seconds", 8)),
            barge_in=bool(listen.get("barge_in", True)),
            keep_recordings=bool(listen.get("keep_recordings", True)),
            hotwords="，".join(listen.get("hotwords", [])),
            voice=cfg["voice"]["engine"],
            city=cfg.get("weather", {}).get("city", ""),
            close_to_orb=bool(cfg.get("app", {}).get("close_to_orb", True)),
            language=cfg.get("app", {}).get("language", "auto"),
            autostart=lifecycle.autostart_enabled(),
        )

    # name -> (section, key, convert, needs a listener restart)
    _SETTINGS = {
        "sensitivity": ("wake", "sensitivity", lambda v: max(1, min(5, int(v))), True),
        "asr": ("listen", "asr", lambda v: v if v in ("auto", "sensevoice", "qwen3") else "auto", True),
        "end_silence": ("listen", "end_silence_seconds", lambda v: max(0.4, min(2.0, float(v))), False),
        "follow_up": ("listen", "follow_up_seconds", lambda v: max(0.0, min(30.0, float(v))), False),
        "barge_in": ("listen", "barge_in", bool, False),
        "keep_recordings": ("listen", "keep_recordings", bool, True),
        "hotwords": ("listen", "hotwords",
                     lambda v: [w.strip() for w in re.split(r"[,，、\n]", str(v)) if w.strip()], True),
        "voice": ("voice", "engine", lambda v: v if v in ("edge", "sapi") else "edge", True),
        "city": ("weather", "city", lambda v: str(v).strip(), False),
        "microphone": ("listen", "device", lambda v: str(v).strip(), True),
        "close_to_orb": ("app", "close_to_orb", bool, False),
        "language": ("app", "language", lambda v: v if v in ("auto", "zh", "en") else "auto", False),
    }

    def set_setting(self, name, value):
        from .. import lifecycle

        try:
            if name == "autostart":
                lifecycle.set_autostart(bool(value))
                return _ok()
            section, key, convert, restart = self._SETTINGS[name]
            config.save_section(section, {key: convert(value)})
            if name == "language" and self._floating:
                self._floating.apply_language()
            if restart:
                self._engine.restart()
            return _ok()
        except Exception as e:
            return _fail(e)

    def weather_test(self):
        from ..skills import Context
        from ..skills.weather import Weather

        cfg = config.load()
        return _ok(reply=Weather(cfg).report(None, 0, Context(config=cfg, say=print)))

    def restart_app(self):
        from .. import lifecycle

        lifecycle.launch_again(after_pid=lifecycle.own_pid())
        threading.Thread(target=self._floating.quit, daemon=True).start()
        return _ok()

    # --- personas ---------------------------------------------------------------------

    def personas(self):
        from .. import personas

        return _ok(**personas.load())

    def save_personas(self, data):
        from .. import personas

        try:
            personas.save(data)
            return _ok(**personas.load())
        except Exception as e:
            return _fail(e)

    # --- reading state --------------------------------------------------------

    def state(self):
        cfg = config.load()
        ai_cfg = cfg["ai"]
        chosen = cfg.get("ai_models", {})
        urls = cfg.get("ai_urls", {})
        if self._hardware is None:
            self._hardware = hardware.summary()
        providers = []
        for p in PROVIDERS.values():
            providers.append({
                "key": p.key, "label": p.label, "group": GROUPS[p.key], "note": p.note,
                "key_url": p.key_url, "needs_key": p.needs_key,
                "has_key": bool(secrets.get_api_key(p.key)),
                "default_url": p.base_url, "url": urls.get(p.key, ""),
                "url_editable": p.kind == "openai" and p.key != "ollama",
                "models": list(p.models),
                "model_notes": CLAUDE_MODEL_NOTES if p.key == "claude" else {},
                "model": chosen.get(p.key, ""),
            })
        hw = self._hardware
        executor_cfg = cfg.get("executors", {})
        return _ok(
            active={"provider": ai_cfg.get("provider", ""), "model": ai_cfg.get("model", "")},
            providers=providers,
            hardware=hw,
            ollama={**ollama.status(),
                    "recommended": ollama.recommend(hw["vram_gb"], hw["ram_gb"]),
                    "cloud": ollama.CLOUD_MODELS},
            executors=[{"key": k, **v, "enabled": bool(executor_cfg.get(k, False))}
                       for k, v in executors.EXECUTORS.items()],
        )

    def executor_status(self, key):
        return _ok(**executors.detect(key))

    def ollama_status(self):
        return _ok(**ollama.status(), downloads=self._downloads.snapshot())

    # --- API keys and models --------------------------------------------------

    def save_key(self, provider, key):
        try:
            secrets.set_api_key(provider, key.strip())
            return _ok()
        except Exception as e:
            return _fail(e)

    def delete_key(self, provider):
        try:
            secrets.delete_api_key(provider)
            return _ok()
        except Exception as e:
            return _fail(e)

    def save_url(self, provider, url):
        config.save_section("ai_urls", {provider: url.strip()})
        return _ok()

    def _url(self, provider):
        return config.load().get("ai_urls", {}).get(provider) or PROVIDERS[provider].base_url

    def fetch_models(self, provider):
        p = PROVIDERS[provider]
        key = secrets.get_api_key(provider)
        try:
            if p.kind == "anthropic":
                from ..ai.claude import list_models

                models = list_models(key)
            else:
                from ..ai.openai_compat import list_models

                models = list_models(key or "none", self._url(provider))
            return _ok(models=models)
        except Exception as e:
            return _fail(e)

    def choose_model(self, provider, model):
        config.save_section("ai_models", {provider: model})
        return _ok()

    def test(self, provider, model):
        cfg = {"ai": {"provider": provider, "model": model, "base_url": self._url(provider)}}
        try:
            brain = create_brain(cfg, [])
            lang = config.ui_language(cfg)
            reply = brain.ask(TEST_PROMPT[lang], Context(config=cfg, say=print, zh=lang == "zh"),
                              raise_errors=True)
            return _ok(reply=reply)
        except AIError as e:
            return _fail(e)
        except Exception as e:
            return _fail(e)

    def activate(self, provider, model):
        url = config.load().get("ai_urls", {}).get(provider, "")
        config.save_section("ai", {"provider": provider, "model": model, "base_url": url})
        config.save_section("ai_models", {provider: model})
        return _ok()

    def turn_off_ai(self):
        config.save_section("ai", {"provider": "none", "model": "", "base_url": ""})
        return _ok()

    # --- Ollama ---------------------------------------------------------------

    def ollama_start(self):
        try:
            ollama.start()
            return _ok()
        except Exception as e:
            return _fail(e)

    def ollama_sign_in(self):
        try:
            ollama.sign_in()
            return _ok()
        except Exception as e:
            return _fail(e)

    def ollama_pull(self, name):
        self._downloads.start(name)
        return _ok()

    # --- task executors -------------------------------------------------------

    def set_executor(self, key, enabled):
        config.save_section("executors", {key: bool(enabled)})
        return _ok()

    # --- misc -----------------------------------------------------------------

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)
        return _ok()
