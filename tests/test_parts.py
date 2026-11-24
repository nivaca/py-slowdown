"""La lectura por partes, en paralelo: siempre idéntica a la seguida, y de corrido cuando una parte no coincide."""

import os
import sys

import numpy as np
import pytest
from conftest import RATE, write

from py_slowdown import audio as audio_module
from py_slowdown import parts
from py_slowdown.audio import Audio

SECONDS = 24.0


def music(seconds: float, rate: int = RATE) -> np.ndarray:
    """Something like music: a tone that wanders and a little noise (no stretch repeats itself, as a pure tone
    or silence would)."""
    rng = np.random.default_rng(11)
    t = np.arange(int(seconds * rate)) / rate
    x = 0.25 * np.sin(2 * np.pi * (220 + 60 * np.sin(t / 2)) * t) + 0.04 * rng.standard_normal(len(t))
    return np.stack([x, 0.7 * x + 0.03 * rng.standard_normal(len(t))], axis=1).astype(np.float32)


@pytest.fixture
def small_parts(monkeypatch):
    # Un archivo de 24 s, en cuatro partes de 6 s (las de verdad: desde 4 minutos, de un minuto o más).
    monkeypatch.setattr(parts, "MIN_SECONDS", 10.0)
    monkeypatch.setattr(parts, "MIN_PART", 5.0)
    monkeypatch.setattr(parts, "MAX_PARTS", 4)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)


def read(path, parallel: bool, monkeypatch) -> Audio:
    monkeypatch.setenv("PY_SLOWDOWN_PARALLEL", "1" if parallel else "0")
    audio = Audio(path)
    assert audio.wait(60)
    return audio


def same(a: Audio, b: Audio) -> bool:
    return (a.decoded == b.decoded and np.array_equal(a._data[:a.decoded], b._data[:b.decoded])
            and a.peaks.count == b.peaks.count
            and np.array_equal(a.peaks.lo[:a.peaks.count], b.peaks.lo[:b.peaks.count])
            and np.array_equal(a.peaks.hi[:a.peaks.count], b.peaks.hi[:b.peaks.count]))


@pytest.mark.parametrize("suffix", [".mp3", ".opus", ".ogg", ".flac"])
def test_parts_are_the_straight_reading(tmp_path, suffix, decoder, small_parts, monkeypatch):
    """Each later part, read by a process of its own, is put after the one before where the second before it
    agrees sample for sample: the whole is the straight reading, sample for sample, peaks and all."""
    rate = 48000 if suffix == ".opus" else RATE
    path = tmp_path / f"music{suffix}"
    write(path, music(SECONDS, rate), rate=rate)
    straight = read(path, False, monkeypatch)
    assert straight.parts_used == 0
    parallel = read(path, True, monkeypatch)
    assert parallel.parts_used == 3 and not parallel.error
    assert same(straight, parallel)
    straight.close()
    parallel.close()
    assert not list((tmp_path / "xdg_cache_home" / "py-slowdown").glob("part-*"))  # (nada queda)


def test_aac_is_read_straight(tmp_path, decoder, small_parts, monkeypatch):
    """AAC is read straight on: its noise substitution (PNS) comes from a random generator that runs from the
    start of the file, so a part begun elsewhere would have other noise in those bands."""
    path = tmp_path / "music.m4a"
    write(path, music(SECONDS))
    audio = read(path, True, monkeypatch)
    assert audio.codec == "aac" and audio.parts_used == 0
    audio.close()


def test_a_part_that_disagrees(tmp_path, decoder, small_parts, monkeypatch):
    """When a part does not agree with what was read before it, the rest is read straight on."""
    path = tmp_path / "music.mp3"
    write(path, music(SECONDS))
    straight = read(path, False, monkeypatch)
    calls = []
    real = parts.align

    def second_fails(*args):
        calls.append(1)
        return None if len(calls) == 2 else real(*args)

    monkeypatch.setattr(parts, "align", second_fails)
    parallel = read(path, True, monkeypatch)
    assert parallel.parts_used == 1 and same(straight, parallel)


def test_a_part_that_fails(tmp_path, decoder, small_parts, monkeypatch):
    """A process that fails (here, the third part) is the same: the rest is read straight on."""
    path = tmp_path / "music.flac"
    write(path, music(SECONDS))
    straight = read(path, False, monkeypatch)
    calls = []
    real = Audio._start_part

    def third_fails(self, at, end):
        calls.append(1)
        if len(calls) == 3:
            monkeypatch.setattr(self._source, "part", lambda *args: ([sys.executable, "-c", "raise SystemExit(3)"],
                                                                     False, None))
        return real(self, at, end)

    monkeypatch.setattr(Audio, "_start_part", third_fails)
    parallel = read(path, True, monkeypatch)
    assert parallel.parts_used == 2 and same(straight, parallel)


def test_announced_longer_than_it_is(tmp_path, decoder, small_parts, monkeypatch):
    """A file that announces 60 s and lasts 24: the parts past its end have nothing, and it is read whole."""
    path = tmp_path / "music.mp3"
    write(path, music(SECONDS))
    straight = read(path, False, monkeypatch)
    monkeypatch.setattr(Audio, "_announced_seconds", lambda self: 60.0)
    parallel = read(path, True, monkeypatch)
    assert parallel.done and not parallel.error and same(straight, parallel)


def test_closed_while_reading(tmp_path, decoder, small_parts, monkeypatch):
    """Closing the file while the parts are read stops their processes and leaves no file behind."""
    path = tmp_path / "music.mp3"
    write(path, music(SECONDS))
    started = []
    real = parts.Part.__init__

    def keep(self, *args, **kwargs):
        real(self, *args, **kwargs)
        started.append(self)

    monkeypatch.setattr(parts.Part, "__init__", keep)
    monkeypatch.setenv("PY_SLOWDOWN_PARALLEL", "1")
    audio = Audio(path)
    audio.close()
    assert started and all(part._process.poll() is not None for part in started)
    assert not list((tmp_path / "xdg_cache_home" / "py-slowdown").glob("part-*"))


def test_resampled_files_are_read_straight(tmp_path, small_parts, monkeypatch):
    """At another rate than the file's (the sound card's) it is read straight on: the resampler has a memory,
    and the seams would not be those of a straight reading."""
    path = tmp_path / "music.flac"
    write(path, music(SECONDS))
    monkeypatch.setenv("PY_SLOWDOWN_PARALLEL", "1")
    audio = Audio(path, rate=48000)
    assert audio.wait(60) and audio.parts_used == 0
    audio.close()


def test_plan(monkeypatch):
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    monkeypatch.delenv("PY_SLOWDOWN_PARALLEL", raising=False)
    assert parts.plan(120.0, RATE) == []  # (corto: de corrido)
    assert parts.plan(600.0, RATE) == [150 * RATE, 300 * RATE, 450 * RATE]
    monkeypatch.setenv("PY_SLOWDOWN_PARALLEL", "0")
    assert parts.plan(600.0, RATE) == []
    monkeypatch.delenv("PY_SLOWDOWN_PARALLEL")
    monkeypatch.setattr(os, "process_cpu_count", lambda: 1, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    assert parts.plan(600.0, RATE) == []  # (un solo procesador)


def test_align():
    rng = np.random.default_rng(3)
    whole = rng.integers(-3000, 3000, (20000, 2)).astype(np.int16)
    window = whole[9000:10000]
    head = whole[7000:15000]
    assert parts.align(window, 9000, head, 7000) == 7000  # (donde los tiempos dicen)
    assert parts.align(window, 9000, head, 6990) == 7000  # (los tiempos se equivocan: se busca)
    assert parts.align(window, 9000, whole[9500:15000], None) is None  # (no está)
    silence = np.zeros((1000, 2), np.int16)
    assert parts.align(silence, 9000, np.zeros((8000, 2), np.int16), None) is None  # (estaría en cualquier parte)
    assert parts.align(silence, 9000, np.zeros((8000, 2), np.int16), 7000) == 7000  # (los tiempos lo dicen)
    assert parts.align(window, 9000, np.concatenate([head, head]), None) is None  # (dos veces: no se sabe)


def test_interpreter(monkeypatch, tmp_path):
    """On Windows the program runs in pythonw.exe; its parts, in the python.exe beside it, and with -s if it has it."""
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    assert parts.interpreter()[0] == str(tmp_path / "python.exe")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    assert parts.interpreter()[0] == "/usr/bin/python3"


def test_sweep(tmp_path):
    """The files of parts that a program ended abruptly left (on Windows) go after an hour, not before."""
    old, new = tmp_path / "part-old", tmp_path / "part-new"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    os.utime(old, (0, 0))
    parts.sweep(tmp_path)
    assert not old.exists() and new.exists()
