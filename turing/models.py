"""Download the speech models Turing needs on first run.

All models come from the sherpa-onnx GitHub releases. Users who can't reach GitHub
can set `model_mirror` in config.toml to a prefix such as "https://ghfast.top/".
"""

import posixpath
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .paths import MODELS_DIR

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"


@dataclass(frozen=True)
class Model:
    key: str
    tag: str
    asset: str
    # Directory name after extraction (archives) or file name (single files).
    target: str

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.target

    @property
    def url(self) -> str:
        return f"{RELEASES}/{self.tag}/{self.asset}"


KWS = Model(
    "kws",
    "kws-models",
    "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2",
    "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20",
)
ASR = Model(
    "asr",
    "asr-models",
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2",
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09",
)
VAD = Model("vad", "asr-models", "silero_vad.onnx", "silero_vad.onnx")
# Optional, more accurate recognizer: much better with Chinese and English mixed in one
# sentence, with accents, and it takes hotwords. Bigger and slower than SenseVoice.
QWEN3_ASR = Model(
    "qwen3-asr",
    "asr-models",
    "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25.tar.bz2",
    "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
)

ALL = [KWS, ASR, VAD]


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                sys.stdout.write(f"\r  {dest.name}: {done >> 20}/{total >> 20} MB ({pct}%)")
                sys.stdout.flush()
    sys.stdout.write("\n")
    # shutil.move, not Path.replace: redirected AppData folders can make a same-folder
    # rename look like a cross-drive move on some Windows setups.
    shutil.move(tmp, dest)


def _remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length") or 0)


def _extract(archive: Path, dest: Path):
    """Unpack after checking every entry stays inside `dest`.

    Python's built-in "data" filter can't be used: it compares fully resolved paths, and
    when AppData is redirected to another drive those differ in drive letter and every
    entry is refused ("Paths don't have the same drive").
    """
    with tarfile.open(archive, "r:bz2") as tar:
        members = tar.getmembers()
        for member in members:
            name = posixpath.normpath(member.name)
            if (name.startswith(("/", "..")) or ":" in name or "/../" in f"/{name}/"
                    or not (member.isfile() or member.isdir())):
                raise RuntimeError(f"unsafe entry in {archive.name}: {member.name}")
        tar.extractall(dest, members=members, filter="fully_trusted")


def installed(m: Model) -> bool:
    if m.asset.endswith(".tar.bz2"):
        return (m.path / ".complete").exists()
    return m.path.exists()


def ensure(models=ALL, mirror: str = "") -> None:
    """Download and unpack any model that isn't fully on disk yet."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for m in models:
        if installed(m):
            continue
        url = mirror + m.url if mirror else m.url
        if m.asset.endswith(".tar.bz2"):
            archive = MODELS_DIR / m.asset
            if m.path.exists() and any(m.path.iterdir()) and not archive.exists():
                # Unpacked before the completion marker existed (the archive is deleted
                # only after a successful unpack, so its absence means it finished).
                (m.path / ".complete").touch()
                continue
            if not (archive.exists() and archive.stat().st_size == _remote_size(url)):
                print(f"Downloading {m.key} model / 正在下载{m.key}模型 ...")
                _download(url, archive)
            shutil.rmtree(m.path, ignore_errors=True)  # half-unpacked leftovers
            _extract(archive, MODELS_DIR)
            if not m.path.exists():
                raise RuntimeError(f"{m.asset} did not unpack to {m.path}")
            (m.path / ".complete").touch()
            archive.unlink()
        else:
            _download(url, m.path)


def remove_all() -> None:
    shutil.rmtree(MODELS_DIR, ignore_errors=True)


if __name__ == "__main__":
    # python -m turing.models             the models Turing needs
    # python -m turing.models qwen3-asr   also the optional accurate recognizer (~840 MB)
    import sys

    extra = {m.key: m for m in (QWEN3_ASR,)}
    ensure(ALL + [extra[k] for k in sys.argv[1:] if k in extra])
    print(f"Models ready in {MODELS_DIR}")
