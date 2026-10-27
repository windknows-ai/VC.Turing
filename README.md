# VC.Turing · 图灵

**Windows 桌面语音助手，像小爱同学、Siri 一样直接喊它。**
A voice assistant for the Windows desktop. Just say **"嗨，图灵"** or **"Hey Turing"**.

```
你：嗨，图灵   (叮~)
你：把音量调到 30
图灵：音量 30
```

## 现在能做什么 / What it can do

| 说 / Say | 做 / Does |
|---|---|
| 打开微信 · 打开记事本 · open Chrome · 用 student 账号打开谷歌浏览器 | 打开任何软件（拼音模糊匹配、中英文名都行），已开着的直接切过去，包括藏在托盘里的微信 |
| 给妈妈发微信说我到家了 | 发微信消息：先念给你听，**你说"发"才发**，可以当场改 |
| 播放 · 下一首 · 这是什么歌 · 在 YouTube 放点爵士乐 · 在 B 站搜原神 | 控制正在播放的音乐和视频，在网站上搜索、播放 |
| 音量调到 30 · 静音 · 亮度调高 · 打开深色模式 · 连上蓝牙耳机 | 音量、亮度、深色模式；蓝牙、Wi-Fi、勿扰模式会打开对应的设置页，你点一下就好 |
| 几点了 · 东京现在几点 · 下周五是几号 · 春节还有几天 | 时间、日期、世界时间、节假日 |
| 十分钟后提醒我喝水 · 明早 7 点叫我 · 开个番茄钟 | 计时器、闹钟、番茄钟 |
| 明天天气怎么样 · 周末会下雨吗 · 空气质量 · 几点日落 | 天气、7 天预报、空气质量、日出日落 |
| 100 美元换人民币 · 今天有什么新闻 · 苹果股价 · 比特币多少钱 | 汇率、新闻、股票、加密货币 |
| 记一下明天交作业 · 我记了什么 · 以后叫我小明 | 备忘、记住你的名字和习惯 |
| 切到下一个桌面 · 把窗口最大化 · 复制 · 撤销 · 截图 | 虚拟桌面、窗口、编辑快捷键、截图 |
| 屏幕上是什么 · 这个报错什么意思 · 把这页翻译一下 | 把你正在看的屏幕交给 AI 看（需要能看图的 AI） |
| 问一下 ChatGPT 量子计算是什么 · 搜索 python | 在浏览器里问 ChatGPT / Claude / Perplexity，或直接搜索 |
| 电脑内存用了多少 · 电池还剩多少 · 锁屏 · 关机 | 电脑状态、锁屏、关机（关机会先问你） |

中英文都能说，也可以混着说。Chinese, English, or a mix. 图灵说话时可以直接插话打断它；回答完 8 秒内接着说，
不用再喊名字。You can talk over Turing to interrupt it, and follow up without the wake word.

上面这些指令在本地直接执行，又快又免费。**接入 AI 之后**，换种说法它也能听懂，还能回答问题：
"太吵了"、"放首歌然后调小声一点"、"帮我打开那个修图软件"、"量子计算是什么"。
AI 只能说它真正做过的事：没有执行就声称"已完成"的回答会被拦下来改正。

## AI 服务 / AI providers

第一次运行会打开**图灵设置**窗口，随时可以用 `python -m turing --setup` 再打开。窗口顶部会显示你说的话经过哪些步骤、
哪些在本机完成；左边按付费方式分成三组：

| 分组 | 包括 | 花谁的钱 |
|---|---|---|
| **免费** | Ollama 本地模型 | 不花钱。窗口会检测你的显卡和内存，推荐跑得动的最聪明的模型，并能直接下载。登录免费的 Ollama 账户后还能用云端模型（有免费额度） |
| **填 API Key，按用量付费** | Claude、OpenAI、DeepSeek、通义千问、Kimi、智谱 GLM、其他兼容服务 | 你在服务商那里的余额。Claude Haiku、DeepSeek 等每条指令不到 1 分钱，Claude Opus 约 5–8 分钱 |
| **用你的订阅执行任务** | Claude Code、Codex | 你的 Claude / ChatGPT 订阅额度。图灵会把大任务交给你电脑上已登录的官方工具去做（下一个版本启用） |

订阅不能当图灵的日常 AI：Anthropic 不允许其他程序借用 Claude 订阅额度，OpenAI 也建议程序调用时使用 API Key，
而且每次启动要等好几秒，对语音对话太慢。

**API Key 由每个用户自己申请，只保存在本机的 Windows 凭据管理器里**，不会写进配置文件，也不会上传。
Each user brings their own API key; it's stored in Windows Credential Manager, never in files.

## 隐私 / Privacy

- 唤醒词检测和语音识别**完全在本机运行**，唤醒之前的声音不会离开你的电脑。
  Wake word detection and speech recognition run entirely on your PC.
- 只有本地规则处理不了的指令文字，才会发给你选择的 AI 服务（选 Ollama 本地模型则完全不出本机）。
  Only commands the local rules can't handle are sent, as text, to the AI provider you chose.
- 只有你让图灵看屏幕时才会截图，只截你正在看的那块屏幕，并只发给你选的 AI。
  Screenshots are taken only when you ask about your screen, and go only to the AI you chose.
- 默认用微软 Edge 在线语音朗读回复（只发送回复文字）。不想联网可以在配置里改成 `sapi`。
  Replies are spoken with Microsoft's online Edge voices by default; set `engine = "sapi"` to stay offline.

## 安装 / Install

需要 Windows 10/11 和 [Python 3.11+](https://www.python.org/downloads/)。

```bash
git clone https://github.com/windknows-ai/VC.Turing.git
cd VC.Turing
start.bat
```

第一次双击 `start.bat` 会自动安装依赖，在桌面和开始菜单里放一个 **图灵** 图标，然后打开图灵 APP。
以后直接双击桌面上的 **图灵** 就行。第一次启动会下载约 190 MB 的语音模型。
Double-click `start.bat` once; it installs everything and adds a 图灵 shortcut to the desktop and
Start menu. After that, open Turing from the shortcut.

桌面右下角会有一个**悬浮球**：点它说话，拖它换位置，它旁边的气泡会实时显示你说的话和图灵的回答。
A floating orb sits above the taskbar: click it to talk, drag it anywhere; its bubble shows what you
said and the reply as you speak.

图灵 APP 有五页 / The app has five pages (中文 / English，设置里切换):

- **首页**：图灵是否在听、对话记录、开始 / 暂停聆听，也可以打字给指令。
- **AI 连接**：选择图灵用哪个 AI（本机 Ollama、国外、国内、自定义）。
- **人设**：图灵的性格和说话方式，有几种预设，也可以自己写。
- **设置**：麦克风、叫醒灵敏度、插话打断、语音识别、声音、开机启动、界面语言。
- **测试**：试麦克风、打字代替说话、试听声音。

**更准的语音识别（可选）**：默认用又快又小的 SenseVoice。中英混说、口音重时，可以另外下载 Qwen3-ASR
（约 840 MB），图灵会在听到英文或你在口述消息时自动换它再听一遍（空闲内存少于 3 GB 时不用）：
Optional, more accurate recognizer for mixed Chinese and English:

```bash
.venv\Scripts\python -m turing.models qwen3-asr
```

手动安装 / Manual:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\create_shortcuts.py
.venv\Scripts\pythonw -m turing.desktop
```

## 配置 / Configuration

第一次运行会生成 `%APPDATA%\Turing\config.toml`，里面每一项都有中英文说明，可以改：

- 唤醒词（任意中文或英文，**不需要训练**）和灵敏度
- 麦克风、语音音色、语速
- 软件别名，比如 `"网易云" = "网易云音乐"`
- 模型下载镜像（GitHub 访问慢时用）

## 调试 / Testing

```bash
python -m turing              # 不开窗口，在命令行里运行 / run in the console, no window
python -m turing --text        # 打字代替说话 / type instead of talking
python -m turing --apps        # 列出能打开的软件 / list openable apps
python -m turing --devices     # 列出麦克风 / list microphones
pip install pytest && python -m pytest       # 全部测试 / all tests
python scripts/mutation_check.py              # 把修过的旧 bug 放回去，确认测试都能抓到 / old bugs stay caught
python scripts/scenario_eval.py               # 试跑 172 条日常指令（不真的执行）/ dry-run 172 everyday commands

# 用合成语音测试整条流程，不需要麦克风 / full pipeline test without a mic
python scripts/make_test_wavs.py .scratch
python -m turing --wav .scratch/zh.wav --quiet
```

每个修过的 bug（目前 65 个）和挡住它的测试都列在 [tests/README_REGRESSIONS.md](tests/README_REGRESSIONS.md)。
Every bug fixed so far, and the test that keeps it fixed, is listed there.

## 工作原理 / How it works

```
麦克风 → 唤醒词检测（sherpa-onnx，本地）→ 叮 → 语音活动检测（Silero VAD）
      → 语音识别（SenseVoice / Qwen3-ASR，本地，中英混合）→ 本地规则匹配 → 执行 → 语音回复
                                                  ↓ 没匹配上
                                     AI（调用同一批技能作为工具）
```

每个功能都是 `turing/skills/` 里的一个"技能"：`handle()` 负责本地规则，`tools()` 把同样的能力
提供给 AI。想加新功能，写一个 `Skill` 子类并在 `load_skills` 里注册即可，欢迎提 PR。
Each feature is a skill in `turing/skills/`: `handle()` is the fast local rule, `tools()` offers the
same ability to the AI. Subclass `Skill`, register it in `load_skills`, and send a PR.

## 致谢 / Credits

[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) · [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) ·
[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) · [pywebview](https://github.com/r0x0r/pywebview) ·
[Silero VAD](https://github.com/snakers4/silero-vad) · [edge-tts](https://github.com/rany2/edge-tts) ·
[pycaw](https://github.com/AndreMiras/pycaw) · [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) ·
[OpenAI SDK](https://github.com/openai/openai-python) · [Ollama](https://ollama.com)

## 许可证 / License

[MIT](LICENSE)
