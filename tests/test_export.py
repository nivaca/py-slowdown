"""Guardar la grabación como se oye: el archivo entero a 1× es él mismo; una selección, a otra velocidad, dura lo
que debe; los filtros no la atrasan; los formatos se leen de nuevo."""

import threading

import numpy as np
import pytest
from conftest import RATE, tone, write

from py_slowdown import export
from py_slowdown.audio import Audio
from py_slowdown.export import Settings


@pytest.fixture
def audio(tmp_path, decoder):
    path = tmp_path / "clicks.wav"
    write(path, tone(6.0))
    a = Audio(path)
    a.wait(10)
    yield a
    a.close()


def read_back(path) -> Audio:
    a = Audio(path)
    a.wait(10)
    return a


def test_whole_file_at_1x_is_the_file(audio, tmp_path):
    out = tmp_path / "same.wav"
    assert export.export(audio, out, "wav", Settings())
    again = read_back(out)
    assert again.decoded == audio.decoded
    assert np.array_equal(again._data[:again.decoded], audio._data[:audio.decoded])
    again.close()


@pytest.mark.parametrize("speed", [0.5, 1.25])
def test_selection_at_another_speed(audio, tmp_path, speed):
    out = tmp_path / "part.wav"
    shares = []
    export.export(audio, out, "wav", Settings(start=1.5, end=4.5, speed=speed), progress=shares.append)
    again = read_back(out)
    assert again.duration == pytest.approx(3.0 / speed, abs=0.03)
    assert shares[-1] == 1.0 and shares == sorted(shares)
    # Los golpes de los segundos 2, 3 y 4 caen donde deben, contados desde 1,5 s, a esa velocidad
    left = again.frames(0, again.decoded)[:, 0]
    loud = np.flatnonzero(np.abs(left) > 0.5)
    peaks = [loud[0] / RATE] + [b / RATE for a, b in zip(loud, loud[1:]) if b - a > RATE // 10]  # (un golpe, una vez)
    assert [round(p * speed, 1) for p in peaks] == [0.5, 1.5, 2.5]
    edges = np.abs(left[:5]).max(), np.abs(left[-5:]).max()
    assert max(edges) < 0.05  # (entra y sale en una rampa)
    again.close()


def test_filters_do_not_delay(audio, tmp_path):
    """With a filter, the export has the same length, and its clicks at the same places, as without."""
    plain, filtered = tmp_path / "plain.wav", tmp_path / "no_bass.wav"
    export.export(audio, plain, "wav", Settings())
    export.export(audio, filtered, "wav", Settings(hearing=("left", "no_bass")))
    a, b = read_back(plain), read_back(filtered)
    assert a.decoded == b.decoded
    x, y = a.frames(0, a.decoded)[:, 0], b.frames(0, b.decoded)[:, 1]
    assert abs(int(np.argmax(np.abs(y[RATE // 2:RATE * 3 // 2]))) - int(np.argmax(x[RATE // 2:RATE * 3 // 2]))) <= 2
    a.close()
    b.close()


@pytest.mark.parametrize("format_", ["flac", "mp3", "opus"])
def test_formats(audio, tmp_path, format_):
    out = tmp_path / f"slow{export.FORMATS[format_][0]}"
    assert export.export(audio, out, format_, Settings(speed=0.75, pitch=-2.0))
    again = read_back(out)
    assert again.duration == pytest.approx(6.0 / 0.75, abs=0.1)
    assert again.rate == (48000 if format_ == "opus" else RATE)
    again.close()


def test_cancel_leaves_nothing(audio, tmp_path):
    out = tmp_path / "cancelled.flac"
    cancel = threading.Event()
    cancel.set()
    assert not export.export(audio, out, "flac", Settings(speed=0.5), cancel=cancel)
    assert not out.exists()


def test_available():
    assert export.available()[0] == "wav" and set(export.available()) <= set(export.FORMATS)
