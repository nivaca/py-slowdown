"""La altura: el detector de py-tuner (sus pruebas, copiadas de allí con él) y lo que py-slowdown hace con él:
seguir la altura de un trozo, partirlo en notas, afinar la nota de K y el espectro del panel Notas."""

from __future__ import annotations

import numpy as np
import pytest

from py_slowdown import notes, pitch
from py_slowdown.pitch import Detector

RATE = 48000  # (la de las pruebas de py-tuner)


def string(f1: float, seconds: float = 1.0, rate: int = RATE, b: float = 1e-4, harmonics: int = 20,
           fundamental: float = 1.0, snr_db: float | None = 40.0, decay: float = 0.5, seed: int = 0,
           attack: bool = False) -> np.ndarray:
    """A plucked-string tone whose FIRST PARTIAL is exactly F1 Hz.

    Partials at n·f0·√(1+B·n²) with amplitude 1/n (the first scaled by
    FUNDAMENTAL), each decaying a little faster than the one below, random
    phases, and white noise SNR_DB below the signal (None: no noise).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    f0 = f1 / np.sqrt(1 + b)
    x = np.zeros_like(t)
    for n in range(1, harmonics + 1):
        fn = n * f0 * np.sqrt(1 + b * n * n)
        if fn > 0.45 * rate:
            break
        a = (fundamental if n == 1 else 1.0) / n
        x += a * np.exp(-decay * np.sqrt(n) * t) * np.sin(2 * np.pi * fn * t + rng.uniform(0, 2 * np.pi))
    if attack:
        x *= np.minimum(1.0, t * 200)
    x *= 0.5 / np.max(np.abs(x))
    if snr_db is not None:
        power = np.mean(x * x) / 10 ** (snr_db / 10)
        x += rng.normal(0, np.sqrt(power), len(x))
    return x


def cents(f: float, ref: float) -> float:
    return 1200 * np.log2(f / ref)


# (nombre, primer parcial en Hz, inarmonicidad B): las cuerdas al aire de los
# cuatro instrumentos, de la más grave del bajo de cinco a la más aguda del violín.
STRINGS = [
    ("B0 bass", 30.868, 8e-5), ("E1 bass", 41.203, 5e-5), ("A1 bass", 55.0, 5e-5),
    ("E2 guitar", 82.407, 1e-4), ("A2 guitar", 110.0, 1e-4), ("D3 guitar", 146.832, 1e-4),
    ("G3 violin", 195.998, 2e-5), ("B3 guitar", 246.942, 2e-4), ("E4 guitar", 329.628, 3e-4),
    ("A4 violin", 440.0, 5e-5), ("E5 violin", 659.255, 5e-5),
]


def errors(x: np.ndarray, f1: float, det: Detector, hop: int = 2400) -> np.ndarray:
    """The error (cents) of every frame through X; NaN where nothing was found."""
    out = []
    for end in range(det.history, len(x) + 1, hop):
        e = det.analyze(x[end - det.history:end])
        out.append(cents(e.frequency, f1) if e.found else np.nan)
    return np.array(out)


@pytest.mark.parametrize(("label", "f1", "b"), STRINGS, ids=[s[0] for s in STRINGS])
def test_open_strings_within_a_tenth_of_a_cent(label, f1, b):
    # A 40 dB de relación señal/ruido, cada cuadro por sí solo cae a menos de 0,1 cent.
    det = Detector(rate=RATE)
    err = errors(string(f1, seconds=1.2, b=b, seed=int(f1)), f1, det)
    assert not np.isnan(err).any()
    assert np.max(np.abs(err)) < 0.1, err


@pytest.mark.parametrize(("label", "f1", "b"), STRINGS[::2], ids=[s[0] for s in STRINGS[::2]])
def test_noisy_strings_are_unbiased(label, f1, b):
    # With noise only 20 dB down, single frames scatter, but their mean stays put.
    det = Detector(rate=RATE)
    err = errors(string(f1, seconds=3.0, b=b, snr_db=20, decay=0.2, seed=7), f1, det)
    assert not np.isnan(err).any()
    assert abs(np.mean(err)) < 0.1
    assert np.std(err) < 0.4


@pytest.mark.parametrize("f1", [41.203, 82.407, 196.0])
def test_weak_fundamental(f1):
    # Un micrófono pequeño apenas recoge la fundamental de una cuerda grave:
    # la frecuencia sale de los armónicos y del ajuste de la inarmonicidad.
    det = Detector(rate=RATE)
    err = errors(string(f1, seconds=1.2, fundamental=0.02), f1, det)
    assert np.max(np.abs(err)) < 0.1


def test_missing_fundamental():
    det = Detector(rate=RATE)
    f1 = 55.0
    err = errors(string(f1, seconds=1.2, fundamental=0.0, b=0.0), f1, det)
    assert not np.isnan(err).any()
    assert np.max(np.abs(err)) < 0.2


def test_inharmonicity_is_fitted_and_does_not_bias():
    # A strongly inharmonic string: the upper partials are many cents sharp of n·f1.
    det = Detector(rate=RATE)
    f1, b = 82.407, 5e-4
    x = string(f1, seconds=1.2, b=b)
    e = det.analyze(x[-det.history:])
    assert abs(cents(e.frequency, f1)) < 0.1
    assert e.inharmonicity == pytest.approx(b, rel=0.15)
    assert e.harmonics >= 8


def test_strong_second_harmonic_is_not_an_octave_error():
    t = np.arange(RATE) / RATE
    f1 = 110.0
    x = 0.2 * np.sin(2 * np.pi * f1 * t) + 0.8 * np.sin(2 * np.pi * 2 * f1 * t + 1.0) \
        + 0.3 * np.sin(2 * np.pi * 3 * f1 * t)
    det = Detector(rate=RATE)
    e = det.analyze(x)
    assert abs(cents(e.frequency, f1)) < 0.05


def test_pure_sine_is_exact():
    t = np.arange(RATE) / RATE
    for f in (31.0, 100.0, 440.0 * 2 ** (0.37 / 1200), 1000.0):
        e = Detector(rate=RATE, fmax=1500).analyze(0.5 * np.sin(2 * np.pi * f * t + 0.3))
        assert abs(cents(e.frequency, f)) < 0.01, f


def test_other_sample_rates():
    for rate in (44100, 96000):
        f1 = 110.0
        det = Detector(rate=rate)
        x = string(f1, seconds=1.0, rate=rate)
        e = det.analyze(x[-det.history:])
        assert abs(cents(e.frequency, f1)) < 0.1


def test_silence_and_quiet_sounds_have_no_pitch():
    det = Detector(rate=RATE)
    assert not det.analyze(np.zeros(det.history)).found
    assert det.analyze(np.zeros(det.history)).level == float("-inf")
    quiet = 1e-4 * string(110.0, snr_db=None)  # -86 dBFS
    assert not det.analyze(quiet[-det.history:]).found
    assert not det.analyze(np.array([])).found


def test_noise_has_no_pitch():
    rng = np.random.default_rng(5)
    det = Detector(rate=RATE)
    found = [det.analyze(0.1 * rng.normal(size=det.history)).found for _ in range(10)]
    assert sum(found) == 0


def test_out_of_range_is_not_found():
    # Un La 440 cuando el margen acaba en 300 Hz no debe verse como otra nota.
    det = Detector(rate=RATE, fmin=27.5, fmax=300.0)
    t = np.arange(RATE) / RATE
    e = det.analyze(0.5 * np.sin(2 * np.pi * 440 * t))
    assert not e.found or abs(cents(e.frequency, 220.0)) < 1  # at most the octave below, never something else


def test_phasors_match_exp():
    f = np.array([41.2, 523.3, 4000.0])
    n = 5000
    t = (np.arange(n) - (n - 1) / 2) / RATE
    assert np.max(np.abs(pitch._phasors(f, n, RATE) - np.exp(-2j * np.pi * np.outer(f, t)))) < 1e-11


def test_nsdf_of_sine_peaks_at_the_period():
    t = np.arange(4800) / RATE
    x = np.sin(2 * np.pi * 100 * t)
    n = pitch.nsdf(x, 600)
    assert n[0] == pytest.approx(1.0)
    assert int(np.argmax(n[100:])) + 100 == 480


def test_level_db():
    assert pitch.level_db(np.ones(100)) == pytest.approx(0.0)
    assert pitch.level_db(np.full(100, 0.1)) == pytest.approx(-20.0)
    assert pitch.level_db(np.zeros(10)) == float("-inf")


def test_frame_sizes():
    det = Detector(rate=48000, fmin=40, periods=16)
    assert det.fine_size(1000) == pitch.MIN_FINE
    assert det.fine_size(40) == 19200
    assert det.history >= det.coarse_size


def test_no_pitch_without_a_whole_fine_frame():
    # Al empezar a escuchar el búfer tiene pocas muestras: un cuadro corto no da altura, en vez de una mala.
    det = Detector(rate=RATE)
    x = string(110.0, seconds=1.0)
    assert not det.analyze(x[-(det.fine_size(110.0) - 100):]).found
    assert det.analyze(x[-det.fine_size(110.0):]).found


def test_weak_odd_harmonics_are_not_an_octave_up():
    # A string whose odd partials are weak (a steel string on a small microphone): the period alone reads an
    # octave up; the harmonic score finds the odd partials and keeps the octave.
    rng = np.random.default_rng(1)
    t = np.arange(RATE) / RATE
    f = 82.41
    x = sum((1 / n if n % 2 == 0 else 0.06 / n) * np.sin(2 * np.pi * n * f * t + rng.uniform(0, 6))
            for n in range(1, 13))
    x = 0.4 * x / np.abs(x).max() + rng.normal(0, 1e-4, len(t))
    e = Detector(rate=RATE, fmin=50, fmax=700).analyze(x)
    assert abs(cents(e.frequency, f)) < 0.1


def test_choose_octave_up_from_a_subharmonic():
    # Un período tres veces el verdadero (el submúltiplo de dos cuerdas que resuenan): la puntuación lo corrige.
    x = string(143.0, seconds=1.0, b=0.0)
    n = pitch.nsdf(x[-8000:], 4000)
    period = RATE / 143.0

    def periodicity(r):
        i = int(round(3 * period / r))
        return n[i - 1:i + 2].max() / n[int(round(3 * period))]

    f = pitch.choose_octave(x, RATE, 143.0 / 3, 40, 700, 16, None, periodicity)
    assert abs(cents(f, 143.0)) < 5


def test_continuity_breaks_a_tie():
    x = string(110.0, seconds=1.0, snr_db=10, decay=3.0)
    guess = 110.0
    assert pitch.choose_octave(x, RATE, guess, 40, 700, 16, prefer=110.0) == guess


def test_highpass_keeps_the_phase_above_the_corner():
    t = np.arange(48000) / RATE
    # (un retumbo de 3 Hz, 40 dB bajo un filtro de segundo orden a 30 Hz, y la continua)
    x = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 3 * t) + 0.3
    y = pitch.highpass(x, RATE, 30.0)
    core = slice(2000, -2000)
    assert np.max(np.abs(y[core] - np.sin(2 * np.pi * 440 * t)[core])) < 0.02


def test_prominence_marks_partials_not_noise():
    rng = np.random.default_rng(2)
    t = np.arange(16384) / RATE
    x = np.sin(2 * np.pi * 300 * t) + rng.normal(0, 0.01, len(t))
    prom, df = pitch.prominence(x, RATE)
    assert prom[int(300 / df)] > 30
    assert np.median(prom) < 6


# --- Lo de py-slowdown: track, split, sharpen y el espectro

def melody(parts, rate=44100, noise=0.002):
    """Notes one after another, PARTS = [(midi, seconds, cents)], each with five harmonics, a short attack and a
    decay, and a little noise."""
    out = []
    for midi, seconds, off in parts:
        t = np.arange(int(rate * seconds)) / rate
        f = notes.frequency(midi + off / 100)
        x = sum(a * np.sin(2 * np.pi * f * h * t) for h, a in enumerate((1, 0.5, 0.3, 0.2, 0.1), 1))
        out.append(x * np.minimum(1, t / 0.01) * np.exp(-1.5 * t))
    x = np.concatenate(out)
    x = 0.4 * x / np.abs(x).max()
    return x + np.random.default_rng(3).normal(0, noise, len(x))


def test_track_finds_each_note_of_a_melody():
    parts = [(55, 0.5, 7), (57, 0.5, -12), (59, 0.3, 0), (60, 0.7, 20), (40, 0.6, 0), (28, 0.8, -5), (84, 0.5, 3)]
    x = melody(parts)
    seen = []
    track = pitch.track(np.stack([x, x], axis=1), 44100, 0.0, 0.0, len(x) / 44100, progress=seen.append)
    assert seen and seen[0] == 0.0 and all(0 <= f < 1 for f in seen)
    assert track.found and len(track.times) == len(track.hz)
    assert [notes.nearest(n.hz)[0] for n in track.notes] == [p[0] for p in parts]
    for note, (_midi, _seconds, off) in zip(track.notes, parts):
        assert notes.nearest(note.hz)[1] == pytest.approx(off, abs=0.2)
    # (cada nota empieza y termina cerca de donde suena)
    starts = np.cumsum([0] + [p[1] for p in parts[:-1]])
    for note, start, (_m, seconds, _c) in zip(track.notes, starts, parts):
        assert start - 0.05 <= note.start <= start + 0.15 and note.end <= start + seconds + 0.05


def test_track_of_a_part_with_its_offset():
    # Las muestras empiezan en el segundo 10 de la grabación; se sigue del 10,5 al 11,5.
    x = melody([(57, 2.5, 0)])
    track = pitch.track(x, 44100, 10.0, 10.5, 11.5)
    assert track.start == 10.5 and track.end == 11.5
    assert track.times.min() >= 10.49 and track.times.max() <= 11.51
    assert len(track.notes) == 1 and notes.nearest(track.notes[0].hz)[0] == 57


def test_track_can_be_cancelled_and_silence_has_no_pitch():
    x = melody([(57, 1.0, 0)])
    assert pitch.track(x, 44100, 0.0, 0.0, 1.0, cancelled=lambda: True) is None
    quiet = pitch.track(np.zeros(44100), 44100, 0.0, 0.0, 1.0)
    assert not quiet.found and quiet.notes == []


def test_the_quiet_tail_has_no_pitch():
    # Una nota fuerte y luego otra 50 dB más baja: la segunda es la cola, o la sala, y no cuenta.
    x = np.concatenate([melody([(57, 0.6, 0)]), 10 ** (-50 / 20) * melody([(64, 0.6, 0)], noise=0.0)])
    track = pitch.track(x, 44100, 0.0, 0.0, len(x) / 44100)
    assert [notes.nearest(n.hz)[0] for n in track.notes] == [57]


def test_split_strays_glides_and_gaps():
    times = np.arange(0, 2, 0.02)
    hz = np.full(len(times), 220.0)
    hz[10] = 440.0  # (un valor suelto, una octava arriba: no corta la nota)
    hz[11] = 440.0
    # un vibrato de ±30 cents sigue siendo la misma nota
    hz[20:50] = 220 * 2 ** (30 * np.sin(np.arange(30) / 3) / 1200)
    hz[50:52] = 0.0  # (dos cuadros sin altura: la nota sigue)
    hz[70:75] = 0.0  # (100 ms: se termina, y empieza otra)
    hz[75:] = 330.0
    found = pitch.split(times, hz)
    assert len(found) == 2
    assert found[0].start == 0 and found[0].end == pytest.approx(times[69])
    assert found[0].hz == pytest.approx(220.0, rel=0.01) and found[1].hz == pytest.approx(330.0)
    # (una nota más corta que MIN_NOTE no cuenta)
    assert pitch.split(times[:4], hz[:4]) == []


def test_strays_are_removed():
    hz = np.array([0, 220, 0, 0, 220, 221, 0, 440, 220, 0.0])
    assert list(pitch._without_strays(hz)) == [0, 0, 0, 0, 220, 221, 0, 0, 0, 0]


def test_sharpen_measures_to_hundredths_of_a_cent():
    x = string(146.832 * 2 ** (-13 / 1200), seconds=1.0, b=1e-4, seed=2)
    f = pitch.sharpen(x, RATE, 146.0)
    assert cents(f, 146.832) == pytest.approx(-13, abs=0.05)
    assert pitch.sharpen(x, RATE, 146.832 * 1.2) is None  # (lejos de la nota: nada que afinar)
    assert pitch.sharpen(np.zeros(100), RATE, 146.0) is None


def test_find_the_note_is_sharper():
    # notes.find usa sharpen: con la nota sintética de test_notes, a menos de una décima de cent.
    t = np.arange(int(44100 * 1.5)) / 44100
    f = notes.frequency(57 - 0.137)
    wave = sum(a * np.sin(2 * np.pi * f * h * t) for h, a in enumerate((1, 0.5, 0.3, 0.2, 0.1), 1))
    found = notes.find(np.stack([wave, wave], axis=1).astype(np.float32) * 0.3, 44100)
    assert found.midi == 57 and found.cents == pytest.approx(-13.7, abs=0.1)


def test_spectrum_points_and_named_peaks():
    t = np.arange(int(44100 * 1.0)) / 44100
    x = np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 660 * t)
    x += np.random.default_rng(0).normal(0, 0.001, len(x))
    mag, bin_hz = notes.spectrum(x, 44100)
    freqs, levels = pitch.spectrum_points(mag, bin_hz)
    assert len(freqs) == len(levels) == 300 and levels.max() == pytest.approx(0.0, abs=0.5)
    assert freqs[0] > pitch.SPECTRUM_LOW and freqs[-1] < pitch.SPECTRUM_HIGH
    peaks = pitch.named_peaks(mag, bin_hz)
    assert [round(f) for f, _ in peaks[:2]] == [220, 660]
    assert peaks[1][1] == pytest.approx(20 * np.log10(0.3), abs=1.0)
