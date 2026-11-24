"""Guardar en un archivo la grabación como se oye: a otra velocidad, a otra altura.

render() la hace bloque a bloque con un Renderer propio (el mismo motor que
suena, con su propio estirador de Rubber Band, de modo que la reproducción
sigue mientras tanto), del archivo entero o de la selección, y si se pide le
aplica la manera de oír (hearing.py), sin el retraso de sus filtros. Un archivo
entero a 1× y a su altura sale tal cual, muestra por muestra; una selección
entra y sale en una rampa corta, sin chasquido.

Writer la escribe: WAV de 16 bits con el módulo wave de Python, y FLAC, MP3 u
Opus con PyAV o, donde no está (el RPM), con el programa ffmpeg, que recibe las
muestras por una tubería.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import Audio, decoder
from .engine import FADE, Renderer
from .hearing import Hearing, delay

# Formato: (extensión, códec de FFmpeg, bits por segundo o None, frecuencias que acepta o None)
FORMATS = {
    "wav": (".wav", "pcm_s16le", None, None),
    "flac": (".flac", "flac", None, None),
    "mp3": (".mp3", "libmp3lame", 192_000, (48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000)),
    "opus": (".opus", "libopus", 160_000, (48000,)),
}


class ExportError(OSError):
    """The file could not be written."""


@dataclass
class Settings:
    """What is exported, and how it sounds."""

    start: float = 0.0  # segundos
    end: float | None = None  # segundos (None: hasta el final)
    speed: float = 1.0
    pitch: float = 0.0
    formants: bool = False
    hearing: tuple[str, str] = ("both", "none")  # ("both", "none"): sin cambiar cómo se oye


def available() -> list[str]:
    """The formats that can be written here: WAV always; the others with PyAV or the ffmpeg program."""
    if decoder() == "av" or shutil.which("ffmpeg"):
        return list(FORMATS)
    return ["wav"]


def render(audio: Audio, settings: Settings, cancel: threading.Event | None = None,
           progress: Callable[[float], None] | None = None) -> Iterator[np.ndarray]:
    """The output, block after block (frames × channels, float32), from SETTINGS.start to SETTINGS.end.

    It waits for the decoder where the file is not read yet. PROGRESS is told the share done (0 to 1).
    """
    rate = audio.rate
    start = max(0, round(settings.start * rate))
    whole = settings.end is None
    renderer = Renderer(audio)
    renderer.set_speed(settings.speed)
    renderer.set_pitch(settings.pitch)
    renderer.set_formants(settings.formants)
    # (desde el principio no hay corte: sin la rampa de entrada, el archivo tal cual)
    renderer.seek(start, fade=start > 0)
    hearing = Hearing(rate, *settings.hearing)
    lag = delay(hearing.filter, rate)  # cuadros que el filtro atrasa: los primeros se dejan, y al final se vacía
    fade_out = not whole
    held: np.ndarray | None = None  # el último bloque, que espera por si hay que apagarlo (una selección)
    while True:
        if cancel is not None and cancel.is_set():
            return
        # (el archivo entero: hasta su final, una vez leído; lo que Rubber Band da después es su cola, de más)
        end = (audio.decoded if audio.done else None) if whole else round(settings.end * rate)
        block, _seam = renderer.render()
        if block is None:
            break
        if not len(block.frames):
            time.sleep(0.02)  # (el archivo todavía se lee)
            continue
        frames = block.frames
        if end is not None:
            # Solo los cuadros cuyo lugar en el archivo está antes del final.
            keep = int(np.ceil((end - block.start) / block.step)) if block.step else len(frames)
            frames = frames[:max(0, min(len(frames), keep))]
        if progress is not None:
            last = end if end is not None else (audio.length or 1)
            progress(min(1.0, (block.start - start) / max(1, last - start)))
        frames = hearing.process(frames) if not hearing.plain else frames
        if lag:
            drop = min(lag, len(frames))
            frames, lag = frames[drop:], lag - drop
        if held is not None and len(held):
            yield held
        held = frames
        if end is not None and block.start + len(block.frames) * block.step >= end:
            break
    if not hearing.plain and delay(hearing.filter, rate):
        # Lo que el filtro tiene todavía: su retraso, empujado con silencio.
        tail = hearing.process(np.zeros((delay(hearing.filter, rate), audio.channels), np.float32))
        held = tail if held is None else np.concatenate([held, tail])
    if held is not None and len(held):
        if fade_out:
            ramp = min(FADE, len(held))
            held = held.copy()
            held[len(held) - ramp:] *= np.linspace(1.0, 0.0, ramp, dtype=np.float32)[:, None]
        yield held
    if progress is not None:
        progress(1.0)


class Writer:
    """Writes float32 frames into PATH, in FORMAT (see FORMATS)."""

    def __init__(self, path: str | os.PathLike, format_: str, rate: int, channels: int):
        self.path = Path(path)
        self.format = format_
        self.rate = rate
        self.channels = channels
        _suffix, codec, bit_rate, rates = FORMATS[format_]
        self._out_rate = rate if rates is None or rate in rates else rates[0]
        self._wave = self._container = self._process = None
        try:
            if format_ == "wav":
                self._wave = wave.open(str(self.path), "wb")
                self._wave.setnchannels(channels)
                self._wave.setsampwidth(2)
                self._wave.setframerate(rate)
            elif decoder() == "av":
                self._open_av(codec, bit_rate)
            else:
                self._open_ffmpeg(codec, bit_rate)
        except Exception as error:  # noqa: BLE001 (PyAV, ffmpeg o el disco: lo que sea, el archivo no se escribe)
            raise ExportError(str(error)) from error

    def _open_av(self, codec: str, bit_rate: int | None) -> None:
        import av

        layout = "mono" if self.channels == 1 else "stereo"
        self._container = av.open(str(self.path), "w")
        stream = self._container.add_stream(codec, rate=self._out_rate, layout=layout)
        if bit_rate:
            stream.codec_context.bit_rate = bit_rate
        self._stream = stream
        fmt = stream.codec_context.format.name if stream.codec_context.format else "s16"
        # Cuadros del tamaño que el codificador pide (1152 en MP3, 960 en Opus), a su frecuencia.
        self._resampler = av.AudioResampler(format=fmt, layout=layout, rate=self._out_rate,
                                            frame_size=stream.codec_context.frame_size or None)
        self._av = av
        self._layout = layout
        self._pts = 0

    def _open_ffmpeg(self, codec: str, bit_rate: int | None) -> None:
        command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(self.rate), "-ac",
                   str(self.channels), "-i", "pipe:0", "-c:a", codec, "-ar", str(self._out_rate)]
        if bit_rate:
            command += ["-b:a", str(bit_rate)]
        command.append(str(self.path))
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE, creationflags=flags)

    def write(self, frames: np.ndarray) -> None:
        if not len(frames):
            return
        try:
            if self._wave is not None:
                ints = np.clip(np.rint(frames * 32768.0), -32768, 32767).astype("<i2")
                self._wave.writeframes(ints.tobytes())
            elif self._container is not None:
                self._encode(np.ascontiguousarray(frames, np.float32))
            else:
                self._process.stdin.write(np.ascontiguousarray(frames, "<f4").tobytes())
        except Exception as error:  # noqa: BLE001
            raise ExportError(str(error)) from error

    def _encode(self, frames: np.ndarray | None) -> None:
        av = self._av
        if frames is None:
            pieces = self._resampler.resample(None)
        else:
            frame = av.AudioFrame.from_ndarray(frames.reshape(1, -1), format="flt", layout=self._layout)
            frame.rate = self.rate
            frame.pts = self._pts
            self._pts += len(frames)
            pieces = self._resampler.resample(frame)
        for piece in pieces:
            for packet in self._stream.encode(piece):
                self._container.mux(packet)

    def close(self) -> None:
        """Finish the file."""
        try:
            if self._wave is not None:
                self._wave.close()
            elif self._container is not None:
                self._encode(None)
                for packet in self._stream.encode(None):
                    self._container.mux(packet)
                self._container.close()
            elif self._process is not None:
                self._process.stdin.close()
                error = self._process.stderr.read().decode(errors="replace").strip()
                if self._process.wait() != 0:
                    raise ExportError(error.splitlines()[-1] if error else "ffmpeg failed")
        except ExportError:
            raise
        except Exception as error:  # noqa: BLE001
            raise ExportError(str(error)) from error

    def abort(self) -> None:
        """Stop, and remove what was written."""
        try:
            if self._wave is not None:
                self._wave.close()
            elif self._container is not None:
                self._container.close()
            elif self._process is not None:
                self._process.kill()
                self._process.wait()
        except Exception:  # noqa: BLE001 (lo que quede se borra de todos modos)
            pass
        self.path.unlink(missing_ok=True)


def export(audio: Audio, path: str | os.PathLike, format_: str, settings: Settings,
           cancel: threading.Event | None = None, progress: Callable[[float], None] | None = None) -> bool:
    """Write the recording, as SETTINGS say, into PATH. False if it was cancelled (and nothing is left)."""
    writer = Writer(path, format_, audio.rate, audio.channels)
    try:
        for frames in render(audio, settings, cancel, progress):
            writer.write(frames)
        if cancel is not None and cancel.is_set():
            writer.abort()
            return False
        writer.close()
    except BaseException:
        writer.abort()
        raise
    return True
