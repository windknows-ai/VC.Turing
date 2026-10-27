"""Measure how well each wake-word setting wakes, and how often it wakes by mistake.

    python scripts/wake_eval.py            # builds the recordings once (.scratch/wake), then evaluates

Positives (should wake): several voices, three speeds, near / far (quiet) / noisy, every
way of calling Turing. Negatives (should not): everyday chatter, including sentences that
mention 图灵 in the middle.
"""

import asyncio
import itertools
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from make_test_wavs import tts  # noqa: E402
from turing.audio import CHUNK, SAMPLE_RATE  # noqa: E402
from turing.wakeword import WakeWord  # noqa: E402

OUT = Path(".scratch/wake")
ZH_VOICES = ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural",
             "zh-CN-XiaoyiNeural", "zh-CN-YunyangNeural"]
EN_VOICES = ["en-US-GuyNeural", "en-US-JennyNeural", "en-US-AriaNeural", "en-US-ChristopherNeural"]
RATES = ["-15%", "+0%", "+25%"]
ZH_CALLS = ["嗨图灵", "嘿图灵", "图灵", "Hi，图灵", "Hey，图灵", "嗨图灵，现在几点了", "图灵，打开微信"]
EN_CALLS = ["Hey Turing", "Hi Turing", "Hey Turing, what time is it"]
CHATTER = [
    ("zh", "我昨天看了一部关于图灵的电影，讲得挺好的"),
    ("zh", "他说这个模型能通过图灵测试，我不太信"),
    ("zh", "这本书讲的是阿兰图灵的一生"),
    ("zh", "你知道今年的图灵奖颁给谁了吗"),
    ("zh", "我们下节课要讨论图灵机和计算理论"),
    ("zh", "今天天气不错，我们下午出去走走吧"),
    ("zh", "嘿，你今天中午吃饭了吗"),
    ("zh", "嗨大家好，欢迎来到今天的直播"),
    ("zh", "等一下我把这个文件发给你"),
    ("en", "Hey, how are you doing today?"),
    ("en", "Hi there, nice to meet you."),
    ("en", "Alan Turing was a brilliant mathematician."),
    ("en", "The Turing test is about whether a machine can seem human."),
    ("en", "During the meeting we talked about the budget."),
]

CURRENT = ["嗨图灵", "嘿图灵", "Hey Turing"]
NEW = ["嗨图灵", "嘿图灵", "图灵", "Hi 图灵", "Hey 图灵", "Hey Turing", "Hi Turing"]


def to_float(x: np.ndarray) -> np.ndarray:
    return x.astype(np.float32) / 32768


async def build():
    OUT.mkdir(parents=True, exist_ok=True)
    pos = []
    jobs = [(v, r, t) for v, r, t in itertools.product(ZH_VOICES, RATES, ZH_CALLS)]
    jobs += [(v, r, t) for v, r, t in itertools.product(EN_VOICES, RATES, EN_CALLS)]
    for i, (voice, rate, text) in enumerate(jobs):
        path = OUT / f"pos{i:03d}.npy"
        if not path.exists():
            np.save(path, await tts(text, voice, rate))
        pos.append({"file": path.name, "voice": voice, "rate": rate, "text": text})
    neg = []
    for i, ((lang, text), voice) in enumerate(itertools.product(CHATTER, ["a", "b"])):
        v = (ZH_VOICES if lang == "zh" else EN_VOICES)[0 if voice == "a" else 1]
        path = OUT / f"neg{i:03d}.npy"
        if not path.exists():
            np.save(path, await tts(text, v))
        neg.append({"file": path.name, "voice": v, "text": text})
    (OUT / "index.json").write_text(json.dumps({"pos": pos, "neg": neg}, ensure_ascii=False), encoding="utf-8")


def condition(audio: np.ndarray, kind: str, rng) -> np.ndarray:
    if kind == "far":         # a few metres away: much quieter
        return audio * 0.15
    if kind == "noisy":       # background noise about as loud as a busy room (SNR ~10 dB)
        speech = float(np.sqrt(np.mean(audio ** 2)))
        return audio + rng.standard_normal(len(audio)).astype(np.float32) * speech / 3.2
    return audio


def wakes(detector: WakeWord, audio: np.ndarray) -> int:
    detector.reset()
    hits = 0
    for i in range(0, len(audio), CHUNK):
        if detector.feed(audio[i:i + CHUNK]):
            hits += 1
    return hits


def evaluate(keywords, sensitivity, model="16"):
    rng = np.random.default_rng(0)
    index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    kw_file = Path(tempfile.gettempdir()) / f"turing-eval-{model}-{sensitivity}-{len(keywords)}.txt"
    det = WakeWord({"keywords": keywords, "sensitivity": sensitivity, "threshold": 0.2, "boost": 2.0},
                   keywords_file=kw_file, model=model)
    silence = np.zeros(int(0.8 * SAMPLE_RATE), dtype=np.float32)
    results = {}
    for kind in ("clean", "far", "noisy"):
        rows = []
        for item in index["pos"]:
            speech = condition(to_float(np.load(OUT / item["file"])), kind, rng)
            rows.append((item, wakes(det, np.concatenate([silence, speech, silence, silence])) > 0))
        results[kind] = rows
    # Negatives as one long stretch of chatter, like a room where people talk.
    gap = np.zeros(int(0.35 * SAMPLE_RATE), dtype=np.float32)
    chatter = np.concatenate([np.concatenate([to_float(np.load(OUT / n["file"])), gap]) for n in index["neg"]] * 3)
    false_wakes = wakes(det, chatter)
    return results, false_wakes, len(chatter) / SAMPLE_RATE / 60


def summary(name, results, false_wakes, minutes):
    line = f"{name:<34}"
    for kind, rows in results.items():
        line += f" {kind} {sum(h for _, h in rows) / len(rows):4.0%}"
    line += f" | false wakes {false_wakes} in {minutes:.1f} min of chatter"
    print(line, flush=True)


def by_call(results):
    """Hit rate per way of calling Turing (clean audio)."""
    stats = {}
    for item, hit in results["clean"]:
        s = stats.setdefault(item["text"], [0, 0])
        s[0] += hit
        s[1] += 1
    return {k: f"{h}/{n}" for k, (h, n) in stats.items()}


if __name__ == "__main__":
    asyncio.run(build())
    configs = [("current words, sens 3", CURRENT, 3, "16")]
    for sens in (3, 4, 5):
        configs.append((f"new words, sens {sens}", NEW, sens, "16"))
    configs.append(("new words, sens 4, model 8", NEW, 4, "8"))
    for name, words, sens, model in configs:
        results, fw, minutes = evaluate(words, sens, model)
        summary(name, results, fw, minutes)
        print("    ", by_call(results))
