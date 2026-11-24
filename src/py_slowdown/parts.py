"""La lectura en paralelo de un archivo largo, por partes.

Decodificar es lo que más tarda al abrir un archivo largo (hora y media de MP3,
unos siete segundos), y en un solo proceso no se puede repartir: PyAV hace una
llamada de Python por cada trozo de MP3, y los hilos se turnan el GIL. Así que
Audio lee él mismo el comienzo, como siempre (se puede tocar y dibujar enseguida),
y cada una de las demás partes la lee un proceso propio (Part): este programa
mismo con PyAV (python -m py_slowdown.parts) o el programa ffmpeg, que escriben
muestras de 16 bits, como su salida estándar, en un archivo temporal.

Cada parte empieza PREROLL segundos antes de su lugar, para que el decodificador
se asiente (el de MP3 tarda unos 50 ms, el de Opus medio segundo), y el último
segundo antes de ese lugar (CHECK) debe ser idéntico, muestra por muestra, a lo
que ya se leyó: así se sabe dónde va exactamente (align). Si no coincide, o si
un proceso falla, Audio sigue leyendo de corrido desde donde iba: el resultado
es siempre el de una lectura seguida, a lo sumo más lento.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from pathlib import Path

import numpy as np

MIN_SECONDS = 240.0  # archivos más cortos: se leen de corrido (los procesos tardan en arrancar)
MIN_PART = 60.0  # segundos de cada parte, por lo menos
MAX_PARTS = 4  # el comienzo y tres procesos: más casi no ganan (medido: 2.9 s con 4, 2.7 s con 8)
PREROLL = 3.0  # segundos que cada parte empieza antes de su lugar
CHECK = 1.0  # segundos que deben coincidir con lo ya leído
CHUNK = 1 << 20  # bytes que el proceso de una parte junta antes de escribirlos
HEADER = 8  # bytes del índice del primer cuadro, al comienzo de lo que escribe python -m py_slowdown.parts

# Los códecs cuyo decodificador, empezado en otro punto, da en menos de PREROLL segundos las mismas muestras que
# una lectura seguida (comprobado). No el AAC: su sustitución por ruido (PNS, que el codificador de FFmpeg usa
# por omisión) sale de un generador aleatorio que corre desde el comienzo del archivo, y una parte tendría otro
# ruido en esas bandas, inaudible pero distinto.
EXACT = frozenset({"mp3", "mp3float", "flac", "vorbis", "libvorbis", "opus", "libopus"})


def plan(seconds: float, rate: int) -> list[int]:
    """Where the parts begin, in frames (empty: read the file straight on).

    The first part, from 0, is the one Audio reads itself.
    """
    if os.environ.get("PY_SLOWDOWN_PARALLEL") == "0" or seconds < MIN_SECONDS:
        return []
    cpus = (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or 1
    count = min(MAX_PARTS, cpus, int(seconds // MIN_PART))
    if count < 2:
        return []
    total = seconds * rate
    return [round(total * k / count) for k in range(1, count)]


def interpreter() -> list[str]:
    """How to run this Python for a part: python.exe rather than pythonw.exe (which the shortcuts of Windows use,
    and which may have no standard output), with -s if this one has it (the same packages)."""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe" and (executable.parent / "python.exe").exists():
        executable = executable.parent / "python.exe"
    return [str(executable), *(["-s"] if sys.flags.no_user_site else [])]


def sweep(folder) -> None:
    """Remove the temporary files of parts left by a program that ended abruptly (only on Windows, where a
    file in use keeps its name; elsewhere they have none from the start)."""
    import time

    for path in Path(folder).glob("part-*"):
        try:
            if time.time() - path.stat().st_mtime > 3600:
                path.unlink()
        except OSError:
            pass  # (en uso por otra ventana del programa)


def find(window: np.ndarray, head: np.ndarray) -> list[int]:
    """Every place in HEAD where WINDOW is, sample for sample ([] if WINDOW is all one value: it would be anywhere)."""
    if not len(window) or np.all(window == window[0]):
        return []
    # El cuadro más fuerte de la ventana es el más raro: solo donde está se compara todo.
    q = int(np.abs(window.astype(np.int32)).sum(axis=1).argmax())
    starts = np.flatnonzero(np.all(head == window[q], axis=1)) - q
    size = len(window)
    return [int(c) for c in starts if c >= 0 and c + size <= len(head) and np.array_equal(head[c:c + size], window)]


def align(window: np.ndarray, at: int, head: np.ndarray, predicted: int | None) -> int | None:
    """The index, in the whole file, of the first frame of a part whose first frames are HEAD.

    WINDOW is what was read before, from frame AT: the part must have it, exactly. PREDICTED (from the
    timestamps, exact with PyAV) is tried first; else WINDOW is looked for, and must be in HEAD only once.
    None if the part does not agree.
    """
    size = len(window)
    if predicted is not None:
        i = at - predicted
        if 0 <= i and i + size <= len(head) and np.array_equal(head[i:i + size], window):
            return predicted
    places = find(window, head)
    if len(places) != 1:
        return None
    return at - places[0]


class Part:
    """A part of the file read by a process of its own (COMMAND), which writes it into a temporary file in FOLDER."""

    def __init__(self, command: list[str], channels: int, folder, header: bool, predicted: int | None):
        self.channels = channels
        self._header = header
        self._predicted = predicted
        self._killed = False
        # El proceso escribe en el archivo (es su salida estándar) y aquí se lee con otro descriptor, de modo que
        # leer no mueve el lugar donde él escribe; nadie más los copia (un hilo que vaciaba la tubería le quitaba
        # el GIL a la lectura del comienzo, y la hacía un 60 % más lenta).
        fd, self._path = tempfile.mkstemp(dir=folder, prefix="part-")
        with os.fdopen(fd, "wb") as out:
            self._in = open(self._path, "rb")  # noqa: SIM115 (lo cierra kill)
            if os.name != "nt":
                # (sin nombre desde ya: nada queda si el programa termina de golpe; en Windows, al cerrarlo)
                os.unlink(self._path)
                self._path = None
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL,
                                             creationflags=flags)

    def _size(self) -> int:
        return os.fstat(self._in.fileno()).st_size

    @property
    def predicted(self) -> int | None:
        """The index of the first frame in the whole file, from the timestamps (None: not known)."""
        if self._header and self._predicted is None and self._size() >= HEADER:
            self._in.seek(0)
            first = int.from_bytes(self._in.read(HEADER), "little", signed=True)
            self._predicted = first if first >= 0 else None
        return self._predicted

    @property
    def frames(self) -> int:
        """The frames already in the file."""
        offset = HEADER if self._header else 0
        return max(0, self._size() - offset) // (self.channels * 2)

    @property
    def finished(self) -> bool:
        return self._process.poll() is not None

    @property
    def failed(self) -> bool:
        return self.finished and self._process.returncode != 0 and not self._killed

    def read(self, start: int, stop: int) -> np.ndarray:
        """Frames START to STOP of the part (fewer if it has not got so far), 16-bit."""
        stop = min(stop, self.frames)
        if stop <= start:
            return np.zeros((0, self.channels), np.int16)
        size = self.channels * 2
        self._in.seek((HEADER if self._header else 0) + start * size)
        data = self._in.read((stop - start) * size)
        return np.frombuffer(data, "<i2")[:len(data) // size * self.channels].reshape(-1, self.channels)

    def wait(self, timeout: float) -> None:
        try:
            self._process.wait(timeout)
        except subprocess.TimeoutExpired:
            pass

    def kill(self) -> None:
        """Stop the process and free the temporary file."""
        self._killed = True
        if self._process.poll() is None:
            self._process.kill()
        try:
            self._process.wait(5)
        except subprocess.TimeoutExpired:
            pass
        self._in.close()
        if self._path:
            try:
                os.unlink(self._path)
            except OSError:
                pass


def main(argv: list[str]) -> int:
    """python -m py_slowdown.parts FILE START STOP RATE CHANNELS: decode FILE from START seconds to STOP (-1: the
    end), at RATE and CHANNELS, and write to the standard output the index of its first frame in the whole file
    (8 bytes, little-endian) and then its frames, 16-bit and interleaved."""
    import av

    path, start, stop, rate, channels = argv[0], float(argv[1]), float(argv[2]), int(argv[3]), int(argv[4])
    out = sys.stdout.buffer
    with av.open(path) as container:
        stream = container.streams.audio[0]
        stream.thread_type = "AUTO"
        # El cuadro 0 de una lectura seguida es el del comienzo del flujo (en un MP3, unos 25 ms después de cero).
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else 0.0
        if start > 0:
            container.seek(int((start + origin) / stream.time_base), stream=stream)
        resampler = av.AudioResampler(format="s16", layout="mono" if channels == 1 else "stereo", rate=rate)
        last = round(stop * rate) if stop >= 0 else None
        first = None
        pending: list[bytes] = []
        size = 0
        for frame in container.decode(stream):
            if first is None:
                if frame.time is None:
                    continue  # (sin tiempo no se sabe dónde va: se espera el siguiente)
                first = round((frame.time - origin) * rate)
                out.write(first.to_bytes(HEADER, "little", signed=True))
            for piece in resampler.resample(frame):
                data = piece.to_ndarray().tobytes()
                pending.append(data)
                size += len(data)
            if size >= CHUNK:
                out.write(b"".join(pending))
                pending, size = [], 0
            if last is not None and first is not None and frame.time is not None and \
                    round((frame.time - origin) * rate) >= last:
                break
        if first is None:
            out.write((-1).to_bytes(HEADER, "little", signed=True))
        for piece in resampler.resample(None):
            pending.append(piece.to_ndarray().tobytes())
        out.write(b"".join(pending))
        out.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        # (el programa cerró el archivo, o terminó: lo que falta ya no hace falta)
        sys.exit(1)
