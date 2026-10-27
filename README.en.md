# VC.Turing · 图灵

[中文](README.md) | **English**

**A voice assistant for the Windows desktop. Call it like Siri:** just say **"Hey Turing"** (or "嗨，图灵").

```
You:    Hey Turing   (ding)
You:    Set the volume to 30
Turing: Volume 30
```

## What it can do

| Say | Turing |
|---|---|
| open Notepad · open Chrome · open Chrome with my student profile | Opens any app (fuzzy matching, English or Chinese names) or switches to it if it's already open, even WeChat hidden in the tray |
| send a WeChat message to Mom saying I'm home | Sends WeChat messages: reads it back first and **only sends when you say yes**; you can correct it on the spot |
| pause · next song · what song is this · play some jazz on YouTube · search Genshin on Bilibili | Controls whatever music or video is playing; searches and plays on websites |
| set the volume to 30 · mute · turn the brightness up · turn on dark mode · connect my headphones | Volume, brightness, dark mode; for Bluetooth, Wi-Fi and Do Not Disturb it opens the right Settings page for one click |
| what time is it · what time is it in Tokyo · what's the date next Friday · how many days until Christmas | Time, dates, world clock, holidays |
| set a timer for 10 minutes · wake me up at 7 tomorrow · start a pomodoro | Timers, alarms, pomodoro |
| what's the weather tomorrow · will it rain this weekend · how's the air quality · when is sunset | Weather, 7-day forecast, air quality, sunrise and sunset |
| 100 USD in CNY · what's the news today · what's Apple's stock price · how much is bitcoin | Exchange rates, news, stocks, crypto |
| take a note: buy milk · what are my notes · call me Alex | Notes; remembers your name and preferences |
| next desktop · maximize the window · copy · undo · take a screenshot | Virtual desktops, windows, editing shortcuts, screenshots |
| what's on my screen · what does this error mean · translate this page | Shows the AI the screen you're looking at (needs an AI that can see images) |
| ask ChatGPT what quantum computing is · search for python | Asks ChatGPT / Claude / Perplexity in the browser, or searches the web |
| how much memory is the PC using · how much battery is left · lock the screen · shut down | PC status, lock, shut down (asks first) |

Speak English, Chinese, or a mix. You can talk over Turing to interrupt it, and for 8 seconds after it
answers you can follow up without the wake word.

Everything above runs on your PC with built-in rules: instant and free. **With an AI connected** it also
understands other ways of saying things and answers questions: "it's too loud", "play a song and then
turn it down a bit", "open that photo editing app", "what is quantum computing". The AI can only claim
what it really did: an answer that says "done" when nothing was done is caught and corrected.

## AI providers

On first run Turing opens its **settings window**; reopen it any time with `python -m turing --setup`. The
top of the window shows each step your words go through and which ones stay on your PC. Providers are
grouped by how you pay:

| Group | Includes | Who pays |
|---|---|---|
| **Free** | Ollama local models | Nothing. The window checks your graphics card and memory, recommends the smartest model your PC can run, and downloads it. With a free Ollama account you can also use cloud models (free allowance) |
| **API key, pay per use** | Claude, OpenAI, DeepSeek, Qwen, Kimi, Zhipu GLM, any compatible service | Your balance with the provider. Claude Haiku, DeepSeek and similar cost well under a cent per command; Claude Opus about a cent |
| **Tasks on your subscription** | Claude Code, Codex | Your Claude / ChatGPT subscription. Turing hands big tasks to the official tools already signed in on your PC (coming in the next version) |

A subscription can't be Turing's everyday AI: Anthropic doesn't allow other programs to use Claude
subscription limits, OpenAI recommends API keys for programs, and each start takes seconds, too slow
for a voice conversation.

**Each user brings their own API key. It's stored only in Windows Credential Manager on your PC**, never
in a config file, and never uploaded.

## Privacy

- Wake word detection and speech recognition run **entirely on your PC**; nothing you say before the
  wake word leaves it.
- Only commands the built-in rules can't handle are sent, as text, to the AI provider you chose (with an
  Ollama local model, nothing leaves your PC).
- Screenshots are taken only when you ask about your screen, only of the screen you're looking at, and
  go only to the AI you chose.
- Replies are spoken with Microsoft's online Edge voices by default (only the reply text is sent). To stay
  offline, set `engine = "sapi"` in the config.

## Install

Needs Windows 10/11 and [Python 3.11+](https://www.python.org/downloads/).

```bash
git clone https://github.com/windknows-ai/VC.Turing.git
cd VC.Turing
start.bat
```

The first time, `start.bat` installs everything, adds a **图灵** (Turing) shortcut to the desktop and Start
menu, and opens the Turing app. After that, open Turing from the shortcut. The first start downloads about
190 MB of speech models.

A **floating orb** sits in the bottom-right corner: click it to talk, drag it anywhere. The bubble beside
it shows what you're saying and Turing's reply as they happen.

The Turing app has five pages (switch the interface to English in Settings):

- **Home**: whether Turing is listening, the conversation, start / pause listening, and a box to type commands.
- **AI**: which AI Turing uses (local Ollama, international, Chinese providers, or custom).
- **Personas**: Turing's personality and way of speaking; pick a preset or write your own.
- **Settings**: microphone, wake sensitivity, interrupting, speech recognizer, voice, start with Windows, interface language.
- **Test**: try the microphone, type instead of talking, hear the voice.

**More accurate speech recognition (optional)**: by default Turing uses SenseVoice, which is small and fast.
For mixed Chinese and English or strong accents, download Qwen3-ASR (about 840 MB). Turing then listens
again with it when it hears English or when you dictate a message (not when less than 3 GB of memory is free):

```bash
.venv\Scripts\python -m turing.models qwen3-asr
```

Manual install:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\create_shortcuts.py
.venv\Scripts\pythonw -m turing.desktop
```

## Configuration

The first run creates `%APPDATA%\Turing\config.toml`, with every option explained in English and Chinese:

- wake words (any English or Chinese words, **no training needed**) and sensitivity
- microphone, voice, speaking speed
- app aliases, such as `"music" = "Spotify"`
- a download mirror for the models (if GitHub is slow for you)

## Testing

```bash
python -m turing              # run in the console, no window
python -m turing --text        # type instead of talking
python -m turing --apps        # list the apps Turing can open
python -m turing --devices     # list microphones
pip install pytest && python -m pytest       # all tests
python scripts/mutation_check.py              # put fixed bugs back and check the tests catch them
python scripts/scenario_eval.py               # dry-run 172 everyday commands (nothing really happens)

# full pipeline with synthetic speech, no microphone needed
python scripts/make_test_wavs.py .scratch
python -m turing --wav .scratch/zh.wav --quiet
```

Every bug fixed so far (67 at the moment), and the test that keeps it fixed, is listed in
[tests/README_REGRESSIONS.md](tests/README_REGRESSIONS.md).

## How it works

```
microphone → wake word (sherpa-onnx, local) → ding → voice activity detection (Silero VAD)
           → speech recognition (SenseVoice / Qwen3-ASR, local, mixed Chinese and English)
           → built-in rules → do it → spoken reply
                  ↓ no rule matched
             AI (using the same skills as tools)
```

Each feature is a skill in `turing/skills/`: `handle()` is the fast built-in rule, and `tools()` offers the
same ability to the AI. To add one, subclass `Skill` and register it in `load_skills`. Pull requests welcome.

## Credits

[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) · [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) ·
[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) · [pywebview](https://github.com/r0x0r/pywebview) ·
[Silero VAD](https://github.com/snakers4/silero-vad) · [edge-tts](https://github.com/rany2/edge-tts) ·
[pycaw](https://github.com/AndreMiras/pycaw) · [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) ·
[OpenAI SDK](https://github.com/openai/openai-python) · [Ollama](https://ollama.com)

## License

[MIT](LICENSE)
