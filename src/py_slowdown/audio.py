"""El audio de un archivo, decodificado.

Audio abre un archivo (MP3, MP4, M4A, FLAC, WAV, Ogg, Opus... lo que FFmpeg lea,
mediante PyAV) y lo decodifica en un hilo aparte, a muestras float32 entrelazadas
(cuadros × canales; uno o dos canales: los demás se mezclan en estéreo). Las
muestras van a un archivo temporal sin nombre, mapeado en memoria: una grabación
de dos horas ocupa más de un gigabyte en float32, y así el sistema guarda en la
memoria solo lo que se lee. Mientras decodifica, Audio calcula los picos de la
forma de onda (Peaks) y cuenta los cuadros listos (decoded), de modo que la
ventana (que pregunta cada tanto) puede dibujar y tocar lo que ya está, sin
esperar el final.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import av
import numpy as np

# Frames per peak: the waveform keeps the minimum and the maximum of each group of BUCKET frames.
BUCKET = 256

# Extensiones que el diálogo Abrir ofrece; FFmpeg lee muchas más, y cualquier archivo se puede intentar.
EXTENSIONS = (
    "mp3", "m4a", "m4b", "mp4", "aac", "flac", "wav", "wave", "aif", "aiff", "ogg", "oga",
    "opus", "wma", "wv", "ape", "mka", "mkv", "webm", "mov", "ac3", "amr", "3gp",
)


class AudioError(Exception):
    """A file that cannot be read as audio."""


def cache_dir() -> Path:
    """Where the decoded samples are kept while a file is open.

    Not /tmp: on many systems (Fedora among them) it lives in memory, which
    is what the mapped file is meant to spare.
    """
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    path = Path(base) / "py-slowdown"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Peaks:
    """Minimum and maximum of each BUCKET frames, over all the channels."""

    def __init__(self, capacity: int):
        self.lo = np.zeros(max(capacity, 1), np.float32)
        self.hi = np.zeros(max(capacity, 1), np.float32)
        self.count = 0  # picos completos
        self._rest = np.zeros((0, 1), np.float32)  # cuadros que aún no llenan un grupo

    def add(self, frames: np.ndarray) -> None:
        """Take FRAMES (n × channels), in order, after the ones added before."""
        if self._rest.shape[1] != frames.shape[1]:
            self._rest = np.zeros((0, frames.shape[1]), np.float32)
        if self._rest.shape[0]:
            frames = np.concatenate([self._rest, frames])
        whole = frames.shape[0] // BUCKET
        if whole:
            groups = frames[: whole * BUCKET].reshape(whole, BUCKET * frames.shape[1])
            self._store(groups.min(axis=1), groups.max(axis=1))
        self._rest = frames[whole * BUCKET :].copy()

    def finish(self) -> None:
        """Close the last, incomplete group."""
        if self._rest.shape[0]:
            self._store(np.array([self._rest.min()]), np.array([self._rest.max()]))
            self._rest = self._rest[:0]

    def _store(self, lo: np.ndarray, hi: np.ndarray) -> None:
        end = self.count + lo.size
        if end > self.lo.size:
            # Longer than the announced duration: grow, with room to spare.
            size = max(end, self.lo.size * 2)
            self.lo = np.resize(self.lo, size)
            self.hi = np.resize(self.hi, size)
        self.lo[self.count : end] = lo
        self.hi[self.count : end] = hi
        self.count = end


class Audio:
    """The decoded audio of a file.

    rate, channels and duration (an estimate until done) are known once the
    object exists; frames() gives the samples decoded so far.
    """

    def __init__(self, path: str | os.PathLike, rate: int | None = None):
        """Open PATH and start decoding it, at RATE (the file's own rate if None).

        Raises AudioError if the file has no audio that FFmpeg can read.
        """
        self.path = Path(path)
        try:
            self._container = av.open(str(self.path))
        except (av.FFmpegError, OSError) as error:
            raise AudioError(str(error)) from error
        if not self._container.streams.audio:
            self._container.close()
            raise AudioError("no audio")
        stream = self._container.streams.audio[0]
        self._stream = stream
        self.channels = 1 if (stream.channels or 2) == 1 else 2
        self.rate = int(rate or stream.rate or stream.sample_rate or 44100)
        self.codec = stream.codec_context.name if stream.codec_context else ""

        seconds = self._announced_seconds()
        self.estimated = seconds is not None
        capacity = int((seconds if seconds else 600.0) * self.rate * 1.02) + self.rate
        self._file = tempfile.TemporaryFile(dir=cache_dir(), prefix="decoded-")  # noqa: SIM115 (open while the audio is)
        self._data = self._map(capacity)
        self.peaks = Peaks(capacity // BUCKET + 2)

        self.decoded = 0  # frames ready to be read
        self.done = False
        self.error = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._decode, name="decode", daemon=True)
        self._thread.start()

    # --- lo que se sabe del archivo

    def _announced_seconds(self) -> float | None:
        stream = self._stream
        if stream.duration and stream.time_base:
            return float(stream.duration * stream.time_base)
        if self._container.duration:
            return self._container.duration / av.time_base
        return None

    @property
    def duration(self) -> float:
        """Seconds: the real length once decoded, the announced one before."""
        if self.done or not self.estimated:
            return self.decoded / self.rate
        return max(self.decoded, self._data.shape[0] / 1.02 - self.rate) / self.rate

    @property
    def length(self) -> int:
        """Frames: decoded so far, or announced (for drawing and seeking)."""
        return round(self.duration * self.rate)

    def frames(self, start: int, stop: int) -> np.ndarray:
        """The decoded frames from START to STOP (fewer at the end), a view."""
        start = max(0, start)
        stop = min(stop, self.decoded)
        data = self._data  # (puede ser reemplazado por otro más grande mientras se lee)
        return data[start:max(start, stop)]

    # --- decodificación

    def _map(self, frames: int) -> np.ndarray:
        size = frames * self.channels * 4
        self._file.truncate(size)
        return np.memmap(self._file, dtype=np.float32, mode="r+", shape=(frames, self.channels))

    def _grow(self, needed: int) -> None:
        # Un archivo más largo de lo anunciado: el archivo temporal crece y se mapea de nuevo; lo escrito queda.
        self._data.flush()
        self._data = self._map(max(needed, int(self._data.shape[0] * 1.5)))

    def _decode(self) -> None:
        layout = "mono" if self.channels == 1 else "stereo"
        resampler = av.AudioResampler(format="flt", layout=layout, rate=self.rate)
        try:
            for frame in self._container.decode(self._stream):
                if self._stop.is_set():
                    return
                for out in resampler.resample(frame):
                    self._take(out)
            for out in resampler.resample(None):
                self._take(out)
        except av.FFmpegError as error:
            # A file damaged halfway: what was read until then stays.
            self.error = str(error)
        finally:
            self._container.close()
        self.peaks.finish()
        self.done = True

    def _take(self, frame) -> None:
        samples = frame.to_ndarray().reshape(-1, self.channels)
        if not samples.size:
            return
        end = self.decoded + samples.shape[0]
        if end > self._data.shape[0]:
            self._grow(end)
        self._data[self.decoded:end] = samples
        self.peaks.add(samples)
        self.decoded = end

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until the whole file is decoded; True if it is."""
        self._thread.join(timeout)
        return self.done

    def close(self) -> None:
        """Stop decoding and free the temporary file."""
        self._stop.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(5)
        self._file.close()
