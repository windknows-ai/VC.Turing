"""Microphone input and simple sound output."""

import queue
import threading
import time
import wave
from contextlib import contextmanager

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK = 1600  # 100 ms


class Microphone:
    """Streams 16 kHz mono float32 chunks from the mic into a queue.

    Survives the things that happen on a laptop: headphones plugged in or pulled out, a
    Bluetooth headset connecting, the default device changing, sleep and resume. Any of
    these can leave the stream silently dead or on the wrong device; `read()` notices
    and reopens it (on the same mic by name, or the new default).
    """

    MAX_QUEUED = 300      # 30 s; older audio is dropped rather than piling up
    STALL_SECONDS = 3.0   # no audio for this long while running: the device is gone
    CHECK_SECONDS = 3.0   # how often to look for a new default device

    def __init__(self, device=None, notify=None):
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=self.MAX_QUEUED)
        self._muted = threading.Event()
        self._notify = notify or (lambda message: None)
        self.level = 0.0  # loudness of the latest chunk, 0..1, for the app's meter
        self._name = sd.query_devices(device)["name"] if device is not None else None
        self._device = device
        self._stream = None
        self._running = False
        self._last_audio = time.monotonic()
        self._slept_at = _asleep_seconds()
        self._next_check = 0.0
        self._defaults = _default_endpoints()
        self.reopened = 0  # how many times it had to recover (for tests and logs)
        self._open()

    def _open(self):
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK,
            device=self._device,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        self._last_audio = time.monotonic()
        samples = indata[:, 0]
        self.level = min(1.0, float(np.sqrt(np.mean(samples ** 2))) * 12)
        if self._muted.is_set():
            return
        try:
            self._q.put_nowait(samples.copy())
        except queue.Full:  # nobody is reading: keep the newest audio
            try:
                self._q.get_nowait()
                self._q.put_nowait(samples.copy())
            except (queue.Empty, queue.Full):
                pass

    def start(self):
        self._stream.start()
        self._running = True
        self._last_audio = time.monotonic()

    def stop(self):
        self._running = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    def read(self, timeout: float = 0.5):
        """Next chunk, or None if nothing arrived within `timeout`."""
        self._watch()
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self):
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    @contextmanager
    def muted(self):
        """Ignore the mic while Turing itself is making sound."""
        self._muted.set()
        try:
            yield
        finally:
            self.flush()
            self._muted.clear()

    # --- staying alive ------------------------------------------------------------

    def _watch(self):
        if not self._running:
            return
        now, asleep = time.monotonic(), _asleep_seconds()
        slept, self._slept_at = asleep - self._slept_at > 5, asleep
        if slept:
            return self._recover("电脑刚从睡眠中醒来，重新打开麦克风。")
        if now - self._last_audio > self.STALL_SECONDS:
            return self._recover("麦克风没有声音了（可能被拔掉或切换了），正在重新连接…")
        if now >= self._next_check:
            self._next_check = now + self.CHECK_SECONDS
            defaults = _default_endpoints()
            if defaults != self._defaults and None not in defaults:
                self._defaults = defaults
                self._recover("检测到默认音频设备变了，换到新设备。")

    def _recover(self, why: str):
        """Reopen the stream on the right device. PortAudio only sees devices that existed
        when it started, so it is restarted first (that also moves Turing's voice to the
        new default speakers)."""
        if _output_active():
            return  # Turing is talking; restarting PortAudio would cut it off. Next time.
        self._notify(why)
        self.stop()
        self.flush()
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        self._device = _find_input(self._name)
        if self._name and self._device is None:
            self._notify(f"找不到“{self._name}”，先用系统默认麦克风。")
        self._defaults = _default_endpoints()
        try:
            self._open()
            self.start()
            self.reopened += 1
        except Exception as e:
            # No microphone at all right now: try again in a few seconds.
            self._running = True
            self._last_audio = time.monotonic()
            self._notify(f"暂时打不开麦克风：{e}")


def _asleep_seconds() -> float:
    """How long the PC has spent asleep or hibernating since it booted: wall-clock
    uptime minus the uptime that excludes sleep."""
    try:
        import ctypes

        unbiased = ctypes.c_ulonglong()
        ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(unbiased))
        return ctypes.windll.kernel32.GetTickCount64() / 1000 - unbiased.value / 1e7
    except Exception:
        return 0.0


def _find_input(name):
    if not name:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0:
            return i
    return None


def _output_active() -> bool:
    try:
        return sd.get_stream().active
    except Exception:
        return False


_com = threading.local()  # one device enumerator per thread (COM objects are per thread)


def _default_endpoints():
    """IDs of Windows' default microphone and speakers, (None, None) if unknown. ~2 ms."""
    try:
        if getattr(_com, "enumerator", None) is None:
            import comtypes
            from pycaw.pycaw import AudioUtilities

            comtypes.CoInitialize()
            _com.enumerator = AudioUtilities.GetDeviceEnumerator()
        e = _com.enumerator
        # eCapture = 1, eRender = 0; role eConsole = 0
        return (e.GetDefaultAudioEndpoint(1, 0).GetId(), e.GetDefaultAudioEndpoint(0, 0).GetId())
    except Exception:
        return (None, None)


class WavSource:
    """Feeds a 16 kHz mono wav file in 100 ms chunks, for testing without a mic."""

    def __init__(self, path: str):
        self._chunks = list(_chunks(load_wav(path)))
        # Trailing silence so the VAD can see the end of the last utterance.
        self._chunks += [np.zeros(CHUNK, dtype=np.float32)] * 20

    def start(self):
        pass

    def stop(self):
        pass

    def read(self, timeout: float = 0.5):
        # Real-time pace, so pauses in the recording last as long as they would live.
        time.sleep(CHUNK / SAMPLE_RATE)
        return self._chunks.pop(0) if self._chunks else None

    def flush(self):
        pass

    @contextmanager
    def muted(self):
        # Like the mic, ignore what was "heard" while Turing was talking.
        started = time.monotonic()
        yield
        skip = int((time.monotonic() - started) * SAMPLE_RATE / CHUNK)
        del self._chunks[:skip]

    @property
    def finished(self) -> bool:
        return not self._chunks


def _chunks(samples: np.ndarray):
    for i in range(0, len(samples), CHUNK):
        yield samples[i : i + CHUNK]


def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as f:
        if f.getframerate() != SAMPLE_RATE or f.getnchannels() != 1 or f.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16 kHz mono 16-bit wav")
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768


def chime(rising: bool = True) -> np.ndarray:
    """A short two-note chime; rising for 'I'm listening', falling for 'giving up'."""
    sr = 24000
    notes = (880, 1320) if rising else (1320, 880)
    parts = []
    for freq in notes:
        t = np.arange(int(sr * 0.07)) / sr
        env = np.minimum(1, t * 200) * np.exp(-t * 25)
        parts.append(0.25 * np.sin(2 * np.pi * freq * t) * env)
    return np.concatenate(parts).astype(np.float32)


def play(samples: np.ndarray, sample_rate: int = 24000):
    sd.play(samples, sample_rate)
    sd.wait()
