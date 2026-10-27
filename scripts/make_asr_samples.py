"""Synthetic sentences for comparing speech recognizers, with the expected text.

    python scripts/make_asr_samples.py .scratch/asr
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_test_wavs import silence, tts, write  # noqa: E402

SAMPLES = [
    # (voice, text) — Chinese, English, and the two mixed in one sentence.
    ("zh-CN-YunxiNeural", "帮我打开 Discord 然后去 general 频道发一句 hello"),
    ("zh-CN-XiaoxiaoNeural", "用 Chrome 搜一下 iPhone 18 Pro 的价格"),
    ("zh-CN-YunxiNeural", "给土豆发微信说今晚 seven 点一起吃饭"),
    ("zh-CN-XiaoxiaoNeural", "把 PPT 的第三页翻译成 English"),
    ("en-US-GuyNeural", "Open Discord, go to the badminton server and send hello in general"),
    ("en-US-JennyNeural", "What's the weather like in Oakville tomorrow"),
    ("zh-CN-YunxiNeural", "发送"),
    ("zh-CN-XiaoxiaoNeural", "取消"),
]


async def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    expected = {}
    for i, (voice, text) in enumerate(SAMPLES):
        name = f"s{i}.wav"
        write(out / name, [silence(0.3), await tts(text, voice), silence(0.3)])
        expected[name] = text
    (out / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(SAMPLES)} samples to {out}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".scratch/asr")))
