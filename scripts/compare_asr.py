"""Compare the speech recognizers on accuracy and speed.

    python scripts/make_asr_samples.py .scratch/asr
    python scripts/compare_asr.py .scratch/asr
"""

import difflib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from turing.audio import load_wav  # noqa: E402
from turing.stt import RECOGNIZERS, make_recognizer  # noqa: E402


def norm(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?'\"“”]", "", text.lower())


def score(heard: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, norm(heard), norm(expected)).ratio()


def main(folder: Path):
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    samples = {name: load_wav(str(folder / name)) for name in expected}
    for name in RECOGNIZERS:
        try:
            rec = make_recognizer(name, threads=4)
        except FileNotFoundError:
            print(f"{name}: not installed")
            continue
        rec(samples[next(iter(samples))])  # warm up
        total_audio = total_time = total_score = 0.0
        print(f"\n== {name}")
        for wav, text in expected.items():
            audio = samples[wav]
            t = time.perf_counter()
            heard = rec(audio)
            took = time.perf_counter() - t
            s = score(heard, text)
            total_audio += len(audio) / 16000
            total_time += took
            total_score += s
            print(f"  {s:4.0%} {took:5.2f}s  {heard}")
        n = len(expected)
        print(f"  -> accuracy {total_score / n:.0%}, {total_time / n:.2f}s per sentence, "
              f"{total_time / total_audio:.2f}x real time")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ".scratch/asr"))
