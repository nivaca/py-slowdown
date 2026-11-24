"""Cómo se oye la grabación: qué canales y qué parte del espectro.

Para sacar de oído una parte de una mezcla sirve oírla sola, o casi: un canal
(lo que se grabó a un lado), los dos en uno (mono), la mezcla sin lo que está en
el centro (la diferencia de los canales: la voz y el solo suelen estar allí),
solo los graves (la línea del bajo) o todo menos los graves.

Hearing hace eso con los bloques de salida, uno tras otro. Los canales se mezclan
cuadro por cuadro; los filtros son FIR de fase lineal, aplicados con la FFT
(NumPy no tiene filtros recursivos, y uno en Python puro sería lento), con la
memoria de los últimos cuadros recibidos, de modo que un bloque sigue al anterior
sin costura. Un filtro retrasa el sonido medio largo de su núcleo (unos 20 ms);
al cambiar de modo, el bloque siguiente pasa del uno al otro en un fundido, sin
chasquido.
"""

from __future__ import annotations

import numpy as np

CHANNELS = ("both", "left", "right", "mono", "no_centre")
FILTERS = ("none", "bass", "no_bass")
CROSSOVER = 250.0  # Hz: debajo, «los graves»
KERNEL_SECONDS = 0.04  # el largo del núcleo: más largo, un corte más neto y más retraso


def kernel(kind: str, rate: int) -> np.ndarray:
    """The taps of a linear-phase FIR filter: "bass" lets through what is below CROSSOVER, "no_bass" what is
    above."""
    size = int(KERNEL_SECONDS * rate) | 1  # (impar: el retraso es un número entero de cuadros)
    middle = size // 2
    n = np.arange(size) - middle
    cutoff = CROSSOVER / rate
    # Una sinc con ventana de Blackman: unos 60 dB de rechazo, una transición de unos 100 Hz
    low = 2 * cutoff * np.sinc(2 * cutoff * n) * np.blackman(size)
    low /= low.sum()
    if kind == "bass":
        return low.astype(np.float32)
    high = -low
    high[middle] += 1.0  # (lo que queda del sonido entero sin los graves)
    return high.astype(np.float32)


def delay(filter_: str, rate: int) -> int:
    """Frames by which FILTER delays the sound."""
    return 0 if filter_ == "none" else (int(KERNEL_SECONDS * rate) | 1) // 2


def mix(frames: np.ndarray, channels: str) -> np.ndarray:
    """FRAMES (n × 2) heard as CHANNELS; mono files (n × 1) as they are."""
    if frames.shape[1] < 2 or channels == "both":
        return frames
    left, right = frames[:, 0], frames[:, 1]
    if channels == "left":
        one = left
    elif channels == "right":
        one = right
    elif channels == "mono":
        one = (left + right) * 0.5
    else:
        # Sin el centro: lo que está igual en los dos canales se anula (a 0,7: la diferencia puede pasar de 1)
        one = (left - right) * 0.7
    return np.repeat(one[:, None], 2, axis=1).astype(np.float32)


class Hearing:
    """The channels and the filter of the sound, applied block after block."""

    def __init__(self, rate: int, channels: str = "both", filter_: str = "none"):
        self.rate = rate
        self.channels = channels if channels in CHANNELS else "both"
        self.filter = filter_ if filter_ in FILTERS else "none"
        self._size = int(KERNEL_SECONDS * rate) | 1
        self._history: np.ndarray | None = None  # los últimos cuadros recibidos (size - 1), sin filtrar
        self._kernels: dict[tuple[str, int], np.ndarray] = {}  # (filtro, tamaño de la FFT): su espectro
        self._before: tuple[str, str] | None = None  # el modo de antes, mientras se funde con el nuevo

    @property
    def plain(self) -> bool:
        """Whether the sound is heard as it is."""
        return self.channels == "both" and self.filter == "none"

    def set(self, channels: str, filter_: str) -> None:
        channels = channels if channels in CHANNELS else "both"
        filter_ = filter_ if filter_ in FILTERS else "none"
        if (channels, filter_) != (self.channels, self.filter):
            self._before = (self.channels, self.filter)
            self.channels, self.filter = channels, filter_

    def reset(self) -> None:
        """Forget the frames received (after a jump: what came before is not what follows)."""
        self._history = None

    def process(self, frames: np.ndarray) -> np.ndarray:
        """The next FRAMES (n × channels, float32), as they are to be heard."""
        if not len(frames):
            return frames
        if self._history is None or self._history.shape[1] != frames.shape[1]:
            self._history = np.zeros((self._size - 1, frames.shape[1]), np.float32)
        whole = np.concatenate([self._history, frames])
        self._history = whole[len(whole) - (self._size - 1):]
        if self.plain and self._before is None:
            return frames
        out = self._apply(whole, len(frames), self.channels, self.filter)
        if self._before is not None:
            # Del modo de antes al nuevo, en un fundido a lo largo del bloque.
            old = self._apply(whole, len(frames), *self._before)
            self._before = None
            ramp = np.linspace(0.0, 1.0, len(frames), dtype=np.float32)[:, None]
            out = old * (1.0 - ramp) + out * ramp
        return out

    def _apply(self, whole: np.ndarray, count: int, channels: str, filter_: str) -> np.ndarray:
        if filter_ == "none":
            filtered = whole[len(whole) - count:]
        else:
            size = 1 << int(np.ceil(np.log2(len(whole))))
            key = (filter_, size)
            if key not in self._kernels:
                self._kernels[key] = np.fft.rfft(kernel(filter_, self.rate), size)
            spectrum = np.fft.rfft(whole, size, axis=0) * self._kernels[key][:, None]
            # (la convolución circular solo es buena desde el cuadro size - 1 del núcleo: lo que sigue a la historia)
            filtered = np.fft.irfft(spectrum, size, axis=0)[len(whole) - count:len(whole)].astype(np.float32)
        return mix(filtered, channels)
