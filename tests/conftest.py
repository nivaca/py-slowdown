"""Lo común de las pruebas: archivos de audio de muestra, una tarjeta de sonido falsa
y carpetas propias (configuración, caché, datos) para no tocar las del usuario."""

from __future__ import annotations

import os
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


CODECS = {".wav": "pcm_s16le", ".flac": "flac", ".mp3": "libmp3lame", ".m4a": "aac", ".opus": "libopus"}


def write(path, samples: np.ndarray, rate: int = RATE) -> None:
    """Write SAMPLES (frames × channels) to PATH, with the codec its extension asks for.

    With PyAV if it is installed; else (as in the RPM's %check, Fedora has no PyAV)
    a WAV made by Python, converted by the ffmpeg program.
    """
    codec = CODECS[os.path.splitext(str(path))[1]]
    try:
        import av
    except ImportError:
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
