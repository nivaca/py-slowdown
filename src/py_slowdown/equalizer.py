"""El ecualizador: cinco bandas, de 60 Hz a 12 kHz, de −12 a +12 dB cada una.

Las cinco ganancias son puntos de una curva: entre dos bandas la curva va en
línea recta (en decibeles, sobre la escala logarítmica de la frecuencia), y más
allá de la primera y de la última sigue a su altura, de modo que la de 60 Hz es
también la de los graves más hondos y la de 12 kHz la de los agudos más altos.

NumPy no tiene filtros recursivos, y uno escrito en Python no daría abasto en
tiempo real; así que la curva se vuelve un filtro FIR de fase lineal (la
respuesta pedida, de la FFT al tiempo, centrada y suavizada con una ventana) y
se aplica con la FFT, bloque tras bloque, con la memoria de los últimos cuadros,
como los filtros de Oír (hearing.py). Atrasa el sonido medio largo de su núcleo,
unos 40 ms, que no se oyen y que la exportación quita; plano, no se aplica. Un
cambio de las ganancias pasa de la curva vieja a la nueva en un fundido, a lo
largo de un bloque.
"""

from __future__ import annotations

import numpy as np

BANDS = (60, 250, 1000, 4000, 12000)  # Hz
MAX_GAIN = 12  # dB, arriba o abajo
FLAT = (0, 0, 0, 0, 0)
KERNEL_SECONDS = 0.08  # el largo del núcleo: más largo, más fiel en los graves (y más retraso)


def size(rate: int) -> int:
    """The taps of the filter at RATE (odd: its delay is a whole number of frames)."""
    return int(KERNEL_SECONDS * rate) | 1


def delay(gains, rate: int) -> int:
    """Frames by which the equalizer with GAINS delays the sound (none when it is flat)."""
    return 0 if is_flat(gains) else size(rate) // 2


def is_flat(gains) -> bool:
    return all(g == 0 for g in gains)


def clamp(gains) -> tuple[int, ...]:
    """GAINS as five whole decibels from −MAX_GAIN to +MAX_GAIN (missing ones, 0)."""
    values = [int(round(float(g))) for g in list(gains)[:len(BANDS)]]
    values += [0] * (len(BANDS) - len(values))
    return tuple(max(-MAX_GAIN, min(MAX_GAIN, v)) for v in values)


def response(gains, freqs: np.ndarray) -> np.ndarray:
    """The gain in decibels, at each of FREQS, of the curve through GAINS."""
    where = np.log2(np.maximum(freqs, 1.0))
    return np.interp(where, np.log2(BANDS), np.asarray(gains, dtype=float))


def kernel(gains, rate: int) -> np.ndarray:
    """The taps of a linear-phase filter whose response follows the curve through GAINS."""
    taps = size(rate)
    points = 1 << int(np.ceil(np.log2(taps * 4)))
    freqs = np.fft.rfftfreq(points, 1 / rate)
    wanted = 10 ** (response(gains, freqs) / 20)
    impulse = np.fft.irfft(wanted, points)  # (de fase cero: simétrica alrededor del cuadro 0)
    impulse = np.roll(impulse, taps // 2)[:taps]
    return (impulse * np.hanning(taps)).astype(np.float32)


class Equalizer:
    """The five bands, applied to the sound block after block."""

    def __init__(self, rate: int, gains=FLAT):
        self.rate = rate
        self.gains = clamp(gains)
        self._size = size(rate)
        self._history: np.ndarray | None = None  # los últimos cuadros recibidos (size - 1)
        self._spectra: dict[tuple, np.ndarray] = {}  # (ganancias, tamaño de la FFT): el espectro del núcleo
        self._before: tuple[int, ...] | None = None  # las ganancias de antes, mientras se funden con las nuevas

    def set(self, gains) -> None:
        gains = clamp(gains)
        if gains != self.gains:
            self._before = self.gains
            self.gains = gains

    def reset(self) -> None:
        """Forget the frames received (after a jump: what came before is not what follows)."""
        self._history = None

    def process(self, frames: np.ndarray) -> np.ndarray:
        """The next FRAMES (n × channels, float32), equalized."""
        if not len(frames):
            return frames
        if self._history is None or self._history.shape[1] != frames.shape[1]:
            self._history = np.zeros((self._size - 1, frames.shape[1]), np.float32)
        whole = np.concatenate([self._history, frames])
        self._history = whole[len(whole) - (self._size - 1):]
        if is_flat(self.gains) and (self._before is None or is_flat(self._before)):
            self._before = None
            return frames
        out = self._apply(whole, len(frames), self.gains)
        if self._before is not None:
            old = self._apply(whole, len(frames), self._before)
            self._before = None
            ramp = np.linspace(0.0, 1.0, len(frames), dtype=np.float32)[:, None]
            out = old * (1.0 - ramp) + out * ramp
        return out

    def _apply(self, whole: np.ndarray, count: int, gains) -> np.ndarray:
        if is_flat(gains):
            return whole[len(whole) - count:]
        points = 1 << int(np.ceil(np.log2(len(whole))))
        key = (gains, points)
        if key not in self._spectra:
            if len(self._spectra) > 32:
                self._spectra.clear()  # (al girar una perilla se juntan muchos: los viejos ya no sirven)
            self._spectra[key] = np.fft.rfft(kernel(gains, self.rate), points)
        spectrum = np.fft.rfft(whole, points, axis=0) * self._spectra[key][:, None]
        # (la convolución circular solo es buena desde el cuadro size - 1: lo que sigue a la historia)
        return np.fft.irfft(spectrum, points, axis=0)[len(whole) - count:len(whole)].astype(np.float32)
