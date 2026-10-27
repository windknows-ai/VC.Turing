"""Long-run stress test: many wakes and commands through the real listening pipeline
(wake word, VAD, speech recognition, local commands), no microphone or speakers needed.
Samples memory, threads, handles and CPU every few seconds so leaks show up as growth.

    python scripts/stress.py 100            # about 100 wakes (~15 min)
    python scripts/stress.py 100 --loops 8  # the same recording 8 times over

Writes .scratch/stress/samples.csv and prints a summary. Uses only local commands and
turns the AI off, so it costs nothing and needs no network after the voices are made.
"""

import asyncio
import csv
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_test_wavs import SR, silence, tts, write  # noqa: E402

from turing import app, config  # noqa: E402
from turing.audio import WavSource  # noqa: E402

OUT = Path(".scratch/stress")

# (text, voice, should wake)
LINES = [
    ("嗨图灵，现在几点了", "zh-CN-XiaoxiaoNeural", True),
    ("Hey Turing, what time is it", "en-US-GuyNeural", True),
    ("图灵，现在音量多少", "zh-CN-YunxiNeural", True),
    ("Hi 图灵，现在几点", "zh-CN-YunxiNeural", True),
    ("我昨天看了一本图灵的传记，写得挺好", "zh-CN-XiaoxiaoNeural", False),
    ("嘿图灵，今天几号", "zh-CN-XiaoyiNeural", True),
    ("这个问题可以问问图灵测试的历史", "zh-CN-YunxiNeural", False),
]


def make_recording(wakes: int) -> tuple[Path, int, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (text, voice, _) in enumerate(LINES):
        cache = OUT / f"line{i}.npy"
        if not cache.exists():
            np.save(cache, asyncio.run(tts(text, voice)))
        clips.append(np.load(cache))
    parts, expected, decoys = [silence(1.5)], 0, 0
    while expected < wakes:
        for clip, (_, _, wakes_it) in zip(clips, LINES):
            parts += [clip, silence(3.0)]
            expected += wakes_it
            decoys += not wakes_it
    path = OUT / "stress.wav"
    write(path, parts)
    return path, expected, decoys


def main():
    wakes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    loops = int(sys.argv[sys.argv.index("--loops") + 1]) if "--loops" in sys.argv else 1
    path, expected, decoys = make_recording(wakes)

    cfg = config.load()
    cfg["ai"]["provider"] = "none"
    cfg["listen"]["follow_up_seconds"] = 0  # each line is its own wake
    cfg["listen"]["keep_recordings"] = False  # don't overwrite the user's recordings
    cfg["listen"]["barge_in"] = False

    counts = {"wake": 0, "you": 0, "turing": 0, "error": 0}
    heard = []

    def on_event(kind, text):
        if kind in counts:
            counts[kind] += 1
        if kind == "you":
            heard.append(text)

    app.LISTENERS.append(on_event)
    proc = psutil.Process()
    proc.cpu_percent()
    rows = []
    started = time.monotonic()
    done = threading.Event()

    def sample():
        while not done.wait(5):
            mem = proc.memory_info()
            rows.append({
                "seconds": round(time.monotonic() - started),
                "rss_mb": round(mem.rss / 2**20, 1),
                "private_mb": round(getattr(mem, "private", mem.vms) / 2**20, 1),
                "threads": proc.num_threads(),
                "py_threads": threading.active_count(),
                "handles": proc.num_handles(),
                "cpu_pct": proc.cpu_percent(),
                "wakes": counts["wake"],
            })

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    for loop in range(loops):
        source = WavSource(str(path))
        assistant = app.Assistant(cfg, source=source, speak=False)
        assistant.run()
        print(f"loop {loop + 1}/{loops}: wakes {counts['wake']}, commands {counts['you']}", flush=True)
    done.set()
    sampler.join()

    with open(OUT / "samples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    settle = rows[min(len(rows) - 1, 6)]  # after models have loaded
    last = rows[-1]
    peak = max(r["rss_mb"] for r in rows)
    print(f"\nran {last['seconds']} s; expected wakes {expected * loops}, decoys {decoys * loops}")
    print(f"wakes {counts['wake']}  commands {counts['you']}  replies {counts['turing']}  "
          f"errors {counts['error']}")
    print(f"RSS  after load {settle['rss_mb']} MB -> end {last['rss_mb']} MB (peak {peak})")
    print(f"threads {settle['threads']} -> {last['threads']}   handles {settle['handles']} -> {last['handles']}")
    print(f"mean CPU {np.mean([r['cpu_pct'] for r in rows[6:]] or [0]):.1f}% of one core")
    wrong = [h for h in heard if not any(k in h for k in ("几点", "time", "音量", "几号"))]
    print(f"odd transcripts ({len(wrong)}):", wrong[:10])


if __name__ == "__main__":
    main()
