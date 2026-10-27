"""Make synthetic test recordings for checking the full pipeline without a mic.

    python scripts/make_test_wavs.py .scratch
    python -m turing --wav .scratch/zh.wav --quiet
"""

import asyncio
import sys
import wave
from pathlib import Path

import edge_tts
import miniaudio
import numpy as np

SR = 16000


async def tts(text: str, voice: str, rate: str = "+0%") -> np.ndarray:
    audio = bytearray()
    async for part in edge_tts.Communicate(text, voice, rate=rate).stream():
        if part["type"] == "audio":
            audio += part["data"]
    d = miniaudio.decode(bytes(audio), output_format=miniaudio.SampleFormat.SIGNED16,
                         nchannels=1, sample_rate=SR)
    return np.frombuffer(d.samples, dtype=np.int16)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.int16)


def write(path: Path, parts):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(np.concatenate(parts).tobytes())


async def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    zh, zh2, en = "zh-CN-XiaoxiaoNeural", "zh-CN-YunjianNeural", "en-US-JennyNeural"
    # Wake word, a pause (where the chime would be), then a command.
    write(out / "zh.wav", [silence(1), await tts("嗨，图灵。", zh), silence(0.8),
                           await tts("现在几点了？", zh), silence(1.5),
                           await tts("嘿，图灵。", zh2), silence(0.8),
                           await tts("今天星期几？", zh2), silence(1)])
    write(out / "en.wav", [silence(1), await tts("Hey Turing.", en), silence(0.8),
                           await tts("What time is it?", en), silence(1)])
    # Siri-style: the command in the same breath as the wake word (no reply expected) ...
    write(out / "breath_zh.wav", [silence(1), await tts("嗨图灵，现在几点了？", zh), silence(1.5)])
    write(out / "breath_en.wav", [silence(1), await tts("Hey Turing, what time is it?", en), silence(1.5)])
    # ... and a pause after the name, where Turing should answer "我在" before the command.
    write(out / "pause_zh.wav", [silence(1), await tts("嗨，图灵。", zh), silence(2.5),
                                 await tts("今天几号？", zh), silence(1.5)])
    # Ordinary talk that must NOT wake Turing.
    write(out / "none.wav", [silence(1), await tts("今天天气不错，我们下午去公园散步吧，顺便买点水果。", zh),
                             silence(0.5), await tts("I think the meeting is at three this afternoon.", en),
                             silence(1)])
    print(f"Wrote test recordings to {out}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".scratch")))
