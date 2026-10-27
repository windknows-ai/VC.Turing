"""Dry-run everyday commands through the real Turing (local skills + the configured AI)
with every action on the PC intercepted, and check what it did against what it said.

    python scripts/scenario_eval.py                 # all scenarios
    python scripts/scenario_eval.py 桌面 desktop     # only those containing a word

Nothing happens on the screen: launching programs, opening links, key presses, typing,
media keys, volume, locking, sending WeChat messages and screenshots are all recorded
instead (the AI is shown a placeholder picture, never the real screen). Conversation
memory and the log file are kept out of it. Writes .scratch/scenarios/report.json.
"""

import io
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from turing import app, config, keyboard, memory  # noqa: E402
from turing.skills import messaging, volume  # noqa: E402

OUT = Path(".scratch/scenarios")

SCENARIOS = [
    # apps and windows
    "打开记事本", "打开微信", "关闭记事本", "打开计算器", "打开设置", "打开下载文件夹",
    "打开QQ音乐", "打开Steam", "打开Discord", "切换到微信", "把Chrome最小化", "最大化当前窗口",
    "关闭当前窗口", "把这个窗口放到屏幕左边", "显示桌面", "打开任务管理器",
    # virtual desktops
    "帮我切换到学习那个桌面", "切换到AI那个桌面", "切到下一个桌面", "新建一个桌面", "我现在在哪个桌面",
    # browser and sites
    "打开谷歌浏览器用student账号", "打开YouTube", "在浏览器里新建一个标签页", "关掉这个标签页",
    "刷新一下页面", "打开百度", "搜索今天的新闻", "帮我问一下ChatGPT怎么学Python", "打开Gmail",
    "打开B站看一下影视飓风最新的视频", "打开抖音搜索张大仙", "在YouTube上搜lofi music",
    # music and media
    "用网易云音乐放一首周杰伦的晴天", "用QQ音乐放稻香", "暂停", "下一首", "现在放的是什么歌",
    "音量调到30", "大声点", "静音",
    # system
    "锁屏", "把屏幕调亮一点", "打开蓝牙", "关闭WiFi", "打开深色模式", "打开勿扰模式", "截个图",
    "关机", "重启电脑", "让电脑睡眠", "清空回收站", "电池还剩多少",
    # files
    "打开我的文档", "在桌面新建一个文件夹", "找一下桌面上的合同文件", "打开最近下载的文件",
    # messages and typing
    "给土豆发微信说晚上吃什么", "给妈妈打个微信视频电话", "用QQ给张三发消息说明天见",
    "在记事本里写一句你好世界", "把剪贴板里的内容读给我听",
    # time and reminders
    "10分钟后提醒我喝水", "定一个明天早上7点的闹钟", "现在几点", "今天星期几",
    # questions
    "明天天气怎么样", "奥克维尔周末会下雨吗", "123乘以45等于多少", "把hello world翻译成中文",
    "一美元等于多少人民币", "今天有什么新闻", "屏幕上这个报错是什么意思",
    # English
    "open notepad", "what's the weather tomorrow", "switch to the next desktop",
    "send a WeChat to Tudou saying see you soon", "play some music", "turn the volume down",
    "minimize all windows", "take a screenshot",
    # --- round two: the rest of a day at the computer ---
    # editing in whatever app is in front
    "保存一下", "撤销", "全选", "复制", "粘贴", "帮我把这个文件另存为", "按一下回车", "放大一点", "缩小一点",
    "恢复默认大小", "往下翻一页", "滚到最上面", "回到上一个窗口", "切换窗口", "全屏", "退出全屏",
    # notes and to-dos
    "帮我记一下明天要交化学作业", "我记了什么", "把笔记读给我听", "加一个待办：买牛奶", "我的待办有哪些",
    "清空笔记",
    # timers and reminders
    "计时器还剩多久", "有哪些提醒", "取消所有提醒", "5分钟后提醒我关火", "设一个25分钟的番茄钟",
    # time and dates
    "北京现在几点", "伦敦现在几点", "离圣诞节还有几天", "下周五是几号", "现在是几月几号",
    # the computer itself
    "电脑内存用了多少", "CPU占用多少", "C盘还剩多少空间", "现在有网吗", "我的IP地址是多少",
    "电脑开机多久了", "什么程序最占内存", "打开省电模式", "打开截图工具",
    # money and markets
    "苹果股票现在多少钱", "特斯拉股价", "比特币现在多少钱", "100欧元等于多少加元",
    # maps, places, travel
    "附近有什么好吃的", "去多伦多怎么走", "打开谷歌地图", "离我最近的超市在哪",
    # email and messages
    "给老师发邮件说我明天请假", "写一封邮件给zhangsan@example.com", "打开邮箱",
    # music and video, actually playing
    "播放周杰伦的晴天", "在YouTube上放一首lofi", "B站播放影视飓风最新的视频", "放点轻音乐",
    "暂停视频", "视频全屏",
    # weather details
    "明天要不要带伞", "现在外面多少度", "这周天气怎么样", "今天空气质量怎么样", "几点日落",
    # knowledge and language
    "鲁迅是谁", "光速是多少", "一公里等于多少英里", "100华氏度是多少摄氏度", "帮我把剪贴板里的内容翻译成英文",
    "讲个笑话", "给我讲个睡前故事",
    # Turing itself
    "你能做什么", "说慢一点", "说快一点", "换成女声", "声音大一点", "以后叫我小明", "我叫什么名字",
    "暂停聆听", "打开图灵的设置", "用英文回答我", "你是用什么AI",
    # English
    "save this", "undo that", "zoom in", "scroll down", "take a note: call mom tonight",
    "what time is it in Tokyo", "how much memory is the PC using", "play some jazz on YouTube",
    "what's Apple's stock price", "how do I get to Toronto",
]

# What an honest reply sounds like when it claims something was done.
CLAIM = re.compile(r"已(经)?(帮你|为你)?(打开|切换|关闭|发送|发|搜索|创建|新建|设置|调|最小化|最大化|"
                   r"锁|播放|暂停|写|输入|截|清空|移|放|完成)|好的|搞定|done|opened|switched|sent|"
                   r"closed|created|set |turned|minimi[sz]ed|maximi[sz]ed|took", re.I)

actions: list[str] = []


def record(kind):
    def fake(*args, **kwargs):
        shown = ", ".join([repr(a)[:80] for a in args] + [f"{k}={v!r}"[:60] for k, v in kwargs.items()])
        actions.append(f"{kind}({shown})")
        return True
    return fake


_REAL_POPEN = None
_READ_ONLY = re.compile(r"ollama(?:\.exe)?\"? serve|Get-StartApps|Get-ItemProperty|Get-CimInstance|--version|auth status|tasklist", re.I)


class FakePopen:
    """Records programs Turing starts; read-only queries (listing apps…) really run."""

    def __new__(cls, args, *a, **kw):
        line = " ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args)
        if _READ_ONLY.search(line):
            return _REAL_POPEN(args, *a, **kw)
        return super().__new__(cls)

    def __init__(self, args, *a, **kw):
        line = " ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args)
        actions.append(f"run({line})"[:160])
        self.pid, self.returncode, self.args = 0, 0, args
        self.stdout = self.stderr = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, *a, **kw):
        return ("", "")

    def wait(self, *a, **kw):
        return 0

    def poll(self):
        return 0

    def kill(self):
        pass


def placeholder_screenshot():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 200), "white")
    ImageDraw.Draw(img).text((20, 80), "TEST MODE - this is not the user's screen.", fill="black")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue(), "Test placeholder"


def intercept():
    import ctypes
    import os
    import subprocess
    import webbrowser

    from turing import screen
    from turing.skills import media

    global _REAL_POPEN
    os.startfile = record("startfile")
    _REAL_POPEN = subprocess.Popen
    subprocess.Popen = FakePopen
    webbrowser.open = record("browser")
    for name in ("press", "type_text", "close", "focus"):
        setattr(keyboard, name, record(f"keys.{name}"))
    keyboard.window_of_exe = lambda *a, **k: None
    keyboard.windows_of_exe = lambda *a, **k: []
    keyboard.windows_titled = lambda *a, **k: []
    media._press = record("media_key")

    async def fake_run(action):
        actions.append(f"media.{action}")
        return True, ("晴天", "周杰伦")
    media._run = fake_run
    volume.set_volume = record("set_volume")
    volume.get_volume = lambda: 30
    messaging.send_wechat = record("send_wechat")
    ctypes.windll.user32.LockWorkStation = record("lock")
    screen.capture = placeholder_screenshot
    # keep the user's conversation memory and log out of it
    app._write_log = lambda line: None
    tmp = OUT / "memory.json"
    app.Memory = lambda: memory.Memory(tmp)
    # abilities that act on the PC and then check the result: pretend they worked
    from turing.skills import desktops, device, files, windows

    def ok(kind, value=True):
        def fake(*args, **kwargs):
            record(kind)(*args, **kwargs)
            return value
        return fake

    desktops.switch_to = ok("switch_desktop")
    desktops._press = record("desktop_keys")
    desktops.Desktops.new = lambda self, ctx: (record("new_desktop")(), ctx.reply("已新建桌面", "New desktop made"))[1]
    for action in list(windows._ACTIONS):
        windows._ACTIONS[action] = ok(f"window.{action}")
    windows.show_desktop = ok("show_desktop")
    windows.close = ok("window.close")
    from turing.skills import apps
    apps.Apps._wait_for_window = lambda self, app, ctx, seconds=10: (
        f"{app.name} is open and in front (test); typing goes there now.")
    windows.bring_back_all = ok("restore_all")
    windows.tab = lambda action: (record(f"tab.{action}")(), (True, "Chrome"))[1]
    device.set_brightness = lambda p: (record("set_brightness")(p), max(0, min(100, p)))[1]
    device.set_dark_mode = ok("set_dark_mode")
    device.screenshot = ok("screenshot", r"C:\Pictures\Screenshots\test.png")
    for name in ("sleep_pc", "shutdown", "cancel_shutdown", "empty_recycle_bin", "open_settings"):
        setattr(device, name, ok(name))
    files.new_folder = ok("new_folder", r"C:\Desktop\新建文件夹")
    files.show_in_explorer = record("show_in_explorer")

    class FakeEndpoint:
        def __getattr__(self, name):
            return record(f"volume.{name}") if name.startswith("Set") else (lambda *a: 0)
    volume._endpoint = lambda: FakeEndpoint()
    keyboard._get_clipboard = lambda: "（测试用的剪贴板内容）"  # never read the user's real clipboard
    # nothing the commands change may stick: settings, notes and the user's profile
    from turing.skills import notes
    config.save_section = record("save_settings")
    notes.FILE, notes.PROFILE = OUT / "notes.json", OUT / "profile.json"
    for f in (notes.FILE, notes.PROFILE):
        f.unlink(missing_ok=True)
    volume.set_volume = lambda p: (record("set_volume")(p), p)[1]


def run(text: str, assistant) -> dict:
    actions.clear()
    assistant.ctx.state.clear()  # nothing carries over from the previous command
    if assistant.brain:
        assistant.brain.reset()
        assistant.memory.clear()
    result = {}
    worker = threading.Thread(target=lambda: result.update(reply=assistant.handle(text)), daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(120)
    reply = result.get("reply", "(timed out)")
    did = list(actions)
    real = [a for a in did if not a.startswith(("keys.type_text", "keys.press"))]
    flags = []
    if CLAIM.search(reply or "") and not real:
        flags.append("CLAIM-WITHOUT-ACTION" if not did else "CLAIM-ON-BLIND-KEYS")
    return {"command": text, "reply": reply, "actions": did, "flags": flags,
            "seconds": round(time.monotonic() - started, 1)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    local_only = "--local" in sys.argv  # built-in rules only, no AI
    words = [w for w in sys.argv[1:] if not w.startswith("--")]
    todo = [s for s in SCENARIOS if not words or any(w.lower() in s.lower() for w in words)]
    if "--new" in sys.argv:  # only the round-two list
        todo = [s for s in todo if SCENARIOS.index(s) >= SCENARIOS.index("保存一下")]
    intercept()
    cfg = config.load()
    assistant = app.Assistant(cfg, speak=False)
    if local_only:
        assistant.brain = None
    results = []
    for text in todo:
        r = run(text, assistant)
        results.append(r)
        mark = " ".join(r["flags"]) or "ok?"
        print(f"[{mark}] {text}\n    did: {r['actions'] or '-'}\n    said: {r['reply']}", flush=True)
    (OUT / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    flagged = [r for r in results if r["flags"]]
    print(f"\n{len(results)} commands, {len(flagged)} flagged automatically")


if __name__ == "__main__":
    main()
