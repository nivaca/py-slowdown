"""Lo común de las pruebas: archivos de audio de muestra, una tarjeta de sonido falsa
y carpetas propias (configuración, caché, datos) para no tocar las del usuario."""

from __future__ import annotations

import os
import shutil
import subprocess
import wave

import numpy as np
import pytest

# Las ventanas de las pruebas se dibujan fuera de la pantalla, aunque el escritorio pida Wayland o X11.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

RATE = 44100


def tone(seconds: float, rate: int = RATE, channels: int = 2) -> np.ndarray:
    """A quiet tone with a click at every whole second (frames × channels, float32)."""
    t = np.arange(int(seconds * rate)) / rate
    x = (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for k in range(1, int(seconds)):
        x[k * rate:k * rate + 40] += 0.9
    return np.repeat(x[:, None], channels, axis=1)


CODECS = {".wav": "pcm_s16le", ".flac": "flac", ".mp3": "libmp3lame", ".m4a": "aac", ".opus": "libopus",
          ".ogg": "libvorbis"}


def can_write(suffix: str) -> bool:
    """Whether a file of SUFFIX can be made here: with PyAV, or with the ffmpeg program (Homebrew's, on macOS,
    has no Vorbis encoder)."""
    codec = CODECS[suffix]
    try:
        import av

        av.codec.Codec(codec, "w")
        return True
    except Exception:  # noqa: BLE001 (sin PyAV, o sin ese códec)
        pass
    if not shutil.which("ffmpeg"):
        return False
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return f" {codec} " in encoders


def write(path, samples: np.ndarray, rate: int = RATE) -> None:
    """Write SAMPLES (frames × channels) to PATH, with the codec its extension asks for.

    With PyAV if it is installed and has the codec; else (as in the RPM's %check,
    Fedora has no PyAV, or for Vorbis, which PyAV's wheels lack) a WAV made by
    Python, converted by the ffmpeg program.
    """
    codec = CODECS[os.path.splitext(str(path))[1]]
    try:
        import av

        av.codec.Codec(codec, "w")
    except ImportError:
        av = None
    except Exception:  # noqa: BLE001 (un códec que el PyAV de la rueda no trae, como libvorbis)
        av = None
    if av is None:
        wav = str(path) + ".tmp.wav"
        with wave.open(wav, "wb") as out:
            out.setnchannels(samples.shape[1])
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes((np.clip(samples, -1, 1) * 32767).round().astype("<i2").tobytes())
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", wav, "-c:a", codec, str(path)], check=True)
        os.unlink(wav)
        return
    layout = "mono" if samples.shape[1] == 1 else "stereo"
    with av.open(str(path), "w") as container:
        stream = container.add_stream(codec, rate=rate, layout=layout)
        fmt = stream.codec_context.format.name if stream.codec_context.format else "fltp"
        size = stream.codec_context.frame_size or 1024
        resampler = av.AudioResampler(format=fmt, layout=layout, rate=rate)
        for start in range(0, len(samples), size):
            chunk = np.ascontiguousarray(samples[start:start + size].reshape(1, -1), np.float32)
            frame = av.AudioFrame.from_ndarray(chunk, format="flt", layout=layout)
            frame.rate = rate
            frame.pts = start
            for out in resampler.resample(frame):
                for packet in stream.encode(out):
                    container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def decoders():
    """The decoders there are here: PyAV if installed, the ffmpeg program if installed."""
    found = []
    try:
        import av  # noqa: F401
        found.append("av")
    except ImportError:
        pass
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        found.append("ffmpeg")
    return found


@pytest.fixture(params=decoders())
def decoder(request, monkeypatch):
    monkeypatch.setenv("PY_SLOWDOWN_DECODER", request.param)
    return request.param


@pytest.fixture(autouse=True)
def own_folders(tmp_path, monkeypatch):
    for name in ("XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setenv(name, str(folder))


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "clicks.wav"
    write(path, tone(6.0))
    return path


class FakeOutput:
    """A sound card the tests drive: pull() asks for frames as PortAudio would."""

    latency = 0.0

    def __init__(self):
        self.callback = None

    def open(self, rate, channels, callback):
        self.rate, self.channels, self.callback = rate, channels, callback

    def close(self):
        self.callback = None

    def pull(self, frames: int = 512) -> np.ndarray:
        out = np.zeros((frames, self.channels), np.float32)
        self.callback(out)
        return out

    @staticmethod
    def supports(rate):
        return True

    @staticmethod
    def default_rate():
        return 48000


@pytest.fixture
def output():
    return FakeOutput()


@pytest.fixture(autouse=True)
def no_errors_in_slots(monkeypatch):
    """An error in a Qt slot (a button, a timer, a signal) is only printed by PySide, and the test would go on:
    every test fails if one happened."""
    import sys

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *info: errors.append(info))
    yield
    if errors:
        import traceback

        pytest.fail("an error in a Qt slot:\n" + "".join(traceback.format_exception(*errors[0])))


@pytest.fixture(autouse=True)
def save_when_asked(monkeypatch):
    """Ask to save before closing a file is on at first: in the tests the answer is Save (a dialog would wait
    for a click); the tests of the question itself answer otherwise."""
    monkeypatch.setattr("py_slowdown.window.Window._ask_save", lambda self, name: "save", raising=False)
