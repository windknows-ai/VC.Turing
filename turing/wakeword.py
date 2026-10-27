"""Always-on, fully local wake word detection ("嗨图灵", "Hey Turing", "图灵" ...).

Uses sherpa-onnx's bilingual keyword spotter, so any wake word works without
training: Chinese is spelled in pinyin, English in CMU phones, and the two can be
mixed in one wake word ("Hey 图灵").

A bare name ("图灵") is a word people also use mid-sentence ("我昨天看了关于图灵的
电影"), so it only counts when it begins an utterance: there must be a short pause
right before it.
"""

import collections
import re

import numpy as np
import sherpa_onnx
from pypinyin import pinyin
from pypinyin.contrib.tone_convert import to_finals_tone, to_initials

from . import models
from .audio import CHUNK, SAMPLE_RATE
from .paths import DATA_DIR

_CJK = re.compile(r"[一-鿿]")
_PARTS = re.compile(r"[一-鿿]+|[A-Za-z']+")
# Wake words that are just the name, with no greeting in front.
BARE_NAMES = {"图灵", "turing"}

# Sensitivity 1 (hard to wake) .. 5 (easy): keyword threshold and boost.
SENSITIVITY = {1: (0.35, 1.5), 2: (0.28, 1.8), 3: (0.2, 2.0), 4: (0.15, 2.5), 5: (0.1, 3.0)}


def _load_tokens(path) -> set[str]:
    with open(path, encoding="utf-8") as f:
        return {line.split()[0] for line in f if line.strip()}


def _load_lexicon(path) -> dict[str, list[str]]:
    lexicon = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            word, *phones = line.split()
            lexicon.setdefault(word.upper(), phones)
    return lexicon


# Common ways people actually say words the dictionary spells only one way.
EXTRA_PRONUNCIATIONS = {
    "TURING": [["T", "UW1", "R", "IH0", "NG"], ["T", "Y", "UH1", "R", "IH0", "NG"],
               ["T", "ER1", "IH0", "NG"]],
}


def _pinyin_tokens(text: str) -> list[str]:
    out = []
    for (syllable,) in pinyin(text):
        initial = to_initials(syllable, strict=False)
        final = to_finals_tone(syllable, strict=False)
        out += [p for p in (initial, final) if p]
    return out


def keyword_tokens(keyword: str, lexicon: dict[str, list[str]]) -> list[list[str]]:
    """Spell a keyword in the model's tokens: pinyin initials/finals for Chinese, CMU
    phones for English words, in order, so "Hey 图灵" works too.

    Returns one or more spellings (English words can have several pronunciations).
    """
    spellings = [[]]
    for part in _PARTS.findall(keyword):
        if _CJK.match(part):
            options = [_pinyin_tokens(part)]
        else:
            word = part.upper()
            if word not in lexicon:
                raise ValueError(f"Wake word '{part}' is not in the English dictionary")
            options = [lexicon[word]] + EXTRA_PRONUNCIATIONS.get(word, [])
        spellings = [s + o for s in spellings for o in options][:8]
    return spellings


def is_bare(keyword: str) -> bool:
    return keyword.replace(" ", "").lower() in BARE_NAMES


class WakeWord:
    def __init__(self, cfg: dict, keywords_file=None, model: str = "16"):
        model_dir = models.KWS.path
        tokens_file = model_dir / "tokens.txt"
        known = _load_tokens(tokens_file)
        lexicon = _load_lexicon(model_dir / "en.phone")

        def spell(words) -> list[str]:
            lines = []
            for kw in words:
                for toks in keyword_tokens(kw, lexicon):
                    missing = [t for t in toks if t not in known]
                    if missing:
                        raise ValueError(f"Wake word '{kw}' uses unknown sounds: {missing}")
                    lines.append(" ".join(toks) + " @" + kw.replace(" ", "_"))
            return lines

        level = int(cfg.get("sensitivity", 0) or 0)
        threshold, boost = SENSITIVITY.get(level, SENSITIVITY[4])
        prefix = f"epoch-13-avg-2-chunk-{model}-left-64"
        keywords_file = keywords_file or DATA_DIR / "keywords.txt"
        keywords_file.parent.mkdir(parents=True, exist_ok=True)

        def spotter(lines: list[str], path):
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return sherpa_onnx.KeywordSpotter(
                tokens=str(tokens_file),
                encoder=str(model_dir / f"encoder-{prefix}.int8.onnx"),
                decoder=str(model_dir / f"decoder-{prefix}.onnx"),
                joiner=str(model_dir / f"joiner-{prefix}.int8.onnx"),
                keywords_file=str(path),
                keywords_threshold=float(threshold),
                keywords_score=float(boost),
                num_threads=1,
            )

        # Two spotters: one for wake words with a greeting ("嗨图灵", "Hey Turing"), one
        # for the bare name. In a single spotter "嗨图灵" is sometimes reported as just
        # "图灵"; turning that down (no pause before it) would then lose the greeting too.
        greeted = [k for k in cfg["keywords"] if not is_bare(k)]
        bare = [k for k in cfg["keywords"] if is_bare(k)]
        self._spotters = []
        if greeted:
            self._spotters.append((spotter(spell(greeted), keywords_file), False))
        if bare:
            path = keywords_file.with_name(keywords_file.stem + "-bare.txt")
            self._spotters.append((spotter(spell(bare), path), True))
        self._streams = [kws.create_stream() for kws, _ in self._spotters]
        # Loudness of the last 3 s, in 100 ms steps, to check for a pause before "图灵".
        self._levels: collections.deque[float] = collections.deque(maxlen=30)

    def feed(self, samples: np.ndarray) -> str | None:
        """Feed audio; returns the wake word that was heard, if any."""
        for i in range(0, len(samples), CHUNK):
            part = samples[i:i + CHUNK]
            self._levels.append(float(np.sqrt(np.mean(np.square(part)))) if len(part) else 0.0)
        found = None
        for (kws, bare), stream in zip(self._spotters, self._streams):
            stream.accept_waveform(SAMPLE_RATE, samples)
            while kws.is_ready(stream):
                kws.decode_stream(stream)
                heard = kws.get_result(stream)
                if heard:
                    kws.reset_stream(stream)
                    if bare and not self._paused_before():
                        continue  # "...关于图灵的电影": the name mid-sentence
                    found = found or heard.replace("_", " ")
        return found

    def _paused_before(self) -> bool:
        """Was there a pause just before the name that was just heard?

        Detection comes about 0.3 s after the word ends and the word lasts ~0.6 s, so
        the stretch from 1.8 s to 1.0 s ago is just before it. It counts as a pause if
        it's much quieter than the word itself.
        """
        levels = list(self._levels)
        if len(levels) < 18:
            return True  # just started listening: nothing was said before
        word = max(levels[-10:])
        before = levels[-18:-10]
        return max(before) < max(0.006, 0.25 * word)

    def reset(self):
        self._streams = [kws.create_stream() for kws, _ in self._spotters]
        self._levels.clear()
