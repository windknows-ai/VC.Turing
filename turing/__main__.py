"""Command line entry point: `python -m turing`."""

import argparse
import sys

from . import __version__, config, models
from .paths import CONFIG_FILE, MODELS_DIR


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if stream:  # None under pythonw
            stream.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(prog="turing", description="Turing desktop voice assistant / 图灵桌面语音助手")
    p.add_argument("--text", action="store_true", help="type commands instead of speaking / 打字测试指令")
    p.add_argument("--wav", metavar="FILE", help="run on a 16 kHz mono wav instead of the mic / 用音频文件测试")
    p.add_argument("--quiet", action="store_true", help="don't speak replies / 不朗读回复")
    p.add_argument("--devices", action="store_true", help="list microphones / 列出麦克风")
    p.add_argument("--apps", action="store_true", help="list apps Turing can open / 列出能打开的软件")
    p.add_argument("--setup", action="store_true", help="choose the AI provider / 设置 AI 服务")
    p.add_argument("--version", action="version", version=f"Turing {__version__}")
    args = p.parse_args(argv)

    cfg = config.load()

    if args.devices:
        import sounddevice as sd

        print(sd.query_devices())
        return
    if args.apps:
        from .skills.apps import list_start_apps

        for app in sorted(list_start_apps(), key=lambda a: a.name.lower()):
            print(app.name)
        return

    if args.setup:
        from . import control_center

        control_center.run("ai")
        return
    if not cfg["ai"]["provider"] and not args.wav:
        print("还没有选择 AI。打开图灵 APP（双击桌面上的“图灵”）可以连接 AI。")

    from .app import Assistant

    if args.text:
        bot = Assistant(cfg, speak=not args.quiet)
        print("输入指令，回车执行，空行退出 / Type a command, empty line to quit")
        try:
            while line := input("> ").strip():
                bot.say(bot.handle(line))
        except EOFError:  # end of piped input, or Ctrl+Z
            print()
        return

    models.ensure(mirror=cfg["models"]["mirror"])
    print(f"配置文件 / Config: {CONFIG_FILE}")
    print(f"模型目录 / Models: {MODELS_DIR}")

    from . import audio

    if args.wav:
        source = audio.WavSource(args.wav)
    else:
        device = cfg["listen"]["device"]
        source = audio.Microphone(int(device) if str(device).strip() else None)
    try:
        Assistant(cfg, source=source, speak=not args.quiet).run()
    except KeyboardInterrupt:
        print("\n再见 / Bye")


if __name__ == "__main__":
    main()
