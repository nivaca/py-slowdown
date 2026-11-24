"""El audio de un archivo, decodificado.

Audio abre un archivo (MP3, MP4, M4A, FLAC, WAV, Ogg, Opus... lo que FFmpeg lea,
mediante PyAV o, donde PyAV no está, con el programa ffmpeg) y lo decodifica en un hilo aparte, a muestras float32 entrelazadas
(cuadros × canales; uno o dos canales: los demás se mezclan en estéreo). Las
muestras van, en 16 bits, a un archivo temporal sin nombre, mapeado en memoria:
una grabación de dos horas en estéreo ocupa unos 1,3 GB (el doble en float32), y así el
sistema guarda en la memoria solo lo que se lee; frames() las devuelve en float32. Mientras decodifica, Audio calcula los picos de la
forma de onda (Peaks) y cuenta los cuadros listos (decoded), de modo que la
ventana (que pregunta cada tanto) puede dibujar y tocar lo que ya está, sin
esperar el final.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

# Frames per peak: the waveform keeps the minimum and the maximum of each group of BUCKET frames.
BUCKET = 256

# Las muestras se guardan en enteros de 16 bits: x * SCALE. Las de un archivo de 16 bits quedan exactas (FFmpeg
# las da como s / 32768), y las demás pierden lo que está debajo de unos -96 dB, menos que el ruido de una
# grabación; lo que pase de 1.0 (algunos MP3 decodificados) se recorta, como lo recortaría la tarjeta de sonido.
SCALE = 32768.0

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
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        path = Path(os.environ["LOCALAPPDATA"]) / "py-slowdown" / "cache"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Caches" / "py-slowdown"
    else:
        path = Path(os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")) / "py-slowdown"
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


def decoder() -> str:
    """"av" (PyAV) or "ffmpeg" (the ffmpeg program): what reads the files here.

    PyAV is preferred; the ffmpeg program serves where PyAV is not installed
    (Fedora has no package of PyAV, so the RPM uses ffmpeg-free).
    $PY_SLOWDOWN_DECODER chooses one.
    """
    wanted = os.environ.get("PY_SLOWDOWN_DECODER", "")
    if wanted in ("av", "ffmpeg"):
        return wanted
    try:
        import av  # noqa: F401
    except ImportError:
        return "ffmpeg"
    return "av"


class _PyAV:
    """A file read by PyAV."""

    def __init__(self, path: Path):
        import av

        self._av = av
        try:
            self._container = av.open(str(path))
        except (av.FFmpegError, OSError) as error:
            raise AudioError(str(error)) from error
        if not self._container.streams.audio:
            self._container.close()
            raise AudioError("no audio")
        stream = self._stream = self._container.streams.audio[0]
        self.channels = stream.channels or 2
        self.rate = int(stream.rate or stream.sample_rate or 44100)
        self.codec = stream.codec_context.name if stream.codec_context else ""
        if stream.duration and stream.time_base:
            self.seconds = float(stream.duration * stream.time_base)
        elif self._container.duration:
            self.seconds = self._container.duration / av.time_base
        else:
            self.seconds = None

    def samples(self, rate: int, channels: int, stop: threading.Event):
        """The samples, converted to RATE and CHANNELS, as arrays of frames × channels."""
        av = self._av
        resampler = av.AudioResampler(format="flt", layout="mono" if channels == 1 else "stereo", rate=rate)
        try:
            for frame in self._container.decode(self._stream):
                if stop.is_set():
                    return
                for out in resampler.resample(frame):
                    yield out.to_ndarray().reshape(-1, channels)
            for out in resampler.resample(None):
                yield out.to_ndarray().reshape(-1, channels)
        except av.FFmpegError as error:
            raise AudioError(str(error)) from error
        finally:
            self._container.close()


class _FFmpeg:
    """A file read by the ffmpeg program (and described by ffprobe)."""

    CHUNK = 8192  # cuadros por lectura

    def __init__(self, path: Path):
        self.path = path
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise AudioError(f"{tool} is not installed (nor PyAV)")
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                 "stream=codec_name,sample_rate,channels,duration:format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=60, check=False)
            info = json.loads(probe.stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise AudioError(str(error)) from error
        streams = info.get("streams") or []
        if probe.returncode != 0 or not streams:
            raise AudioError(probe.stderr.strip() or "no audio")
        stream = streams[0]
        self.channels = int(stream.get("channels") or 2)
        self.rate = int(stream.get("sample_rate") or 44100)
        self.codec = stream.get("codec_name", "")
        seconds = stream.get("duration") or (info.get("format") or {}).get("duration")
        try:
            self.seconds = float(seconds) if seconds not in (None, "N/A") else None
        except ValueError:
            self.seconds = None

    def samples(self, rate: int, channels: int, stop: threading.Event):
        # Lo que ffmpeg escribe: float32 entrelazado, ya en la frecuencia y los canales pedidos.
        command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.path), "-map", "0:a:0",
                   "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(rate), "pipe:1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        size = self.CHUNK * channels * 4
        rest = b""
        try:
            while not stop.is_set():
                data = process.stdout.read(size)
                if not data:
                    break
                data = rest + data
                whole = len(data) // (channels * 4) * channels * 4
                rest = data[whole:]
                if whole:
                    yield np.frombuffer(data[:whole], np.float32).reshape(-1, channels)
        finally:
            if stop.is_set():
                process.kill()
            process.stdout.close()
            error = process.stderr.read().decode(errors="replace").strip()
            process.stderr.close()
            status = process.wait()
        if status != 0 and not stop.is_set():
            raise AudioError(error.splitlines()[-1] if error else f"ffmpeg ended with {status}")


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
        self._source = _PyAV(self.path) if decoder() == "av" else _FFmpeg(self.path)
        self.channels = 1 if self._source.channels == 1 else 2
        self.rate = int(rate or self._source.rate)
        self.codec = self._source.codec

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
        return self._source.seconds

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
        """The decoded frames from START to STOP (fewer at the end), a new float32 array."""
        start = max(0, start)
        stop = min(stop, self.decoded)
        data = self._data  # (puede ser reemplazado por otro más grande mientras se lee)
        out = data[start:max(start, stop)].astype(np.float32)
        out *= 1.0 / SCALE  # (una potencia de dos: exacto)
        return out

    # --- decodificación

    def _map(self, frames: int) -> np.ndarray:
        size = frames * self.channels * 2
        self._file.truncate(size)
        return np.memmap(self._file, dtype=np.int16, mode="r+", shape=(frames, self.channels))

    def _grow(self, needed: int) -> None:
        # Un archivo más largo de lo anunciado: el archivo temporal crece y se mapea de nuevo; lo escrito queda.
        self._data.flush()
        self._data = self._map(max(needed, int(self._data.shape[0] * 1.5)))

    def _decode(self) -> None:
        try:
            for samples in self._source.samples(self.rate, self.channels, self._stop):
                self._take(samples)
        except AudioError as error:
            # A file damaged halfway: what was read until then stays.
            self.error = str(error)
        self.peaks.finish()
        self.done = True

    def _take(self, samples: np.ndarray) -> None:
        if not samples.size:
            return
        end = self.decoded + samples.shape[0]
        if end > self._data.shape[0]:
            self._grow(end)
        scaled = np.rint(samples * SCALE)
        np.clip(scaled, -SCALE, SCALE - 1, out=scaled)
        self._data[self.decoded:end] = scaled
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
