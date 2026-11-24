"""El audio de un archivo, decodificado.

Audio abre un archivo (MP3, MP4, M4A, FLAC, WAV, Ogg, Opus... lo que FFmpeg lea,
mediante PyAV o, donde PyAV no está, con el programa ffmpeg) y lo decodifica en un hilo aparte, a muestras de 16 bits entrelazadas
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

from . import parts as parallel

# Frames per peak: the waveform keeps the minimum and the maximum of each group of BUCKET frames.
BUCKET = 256

# Las muestras se guardan en enteros de 16 bits: x * SCALE. Las de un archivo de 16 bits quedan exactas (FFmpeg
# las da como s / 32768), y las demás pierden lo que está debajo de unos -96 dB, menos que el ruido de una
# grabación; lo que pase de 1.0 (algunos MP3 decodificados) se recorta, como lo recortaría la tarjeta de sonido.
SCALE = 32768.0

# Cuadros que los lectores juntan antes de entregarlos: el MP3 llega en trozos de 1152 cuadros o menos, y guardar
# cada uno por separado (el archivo temporal, los picos) costaba más que decodificarlo.
BATCH = 32768

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
        if self._rest.shape[1] != frames.shape[1] or self._rest.dtype != frames.dtype:
            self._rest = np.zeros((0, frames.shape[1]), frames.dtype)
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
        if lo.dtype == np.int16:
            # Muestras de 16 bits: el mínimo y el máximo se buscan en los enteros, y solo ellos se convierten.
            lo, hi = lo * np.float32(1 / SCALE), hi * np.float32(1 / SCALE)
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
        """The samples, converted to RATE and CHANNELS, as 16-bit arrays of frames × channels."""
        av = self._av
        # FFmpeg mismo convierte a 16 bits (redondea y recorta como Audio lo haría), y en varios hilos si el
        # códec lo permite (el FLAC se lee así en un tercio del tiempo).
        self._stream.thread_type = "AUTO"
        resampler = av.AudioResampler(format="s16", layout="mono" if channels == 1 else "stereo", rate=rate)
        pending: list[np.ndarray] = []
        size = 0
        try:
            for frame in self._container.decode(self._stream):
                if stop.is_set():
                    return
                for out in resampler.resample(frame):
                    pending.append(out.to_ndarray().reshape(-1, channels))
                    size += pending[-1].shape[0]
                if size >= BATCH:
                    yield np.concatenate(pending)
                    pending, size = [], 0
            for out in resampler.resample(None):
                pending.append(out.to_ndarray().reshape(-1, channels))
            if pending:
                yield np.concatenate(pending)
        except av.FFmpegError as error:
            raise AudioError(str(error)) from error
        finally:
            self._container.close()


    @staticmethod
    def part(path: Path, start: float, stop: float, rate: int, channels: int) -> tuple[list[str], bool, int | None]:
        """How a process reads the file from START seconds to STOP (-1: the end): (command, header, first frame)."""
        command = [*parallel.interpreter(), "-m", "py_slowdown.parts", str(path), repr(start), repr(stop), str(rate),
                   str(channels)]
        return command, True, None


class _FFmpeg:
    """A file read by the ffmpeg program (and described by ffprobe)."""

    CHUNK = BATCH  # cuadros por lectura

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
        # Lo que ffmpeg escribe: enteros de 16 bits entrelazados, ya en la frecuencia y los canales pedidos.
        command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.path), "-map", "0:a:0",
                   "-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(channels), "-ar", str(rate), "pipe:1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        size = self.CHUNK * channels * 2
        rest = b""
        try:
            while not stop.is_set():
                data = process.stdout.read(size)
                if not data:
                    break
                data = rest + data
                whole = len(data) // (channels * 2) * channels * 2
                rest = data[whole:]
                if whole:
                    yield np.frombuffer(data[:whole], "<i2").reshape(-1, channels)
        finally:
            if stop.is_set():
                process.kill()
            process.stdout.close()
            error = process.stderr.read().decode(errors="replace").strip()
            process.stderr.close()
            status = process.wait()
        if status != 0 and not stop.is_set():
            raise AudioError(error.splitlines()[-1] if error else f"ffmpeg ended with {status}")

    @staticmethod
    def part(path: Path, start: float, stop: float, rate: int, channels: int) -> tuple[list[str], bool, int | None]:
        # Sin cabecera: el primer cuadro se calcula de START, y align lo busca si no está ahí (en un MP3, el
        # comienzo del flujo lo corre unos 1100 cuadros).
        command = ["ffmpeg", "-nostdin", "-v", "error", "-ss", repr(start), "-i", str(path), "-map", "0:a:0"]
        if stop >= 0:
            command += ["-t", repr(stop - start)]
        command += ["-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(channels), "-ar", str(rate), "pipe:1"]
        return command, False, round(start * rate)


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
        self._seconds = seconds or 0.0
        capacity = int((seconds if seconds else 600.0) * self.rate * 1.02) + self.rate
        self._file = tempfile.TemporaryFile(dir=cache_dir(), prefix="decoded-")  # noqa: SIM115 (open while the audio is)
        self._data = self._map(capacity)
        self.peaks = Peaks(capacity // BUCKET + 2)

        self.decoded = 0  # frames ready to be read
        self.parts_used = 0  # partes leídas en paralelo que se añadieron (0: todo de corrido)
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
        starts = parallel.plan(self._seconds, self.rate) if self._parallel() else []
        running: list[parallel.Part] = []
        self._straight = self._source.samples(self.rate, self.channels, self._stop)
        self._straight_at = 0  # índice del primer cuadro de lo que la lectura seguida da después
        self._carry: np.ndarray | None = None  # lo que dio de más la última vez
        try:
            # Las demás partes, cada una en su proceso, empiezan a la vez que el comienzo, que se lee aquí.
            if starts and os.name == "nt":
                parallel.sweep(cache_dir())
            running = [self._start_part(at, starts[k + 1] if k + 1 < len(starts) else None)
                       for k, at in enumerate(starts)]
            reached = self._read_straight(starts[0] if starts else None)
            for k, part in enumerate(running):
                if not reached or self._stop.is_set():
                    break
                end = starts[k + 1] if k + 1 < len(starts) else None
                if not self._splice(part, end):
                    # No coincidió (o el proceso falló): de corrido desde donde se iba, como sin partes.
                    self.parts_used = k
                    self._read_straight(None)
                    break
            else:
                self.parts_used = len(running)
        except AudioError as error:
            # A file damaged halfway: what was read until then stays.
            self.error = str(error)
        finally:
            for part in running:
                part.kill()
            self._straight.close()
        self.peaks.finish()
        self.done = True

    def _parallel(self) -> bool:
        # Por partes solo a la frecuencia del archivo (el remuestreador tiene memoria y sus costuras no serían las
        # de una lectura seguida) y con los códecs que se asientan exactos después de un salto.
        return self.estimated and self.rate == self._source.rate and self.codec in parallel.EXACT

    def _start_part(self, at: int, end: int | None) -> parallel.Part:
        begin = max(0.0, at / self.rate - parallel.CHECK - parallel.PREROLL)
        stop = end / self.rate + 0.5 if end is not None else -1.0
        command, header, predicted = self._source.part(self.path, begin, stop, self.rate, self.channels)
        return parallel.Part(command, self.channels, cache_dir(), header, predicted)

    def _read_straight(self, until: int | None) -> bool:
        """Decode straight on up to frame UNTIL (None: the end), keeping only what comes after self.decoded.

        True if it got to UNTIL (False: the file ended, or reading stopped).
        """
        while until is None or self.decoded < until:
            if self._stop.is_set():
                return False
            if self._carry is not None:
                piece, self._carry = self._carry, None
            else:
                piece = next(self._straight, None)
                if piece is None:
                    return False
            at = self._straight_at
            self._straight_at += len(piece)
            # Lo que ya está (de una parte, antes de volver a leer de corrido) no se vuelve a guardar.
            low = min(max(0, self.decoded - at), len(piece))
            high = len(piece) if until is None else min(len(piece), max(low, until - at))
            if high < len(piece):
                self._carry = piece[high:]
                self._straight_at = at + high
            self._take(piece[low:high])
        return True

    def _splice(self, part: parallel.Part, end: int | None) -> bool:
        """Add PART after what is read, up to frame END (None: to its end), once its first frames agree.

        False if they do not, or if the part could not be read to END.
        """
        rate = self.rate
        at = self.decoded - round(parallel.CHECK * rate)
        window = self._data[at:self.decoded].copy()
        # Su comienzo: lo que se adelantó, el segundo que se compara y algo de holgura.
        size = round((parallel.PREROLL + parallel.CHECK + 5.0) * rate)
        while part.frames < size and not part.finished:
            if self._stop.is_set():
                return False
            part.wait(0.02)
        if part.failed:
            return False
        first = parallel.align(window, at, part.read(0, size), part.predicted)
        if first is None:
            return False
        step = 1 << 17
        while True:
            if self._stop.is_set():
                return False
            finished = part.finished  # (antes de contar: lo que escribió hasta terminar ya está contado)
            position = self.decoded - first
            available = part.frames
            stop = available if end is None else min(available, end - first)
            if position < stop:
                self._take(part.read(position, min(stop, position + step)))
                continue
            if end is not None and self.decoded >= end:
                return True
            if finished:
                # Toda la parte está: hasta el final del archivo, si no falló; si no llegó a END, falta algo.
                return end is None and not part.failed
            part.wait(0.02)

    def _take(self, samples: np.ndarray) -> None:
        if not samples.size:
            return
        end = self.decoded + samples.shape[0]
        if end > self._data.shape[0]:
            self._grow(end)
        if samples.dtype != np.int16:
            # (muestras en coma flotante: los lectores dan enteros, pero un float se acepta igual)
            scaled = np.rint(samples * SCALE)
            np.clip(scaled, -SCALE, SCALE - 1, out=scaled)
            samples = scaled.astype(np.int16)
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
