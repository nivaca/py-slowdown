"""Las notas: cuál suena en un trozo de la grabación, y un tono de referencia.

find() busca la nota principal de unos cuadros: promedia su espectro (ventanas
de Hann de unos 0,37 s, a lo sumo MAX_WINDOWS repartidas por el trozo) y, para
cada fundamental posible entre E1 y C7, de diez en diez cents, suma lo que hay
en sus armónicos, cada uno con menos peso que el anterior. La fundamental que
más suma es la nota; su frecuencia se afina luego en el pico de su armónico más
fuerte. También da las otras notas que destacan (las de un acorde), sin las
octavas ni la duodécima de la principal, que son sus propios armónicos.

Tone hace el tono de referencia que suena con la grabación, o solo: una nota
(o un acorde sobre ella), con un timbre de pocos armónicos, que la tarjeta de
sonido pide a trozos (render). Cada cambio (de nota, de timbre, de volumen, al
encenderlo o apagarlo) pasa de lo anterior a lo nuevo a lo largo del trozo
siguiente, para que no se oiga un chasquido.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

A4 = 440.0  # Hz: the usual tuning
TUNINGS = (415.0, 430.0, 432.0, 435.0, 438.0, 440.0, 442.0, 443.0, 444.0, 446.0)
LOWEST, HIGHEST = 28, 96  # las fundamentales que se buscan: E1 (41 Hz) a C7 (2093 Hz), en números MIDI
HARMONICS = 10
MAX_WINDOWS = 120  # ventanas promediadas, a lo sumo, por largo que sea el trozo
MIN_SECONDS = 0.1  # un trozo más corto no dice nada


def names() -> tuple[str, ...]:
    """The twelve names of the notes, from C, in the language of the interface."""
    from .interface import tr

    return tuple(tr("C C♯ D E♭ E F F♯ G A♭ A B♭ B").split())


def name(midi: int) -> str:
    """The name of the note MIDI with its octave, as C4 is the middle C (60): A4, B♭2."""
    return f"{names()[midi % 12]}{midi // 12 - 1}"


def frequency(midi: float, a4: float = A4) -> float:
    """Hz of the note MIDI (fractions are cents), with A4 at A4 Hz."""
    return a4 * 2.0 ** ((midi - 69) / 12)


def nearest(hz: float, a4: float = A4) -> tuple[int, float]:
    """The nearest note to HZ, and how far it is from it, in cents (−50 to +50)."""
    exact = 69 + 12 * math.log2(hz / a4)
    midi = round(exact)
    return midi, (exact - midi) * 100


@dataclass
class Found:
    """What find() found: the main note's frequency, its note and its cents off it; other notes that stand out
    (MIDI numbers, the strongest first)."""

    hz: float
    midi: int
    cents: float
    others: list[int] = field(default_factory=list)

    def text(self) -> str:
        """C4 −12 ¢ (the cents left out when they are fewer than 3)."""
        return f"{name(self.midi)} {cents_text(self.cents)}".rstrip()


def cents_text(cents: float) -> str:
    """+12 ¢, −7 ¢, or nothing when it is within 3 cents of the note."""
    c = round(cents)
    if abs(c) < 3:
        return ""
    return f"{'+' if c > 0 else '−'}{abs(c)} ¢"


def spectrum(frames: np.ndarray, rate: int) -> tuple[np.ndarray, float]:
    """The average magnitude spectrum of FRAMES (mono or frames × channels), and the Hz of each of its bins."""
    mono = frames.mean(axis=1) if frames.ndim == 2 else frames
    mono = np.asarray(mono, dtype=np.float32)
    size = 1 << max(10, math.ceil(math.log2(rate * 0.37)))  # (16384 a 44,1 kHz: unos 2,7 Hz por banda)
    if len(mono) < size:
        mono = np.pad(mono, (0, size - len(mono)))
    hop = size // 2
    starts = np.arange(0, len(mono) - size + 1, hop)
    if len(starts) > MAX_WINDOWS:
        starts = np.linspace(0, len(mono) - size, MAX_WINDOWS).astype(int)
    window = np.hanning(size).astype(np.float32)
    power = np.zeros(size // 2 + 1)
    for start in starts:
        power += np.abs(np.fft.rfft(mono[start:start + size] * window)) ** 2
    return np.sqrt(power / len(starts)), rate / size


def _peak(mag: np.ndarray, center: float, radius: float) -> tuple[float, float]:
    # El pico más alto cerca de la banda CENTER (a RADIUS bandas), afinado con una parábola: (banda, altura).
    low, high = max(1, int(center - radius)), min(len(mag) - 2, int(math.ceil(center + radius)))
    if high < low:
        return center, 0.0
    i = low + int(np.argmax(mag[low:high + 1]))
    a, b, c = (math.log(mag[i + d] + 1e-12) for d in (-1, 0, 1))
    shift = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c < 0 else 0.0
    return i + max(-0.5, min(0.5, shift)), float(mag[i])


def find(frames: np.ndarray, rate: int, a4: float = A4) -> Found | None:
    """The main note of FRAMES (see the module's docstring), or None if there is none (silence, too short)."""
    if len(frames) < MIN_SECONDS * rate:
        return None
    mag, bin_hz = spectrum(frames, rate)
    if not np.any(mag > 1e-6 * math.sqrt(len(frames))):
        return None
    # Lo que se suma de cada banda: la raíz de su altura, menos el ruido de fondo de alrededor (así cuentan los
    # picos, y no el bajo ancho de una mezcla).
    level = np.sqrt(mag)
    floor = np.convolve(level, np.ones(64) / 64, mode="same")
    clean = np.maximum(level - floor, 0.0)
    steps = np.arange(LOWEST * 10, HIGHEST * 10 + 1) / 10  # MIDI, de diez en diez cents
    f0s = frequency(steps, a4)
    salience = np.zeros(len(steps))
    nyquist = rate / 2 * 0.9
    for h in range(1, HARMONICS + 1):
        bins = f0s * h / bin_hz
        radius = np.maximum(1.0, bins * (2 ** (1 / 48) - 1))  # (un cuarto de semitono a cada lado)
        lows = np.clip((bins - radius).astype(int), 0, len(clean) - 1)
        highs = np.clip(np.ceil(bins + radius).astype(int) + 1, 1, len(clean))
        values = np.array([clean[a:b].max() if b > a else 0.0 for a, b in zip(lows, highs)])
        values[f0s * h > nyquist] = 0.0
        salience += values / h ** 0.8
    best = int(np.argmax(salience))
    if salience[best] <= 0:
        return None
    f0 = float(f0s[best])
    # La frecuencia exacta, en el pico de uno de sus cuatro primeros armónicos: el más fuerte.
    peaks = [(_peak(mag, f0 * h / bin_hz, max(1.0, f0 * h / bin_hz * 0.03)), h) for h in range(1, 5)
             if f0 * h < nyquist]
    (center, _height), h = max(peaks, key=lambda p: p[0][1])
    hz = center * bin_hz / h
    midi, cents = nearest(hz, a4)
    others = _others(steps, salience, best, midi)
    return Found(hz, midi, cents, others)


def _others(steps: np.ndarray, salience: np.ndarray, best: int, main: int) -> list[int]:
    # Las otras notas que destacan, a lo sumo tres: cada nota, con lo más que suma a medio semitono de ella;
    # cuentan las que suman más que sus vecinas y al menos la mitad que la principal, sin las vecinas de esta
    # ni las que son armónicos suyos (o ella armónico de ellas) o de sus vecinas, ni las octavas de otra ya
    # elegida.
    notes = np.arange(LOWEST, HIGHEST + 1)
    per_note = np.array([salience[np.abs(steps - m) <= 0.5].max() for m in notes])
    related = {main + d for d in (-25, -24, -23, -19, -13, -12, -11, -1, 1, 12, 19, 24, 28)}
    found: list[int] = []
    for i in np.argsort(per_note)[::-1]:
        if per_note[i] < salience[best] * 0.5 or len(found) == 3:
            break
        if (i > 0 and per_note[i] < per_note[i - 1]) or (i < len(notes) - 1 and per_note[i] < per_note[i + 1]):
            continue
        midi = int(notes[i])
        if midi != main and midi not in related and not any(abs(midi - f) in (12, 24) for f in found):
            found.append(midi)
    return found


# --- el tono de referencia

TIMBRES = {
    "pure": (1.0,),  # una onda senoidal
    "soft": (1.0, 0.4, 0.15, 0.06),
    "bright": (1.0, 0.6, 0.45, 0.35, 0.28, 0.22, 0.18, 0.15),
}
CHORDS = {
    "note": (0,),
    "fifth": (0, 7),
    "octave": (0, 12),
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
}
LOUDEST = 0.35  # the amplitude of the tone at volume 100


@dataclass(frozen=True)
class ToneSettings:
    """What the reference tone plays: a note (MIDI) and cents off it, a chord on it (CHORDS), a timbre
    (TIMBRES), a volume (0 to 100), the tuning (Hz of A4), and whether it sounds."""

    midi: int = 57  # A3
    cents: int = 0
    chord: str = "note"
    timbre: str = "soft"
    volume: int = 50
    a4: float = A4
    on: bool = False

    def partials(self, rate: int) -> tuple[np.ndarray, np.ndarray]:
        """(Hz, amplitude) of each sine wave of the tone, the amplitudes adding up to its loudness."""
        hz, amps = [], []
        for interval in CHORDS.get(self.chord, (0,)):
            f = frequency(self.midi + interval + self.cents / 100, self.a4)
            for h, amp in enumerate(TIMBRES.get(self.timbre, (1.0,)), 1):
                if f * h < rate / 2 * 0.9:
                    hz.append(f * h)
                    amps.append(amp)
        if not hz:
            return np.zeros(0), np.zeros(0)
        amps_ = np.array(amps)
        loud = LOUDEST * (max(0, min(100, self.volume)) / 100) ** 2 if self.on else 0.0
        return np.array(hz), amps_ / amps_.sum() * loud


class Tone:
    """The reference tone (see the module's docstring), RATE frames a second."""

    def __init__(self, rate: int):
        self.rate = rate
        self.settings = ToneSettings()
        self._hz, self._amps = np.zeros(0), np.zeros(0)  # lo que suena ahora
        self._phases = np.zeros(0)
        self._wanted: tuple[np.ndarray, np.ndarray] | None = None  # lo que debe sonar desde el próximo trozo

    def set(self, settings: ToneSettings) -> None:
        """Play SETTINGS from the next block on (called from the window's thread)."""
        self.settings = settings
        self._wanted = settings.partials(self.rate)

    @property
    def silent(self) -> bool:
        return self._wanted is None and not np.any(self._amps)

    def _wave(self, hz: np.ndarray, amps: np.ndarray, phases: np.ndarray, frames: int,
              gains: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        # La suma de las senoidales de HZ y AMPS, desde PHASES: el trozo y las fases con que sigue.
        if not len(hz):
            return np.zeros(frames, dtype=np.float32), phases
        steps = 2 * np.pi * hz / self.rate
        t = np.arange(frames)[:, None]
        wave = (np.sin(phases[None, :] + steps[None, :] * t) * amps[None, :]).sum(axis=1)
        if gains is not None:
            wave *= gains
        return wave.astype(np.float32), (phases + steps * frames) % (2 * np.pi)

    def render(self, frames: int) -> np.ndarray:
        """The next FRAMES frames of the tone, mono (called from the sound card's thread)."""
        wanted, self._wanted = self._wanted, None
        if wanted is None:
            if not np.any(self._amps):
                return np.zeros(frames, dtype=np.float32)
            wave, self._phases = self._wave(self._hz, self._amps, self._phases, frames)
            return wave
        hz, amps = wanted
        if len(hz) == len(self._hz) and np.allclose(hz, self._hz):
            # La misma nota: solo cambia el volumen, de un extremo del trozo al otro, sin cortar las fases.
            ramp = np.linspace(0.0, 1.0, frames, dtype=np.float32)
            old, phases = self._wave(self._hz, self._amps, self._phases, frames, 1.0 - ramp)
            new, _ = self._wave(hz, amps, self._phases, frames, ramp)
            self._amps, self._phases = amps, phases
            return old + new
        # Otra nota: la de antes se apaga mientras la nueva se enciende.
        ramp = np.linspace(0.0, 1.0, frames, dtype=np.float32)
        old, _ = self._wave(self._hz, self._amps, self._phases, frames, 1.0 - ramp)
        start = np.zeros(len(hz))
        new, self._phases = self._wave(hz, amps, start, frames, ramp)
        self._hz, self._amps = hz, amps
        return old + new
