"""El ecualizador de cinco bandas: lo que pide cada banda, sin costuras entre bloques ni chasquidos al cambiar."""

import numpy as np
import pytest
from conftest import RATE, tone, write

from py_slowdown import equalizer, export
from py_slowdown.audio import Audio
from py_slowdown.equalizer import BANDS, Equalizer, kernel


def in_blocks(eq: Equalizer, frames: np.ndarray, size: int = 1024) -> np.ndarray:
    return np.concatenate([eq.process(frames[i:i + size]) for i in range(0, len(frames), size)])


@pytest.mark.parametrize("gains", [(6, 0, 0, 0, 0), (0, -6, 0, 0, 0), (0, 0, 12, 0, 0), (0, 0, 0, -12, 0),
                                   (0, 0, 0, 0, 6), (3, -3, 6, -6, 12)])
def test_each_band_gives_its_gain(gains):
    """At each band's frequency, the filter gives that band's gain, within 0.3 dB."""
    taps = kernel(gains, RATE)
    points = 1 << 16
    spectrum = np.abs(np.fft.rfft(taps, points))
    freqs = np.fft.rfftfreq(points, 1 / RATE)
    measured = [20 * np.log10(spectrum[np.argmin(np.abs(freqs - band))]) for band in BANDS]
    assert measured == pytest.approx(gains, abs=0.3)


def test_blocks_are_a_convolution():
    rng = np.random.default_rng(4)
    x = rng.uniform(-0.3, 0.3, (RATE, 2)).astype(np.float32)
    gains = (4, -2, 0, 3, -6)
    out = in_blocks(Equalizer(RATE, gains), x, size=1000)
    reference = np.stack([np.convolve(x[:, c], kernel(gains, RATE))[:len(x)] for c in range(2)], axis=1)
    assert np.abs(out - reference).max() < 1e-5


def test_flat_is_the_sound_itself():
    x = tone(1.0)
    eq = Equalizer(RATE)
    assert np.array_equal(in_blocks(eq, x), x) and equalizer.delay(eq.gains, RATE) == 0
    assert equalizer.clamp([20, -30, 1.4]) == (12, -12, 1, 0, 0)


def test_turning_a_knob_makes_no_click():
    t = np.arange(RATE * 2) / RATE
    x = np.repeat((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)[:, None], 2, axis=1)
    eq = Equalizer(RATE)
    out = []
    for n, i in enumerate(range(0, len(x), 1024)):
        if 30 <= n < 60:
            eq.set((0, (n - 30) % 13, 0, 0, 0))  # (la perilla de 250 Hz, girada bloque tras bloque)
        out.append(eq.process(x[i:i + 1024]))
    out = np.concatenate(out)
    # (a +12 dB la onda es casi cuatro veces más alta, y su pendiente también; un chasquido saltaría mucho más)
    assert np.abs(np.diff(out[:, 0])).max() < 4.5 * np.abs(np.diff(x[:, 0])).max()


def test_export_with_the_equalizer_is_not_delayed(tmp_path):
    """Exported with the equalizer, the recording has the same length and its clicks at the same places."""
    path = tmp_path / "clicks.wav"
    write(path, tone(4.0))
    audio = Audio(path)
    audio.wait(10)
    plain, equalized = tmp_path / "plain.wav", tmp_path / "eq.wav"
    export.export(audio, plain, "wav", export.Settings())
    export.export(audio, equalized, "wav", export.Settings(eq=(0, 0, 6, 0, -6)))
    a, b = Audio(plain), Audio(equalized)
    a.wait(10)
    b.wait(10)
    assert a.decoded == b.decoded
    x, y = a.frames(0, a.decoded)[:, 0], b.frames(0, b.decoded)[:, 0]
    # (el ecualizador cambia la forma de cada golpe, no su lugar: la correlación da el desfase, que debe ser 0)
    window = slice(RATE // 2, RATE * 3 // 2)
    lags = range(-200, 201)
    scores = [float(np.dot(x[window], np.roll(y, -lag)[window])) for lag in lags]
    assert lags[int(np.argmax(scores))] == 0
    for one in (a, b, audio):
        one.close()
