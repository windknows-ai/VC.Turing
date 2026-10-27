"use strict";

// The app is written in Chinese; in English mode every Chinese phrase on screen is swapped
// for its English version as it appears, including text the scripts add later. What the
// user wrote or said (marked translate="no") is never touched.
// setLang() is called once the language is known (and again when it's changed).

let LANG = "zh";

const t = (zh, en) => (LANG === "en" ? en : zh);

const I18N = {
  // navigation and frame
  "图灵": "Turing", "页面": "Pages", "首页": "Home", "AI 连接": "AI", "人设": "Personas",
  "设置": "Settings", "测试": "Test", "退出图灵": "Quit Turing",
  "关掉这个窗口后，图灵会在屏幕角落的小圆球里继续听。点小圆球就能回到这里。":
    "Close this window and Turing keeps listening in the little orb in the corner of the screen. Click the orb to come back here.",

  // home
  "图灵没有在听": "Turing isn't listening", "点下面的按钮开始。": "Press the button below to start.",
  "开始聆听": "Start listening", "暂停聆听": "Pause listening", "对话": "Conversation",
  "还没有对话。试着说\"嗨图灵，现在几点了\"，或者\"嗨图灵，屏幕上这个报错是什么意思\"。":
    "No conversation yet. Try \"Hey Turing, what time is it?\" or \"Hey Turing, what does this error on my screen mean?\"",
  "打字给图灵下指令": "Type a command for Turing",
  "打字给图灵下指令，比如：打开记事本": "Type a command for Turing, e.g. open Notepad",
  "发送": "Send", "正在准备…": "Getting ready…",
  "第一次启动会下载语音模型，需要一会儿。": "The first start downloads the speech models; it takes a little while.",
  "说「嗨，图灵」叫醒我": "Say \"Hey Turing\" to wake me",
  "可以一口气说完，比如「嗨图灵，打开微信」。": "You can say it all at once, e.g. \"Hey Turing, open WeChat\".",
  "在听…": "Listening…", "说完停一下就好。": "Just pause when you're done.", "想一想…": "Thinking…",
  "你": "You", "出错": "Error", "AI：": "AI: ", "默认模型": "Default model", "未开启": "Off",
  "没有连接 AI，只听懂本地指令。去连接": "No AI connected: only local commands work. Connect one",

  // AI page
  "图灵用哪个 AI": "Which AI Turing uses", "你说的话会经过这些步骤": "What happens to what you say",
  "麦克风": "Microphone", "本机": "This PC", "听到「嗨，图灵」": "Hears \"Hey Turing\"",
  "语音转文字": "Speech to text", "本地指令": "Local commands", "本机，免费": "This PC, free",
  "打开软件、调音量、播放暂停这类指令在本机直接完成。只有本地指令听不懂的话，才会以文字发给你在这里选的 AI。你让图灵看屏幕时，那一刻的截图也会发给这个 AI；选 Ollama 本地模型的话，截图不会离开你的电脑。":
    "Commands like opening apps, changing the volume or play/pause are done right here on your PC. Only what the local commands don't understand is sent, as text, to the AI you choose here. When you ask Turing to look at the screen, that screenshot goes to this AI too; with a local Ollama model it never leaves your PC.",
  "AI 来源": "AI sources", "正在读取设置…": "Loading settings…",
  "正在使用": "In use", "未安装": "Not installed", "未启动": "Not running", "已填 Key": "Key saved",
  "检查中…": "Checking…", "已登录": "Signed in", "未登录": "Not signed in", "当前": "Current",
  "在本机运行（免费）": "Runs on this PC (free)", "国外（填 API Key）": "International (API key)",
  "国内（填 API Key）": "China (API key)", "其他": "Other",
  "用你的订阅执行任务": "Use your subscription for tasks", "不使用 AI": "No AI",
  "还没有模型。": "No models yet.", "模型": "Models", "测试连接": "Test connection",
  "图灵正在用这个 AI": "Turing is using this AI", "让图灵用这个 AI": "Use this AI for Turing",
  "将使用模型": "Will use the model",
  "。图灵下次被叫醒时就会用上，不用重启。": ". Turing uses it the next time it's woken; no restart needed.",
  "已保存在本机的 Windows 凭据管理器里。": "Saved in Windows Credential Manager on this PC.",
  "换一个 Key": "Replace key", "删除 Key": "Delete key",
  "Key 只保存在本机的 Windows 凭据管理器里，不会写进文件，也不会上传。":
    "The key is kept only in Windows Credential Manager on this PC: never written to a file, never uploaded.",
  "接口地址": "API address", "保存地址": "Save address", "一般不用改。": "Usually no need to change this.",
  "注册并创建 API Key": "Sign up and create an API key",
  "需要在服务商那里充值或开通，费用由你和服务商直接结算。":
    "You may need to add credit or activate a plan with the provider; you pay them directly.",
  "填写 API Key": "Enter your API key", "选择模型": "Choose a model", "或者直接填模型名": "Or type a model name",
  "模型名": "Model name", "使用": "Use", "测试并使用": "Test and use", "粘贴 API Key": "Paste your API key",
  "保存 Key": "Save key", "下载并安装 Ollama": "Download and install Ollama",
  "打开 Ollama 下载页": "Open the Ollama download page", "装好后回到这里": "Come back here once it's installed",
  "重新检测": "Check again", "Ollama 已安装，但还没有启动。": "Ollama is installed but not running.",
  "启动 Ollama": "Start Ollama", "云端": "Cloud", "显卡": "Graphics card", "显存": "Video memory",
  "内存": "Memory", "未检测到独立显卡": "No dedicated graphics card found",
  "选一个模型给图灵用": "Choose a model for Turing",
  "还没有下载模型。从下面选一个下载。": "No models downloaded yet. Pick one below.",
  "你现在的模型都比较小，可能会听错指令。你的电脑能跑": "Your models are small and may get commands wrong. Your PC can run",
  "，会聪明很多。": ", which is much smarter.",
  "下载本地模型": "Download a local model",
  "本地模型免费、不联网。越大越聪明，也越吃显卡。": "Local models are free and work offline. Bigger ones are smarter but need more graphics power.",
  "云端模型": "Cloud models",
  "在 Ollama 的服务器上运行，比本地模型聪明、也更快，不占你的显卡。需要登录 Ollama 账户。免费账户只能用标了\"免费可用\"的模型，额度每 5 小时和每周刷新；其他的要付费会员。":
    "Run on Ollama's servers: smarter and faster than local models, and they don't use your graphics card. You need to sign in to Ollama. Free accounts can only use models marked \"Free to use\", with limits that reset every 5 hours and every week; the others need a paid plan.",
  "登录 Ollama 账户": "Sign in to Ollama",
  "会打开一个命令行窗口，按提示在浏览器里登录。": "Opens a command window; follow its steps to sign in in your browser.",
  "下载": "Download", "添加": "Add", "已下载": "Downloaded", "已添加": "Added",
  "需要 Ollama 付费会员": "Needs a paid Ollama plan", "免费可用": "Free to use",
  "最适合你的电脑": "Best for your PC", "你的电脑可能跑不动": "May be too much for your PC",
  "准备下载…": "Preparing…", "完成": "Done", "查看安装方法": "How to install",
  "它怎么工作": "How it works", "这个功能会在下一个版本启用。": "This arrives in the next version.",
  "图灵只执行本地指令：打开软件、播放暂停、调音量、报时、计时、锁屏、网页搜索。完全免费，什么都不会发出去。听不懂的话，它会直接告诉你。":
    "Turing only runs local commands: open apps, play/pause, volume, time, timers, lock screen, web search. Completely free, and nothing is sent anywhere. If it doesn't understand, it says so.",
  "已关闭 AI": "AI is off", "关闭 AI": "Turn AI off",
  "正在保存…": "Saving…", "正在获取…": "Fetching…", "正在测试…": "Testing…", "正在启动…": "Starting…",
  "已打开登录窗口": "Sign-in window opened", "开始下载…": "Starting download…",
  "服务商没有返回任何模型。": "The provider returned no models.",

  // providers (names and notes come from Python)
  "通义千问": "Qwen", "智谱": "Zhipu GLM", "自定义": "Custom",
  "Anthropic 的 AI。理解力和操作电脑最强，中英文都好。国内需要能访问国外网络。":
    "Anthropic's AI. The best at understanding and at using the computer; great in English and Chinese.",
  "ChatGPT 背后的公司。API 按用量付费，和 ChatGPT 会员是分开的。国内需要能访问国外网络。":
    "The company behind ChatGPT. The API is pay-as-you-go and separate from a ChatGPT subscription.",
  "Meta 的 AI（Muse Spark），能看图，会操作电脑。目前只对美国的开发者开放预览，国内需要能访问国外网络。":
    "Meta's AI (Muse Spark). Sees images and can use the computer. Currently a preview for US developers.",
  "国内直接能用，很便宜。": "Works in China; very cheap.",
  "阿里云的 AI，国内直接能用，新用户有免费额度。": "Alibaba Cloud's AI. Works in China; free credit for new users.",
  "月之暗面的 AI，国内直接能用。": "Moonshot AI. Works in China.",
  "智谱 GLM，国内直接能用，flash 模型很便宜。": "Zhipu GLM. Works in China; the flash models are very cheap.",
  "在本机运行开源模型，不花钱、不联网。模型越大越聪明，但需要更好的显卡。登录免费的 Ollama 账户后，还能用有免费额度的云端模型。":
    "Runs open models on this PC: free and offline. Bigger models are smarter but need a better graphics card. With a free Ollama account you can also use cloud models with a free allowance.",
  "其他兼容 OpenAI 接口的服务。填上服务商给的接口地址、模型名和 API Key。":
    "Any other OpenAI-compatible service. Enter the address, model name and API key your provider gives you.",
  "最聪明；每条指令约 5–8 分钱": "Smartest; about ¥0.05–0.08 per command",
  "均衡；每条指令约 2–4 分钱": "Balanced; about ¥0.02–0.04 per command",
  "最快最便宜；每条指令不到 1 分钱": "Fastest and cheapest; under ¥0.01 per command",
  "最聪明，每条指令约 5–8 分钱": "Smartest; about ¥0.05–0.08 per command",
  "均衡，每条指令约 2–4 分钱": "Balanced; about ¥0.02–0.04 per command",
  "最快最便宜，每条指令不到 1 分钱": "Fastest and cheapest; under ¥0.01 per command",
  "本地最聪明的一档，需要 20GB 以上显存的显卡。": "The smartest local tier; needs a graphics card with 20 GB+ of video memory.",
  "比 9B 聪明很多。每次只用 3B 参数，显存放不下时借用内存也跑得动。":
    "Much smarter than 9B. Uses only 3B parameters at a time, so it still runs when it spills into system memory.",
  "能整个放进 8GB 显存，反应快，但复杂指令有时会听错。": "Fits entirely in 8 GB of video memory and is quick, but sometimes gets complex commands wrong.",
  "最省资源，适合没有独立显卡的电脑，比较笨。": "The lightest; for PCs without a dedicated graphics card. Not very smart.",
  "Google Gemma 4 31B：免费账户就能用，能看图，会操作电脑。": "Google Gemma 4 31B: works on a free account, sees images and can use the computer.",
  "智谱 GLM 5.3 Flash：快，中文好。": "Zhipu GLM 5.3 Flash: fast, great at Chinese.",
  "DeepSeek V4.1 Flash：快，中文好。": "DeepSeek V4.1 Flash: fast, great at Chinese.",
  "Claude Pro / Max 订阅": "Claude Pro / Max subscription", "ChatGPT Plus / Pro 订阅": "ChatGPT Plus / Pro subscription",
  "在终端运行 claude，按提示登录你的 Claude 账户。": "Run claude in a terminal and follow its steps to sign in to your Claude account.",
  "在终端运行 codex login，用 ChatGPT 账户登录。": "Run codex login in a terminal and sign in with your ChatGPT account.",
  "Claude 账户": "Claude account", "ChatGPT 账户": "ChatGPT account",

  // personas
  "给图灵设定角色、回答风格和要求。可以存好几套，随时切换。只对接入 AI 后的回答生效。":
    "Give Turing a role, an answer style and rules. Save several and switch any time. Applies to answers from the AI.",
  "人设列表": "Personas", "名字": "Name", "角色": "Role",
  "比如：一位耐心的老师；留空就是图灵自己": "e.g. a patient teacher; leave empty for Turing itself",
  "回答风格": "Answer style", "比如：先说结论，再举一个生活中的例子": "e.g. give the conclusion first, then an everyday example",
  "行为要求": "Rules", "比如：遇到专业名词顺带解释；不要主动推荐购物": "e.g. explain technical terms; don't suggest buying things",
  "保存并使用": "Save and use", "只保存": "Save only", "新建": "New", "删除": "Delete", "已保存。": "Saved.",

  // settings
  "改完马上生效，不用重启。": "Changes apply right away; no restart needed.",
  "叫醒和对话": "Waking and conversation", "叫醒灵敏度": "Wake sensitivity",
  "叫不醒就调高；没叫它却自己醒了就调低。可以说\"嗨图灵\"\"Hey 图灵\"，或者在一句话开头直接说\"图灵\"。":
    "Raise it if Turing doesn't wake; lower it if it wakes by itself. Say \"Hey Turing\", \"嗨图灵\", or just \"图灵\" at the start of a sentence.",
  "不容易醒": "Hard to wake", "适中": "Medium", "很容易醒": "Easy to wake",
  "说完后等多久": "How long to wait after you stop",
  "停顿超过这个时间就算说完了。话说到一半（比如\"然后\"）时会自动多等一会儿。":
    "A pause longer than this ends the command. It waits longer when you trail off mid-sentence (\"and then…\").",
  "反应快": "Quick", "不打断我": "Don't cut me off", "连续对话": "Follow-up",
  "图灵回答后，这段时间内你可以直接接着说，不用再喊\"图灵\"。":
    "After Turing answers, you can keep talking for this long without saying \"Turing\" again.",
  "关闭，每次都要喊": "Off: always say its name", "插话打断": "Interrupting",
  "图灵说话或思考时，你直接开口它就停下来听你说。": "Start talking while Turing speaks or thinks and it stops to listen.",
  "允许打断图灵": "Let me interrupt Turing",
  "用外放音箱时，如果图灵老是自己打断自己，就关掉这个。": "On speakers, turn this off if Turing keeps interrupting itself.",
  "识别": "Recognition", "语音识别": "Speech recognition",
  "自动：平时用快的；听到英文（中英混说）时换更准的再听一遍。":
    "Auto: the fast one normally; English, mixed speech and messages are checked again by the accurate one.",
  "自动（推荐）": "Auto (recommended)", "只用快的（SenseVoice）": "Fast only (SenseVoice)",
  "只用准的（Qwen3-ASR，每句慢约 1 秒）": "Accurate only (Qwen3-ASR, about 1 s slower)",
  "更准的识别模型还没下载，现在都用快的。下载：在图灵文件夹里运行": "The accurate model isn't downloaded yet, so the fast one is used. To get it, in the Turing folder run",
  "（约 840 MB），然后重启图灵。": "(~840 MB), then restart Turing.",
  "常用词": "Your words",
  "联系人名字、常用软件名等，写在这里更容易听对。用逗号隔开。": "Contact names, apps you use and so on are heard right more often if listed here. Separate them with commas.",
  "比如：土豆，Discord，奥克维尔": "e.g. Tudou, Discord, Oakville", "保存": "Save", "已保存": "Saved",
  "换了耳机或麦克风，图灵会自动跟着系统默认设备走。": "Switch headphones or microphones and Turing follows the system default.",
  "跟随系统默认麦克风": "System default microphone",
  "保留录音": "Keep recordings",
  "在这台电脑上保存最近 30 条指令的录音，方便排查听错的问题。不会上传。":
    "Keep the last 30 commands' audio on this PC to look into mishearings. Never uploaded.",
  "保留最近的录音": "Keep recent recordings", "回答": "Answers", "图灵的声音": "Turing's voice",
  "在线声音更自然；离线声音不需要联网。": "The online voice sounds more natural; the offline one needs no internet.",
  "声音": "Voice", "在线声音（推荐）": "Online voice (recommended)", "离线声音（Windows 自带）": "Offline voice (built into Windows)",
  "试听": "Listen", "所在城市": "Your city",
  "问天气时没说城市，就查这里。留空就按网络位置判断。": "Used for weather when you don't name a city. Leave empty to guess from your internet connection.",
  "比如：奥克维尔、Oakville、北京": "e.g. Oakville, Toronto, Beijing", "保存并查天气": "Save and check weather",
  "运行": "Running", "关闭窗口时": "When closing the window", "收到小圆球里，继续听": "Tuck into the orb and keep listening",
  "彻底退出图灵": "Quit Turing", "开机自动启动": "Start with Windows",
  "开机后图灵以小圆球的样子待在屏幕角落。": "Turing waits as the little orb in the corner of the screen.",
  "开机时启动图灵": "Start Turing when Windows starts", "重启图灵": "Restart Turing",
  "遇到听不见、没反应时试试。设置和最近的对话都会保留。": "Try this if Turing stops hearing or responding. Settings and recent conversation are kept.",
  "正在重启…": "Restarting…", "界面语言": "Language", "界面语言 Language": "Language", "跟随系统": "Same as Windows",
  "图灵界面显示的语言。图灵说话用你对它说的语言。": "The language of Turing's windows. Turing always answers in the language you speak.",

  // test page
  "图灵听不清、听不懂的时候，在这里检查。": "Check here when Turing can't hear or understand you.",
  "录 4 秒，看看图灵听到了什么。": "Record 4 seconds and see what Turing heard.",
  "录 4 秒试试": "Record 4 seconds", "正在录音，请说话…": "Recording, speak now…", "没听清。": "Didn't catch that.",
  "声音很小，离麦克风近一点，或者在 Windows 声音设置里调高麦克风音量。":
    "Very quiet. Move closer to the microphone, or turn up its level in Windows sound settings.",

  // orb and bubble
  "图灵：点一下打开，右键更多": "Turing: click to open, right-click for more",
  "打开图灵": "Open Turing",
};

// Text with names or numbers in it. Captured parts are translated too where they're ours.
const I18N_PATTERNS = [
  [/^AI：(.+)$/, (m) => `AI: ${tr(m[1])}`],
  [/^([\d.]+) 秒$/, (m) => `${m[1]} s`],
  [/^(.+)（默认）$/, (m) => `${m[1]} (default)`],
  [/^(\d+) 个模型$/, (m) => `${m[1]} models`],
  [/^服务商返回：([\s\S]*)$/, (m) => `The provider said: ${m[1]}`],
  [/^打开 (.+) 网站充值$/, (m) => `Add credit on the ${tr(m[1])} website`],
  [/^打开 (.+) 的 Key 页面$/, (m) => `Open ${tr(m[1])}'s API key page`],
  [/^从 (.+) 获取全部模型$/, (m) => `Get all models from ${tr(m[1])}`],
  [/^下载失败：([\s\S]*)$/, (m) => `Download failed: ${m[1]}`],
  [/^连接成功。AI 说：([\s\S]*)$/, (m) => `Connected. The AI says: ${m[1]}`],
  [/^获取模型失败：([\s\S]*)$/, (m) => `Couldn't get the models: ${m[1]}`],
  [/^正在检查 (.+)…$/, (m) => `Checking ${m[1]}…`],
  [/^还没有安装 (.+)。$/, (m) => `${m[1]} isn't installed yet.`],
  [/^已安装（(.+)），但还没有登录。$/, (m) => `Installed (${m[1]}) but not signed in.`],
  [/^已登录：(.+)$/, (m) => `Signed in: ${tr(m[1])}`],
  [/^Claude (\S+) 账户$/, (m) => `Claude ${m[1]} account`],
  [/^版本 (.+)$/, (m) => `Version ${m[1]}`],
  [/^(.+) API Key$/, (m) => `${tr(m[1])} API key`],
  [/^用你的 (.+?) ?额度，完成检索文件、写代码这类比较大的任务。$/,
    (m) => `Use your ${tr(m[1])} for bigger jobs like finding files and writing code.`],
  [/^你说"嗨图灵，用 (.+?) 帮我在下载文件夹里找那份合同"，图灵会在终端里打开你电脑上的 (.+?)，把任务交给它。整个过程都在 (.+?) 里进行，你能看到每一步。图灵不会读取或保存你的登录信息。$/,
    (m) => `Say "Hey Turing, use ${m[1]} to find that contract in my Downloads folder" and Turing opens ${m[2]} on your PC in a terminal and hands it the task. Everything happens inside ${m[3]}, where you can watch each step. Turing never reads or stores your sign-in.`],
  [/^允许图灵把任务交给 (.+)$/, (m) => `Let Turing hand tasks to ${m[1]}`],
  [/^订阅不能当图灵的日常 AI。([\s\S]*?)而且每次启动要等好几秒，语音对话会太慢。日常对话请在左边选 Ollama 或一个 API。$/,
    (m) => `A subscription can't be Turing's everyday AI. ${tr(m[1])} and each start takes several seconds, too slow for conversation. For everyday use, choose Ollama or an API on the left.`],
  [/^Anthropic 不允许其他程序借用 Claude 订阅额度当自己的 AI，$/, () => "Anthropic doesn't allow other programs to use a Claude subscription as their AI,"],
  [/^OpenAI 建议其他程序调用时使用 API Key，而不是 ChatGPT 订阅，$/, () => "OpenAI asks other programs to use an API key rather than a ChatGPT subscription,"],
  [/^已经有一个叫“(.+)”的人设了，换个名字吧。$/, (m) => `There's already a persona called "${m[1]}". Pick another name.`],
  [/^已保存，图灵现在用“(.+)”。$/, (m) => `Saved. Turing now uses "${m[1]}".`],
  [/^听到：([\s\S]*)$/, (m) => `Heard: ${m[1]}`],
  [/^你：([\s\S]*)$/, (m) => `You: ${m[1]}`],
  [/^“([\s\S]*)”$/, (m) => `"${m[1]}"`],
];

const _ZH = /[一-鿿]/;

function tr(text) {
  const key = String(text).replace(/\s+/g, " ").trim();
  if (LANG !== "en" || !_ZH.test(key)) return text;
  if (Object.prototype.hasOwnProperty.call(I18N, key)) return I18N[key];
  for (const [re, fn] of I18N_PATTERNS) {
    const m = key.match(re);
    if (m) return fn(m);
  }
  return text;
}

function _skip(node) {
  const el = node.nodeType === 1 ? node : node.parentElement;
  return !el || el.closest("script, style, [translate='no']");
}

function _translateText(node) {
  if (_skip(node)) return;
  const before = node.nodeValue;
  const after = tr(before);
  if (after !== before) {
    // Keep the spaces around it, which separate it from neighbouring elements.
    const lead = before.match(/^\s*/)[0], trail = before.match(/\s*$/)[0];
    node.nodeValue = lead + after.trim() + trail;
  }
}

function _translateAttrs(el) {
  if (_skip(el)) return;
  for (const attr of ["placeholder", "aria-label", "title"]) {
    const value = el.getAttribute(attr);
    if (value && _ZH.test(value)) {
      const after = tr(value);
      if (after !== value) el.setAttribute(attr, after);
    }
  }
}

function translateTree(root) {
  if (LANG !== "en" || !root) return;
  if (root.nodeType === 3) return _translateText(root);
  if (root.nodeType !== 1) return;
  _translateAttrs(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === 3) _translateText(node);
    else _translateAttrs(node);
  }
}

let _observer = null;

function setLang(lang) {
  const was = LANG;
  LANG = lang === "en" ? "en" : "zh";
  document.documentElement.lang = LANG === "en" ? "en" : "zh-CN";
  if (LANG === "en") {
    translateTree(document.body);
    if (!_observer) {
      _observer = new MutationObserver((records) => {
        for (const r of records) {
          if (r.type === "characterData") _translateText(r.target);
          else if (r.type === "attributes") _translateAttrs(r.target);
          else r.addedNodes.forEach(translateTree);
        }
      });
      _observer.observe(document.body, { childList: true, subtree: true, characterData: true,
        attributes: true, attributeFilter: ["placeholder", "aria-label", "title"] });
    }
  } else {
    if (_observer) { _observer.disconnect(); _observer = null; }
    // Pages that were showing English redraw themselves in Chinese.
    if (was === "en" && typeof window.onLanguageBack === "function") window.onLanguageBack();
  }
}
