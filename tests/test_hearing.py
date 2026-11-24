"""Cómo se oye: los canales y los filtros, bloque tras bloque, sin costuras ni chasquidos."""

import numpy as np
import pytest
from conftest import RATE, tone, write

from py_slowdown.audio import Audio
from py_slowdown.engine import Player
from py_slowdown.hearing import Hearing, delay, kernel, mix


def two_tones(seconds: float = 2.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return np.stack([np.sin(2 * np.pi * 100 * t), 0.5 * np.sin(2 * np.pi * 2000 * t)], axis=1).astype(np.float32)


def in_blocks(hearing: Hearing, frames: np.ndarray, size: int = 1024) -> np.ndarray:
    return np.concatenate([hearing.process(frames[i:i + size]) for i in range(0, len(frames), size)])


@pytest.mark.parametrize("filter_", ["bass", "no_bass"])
def test_filters_are_a_convolution(filter_):
    """Block after block, the filter is the convolution with its kernel, as if the whole were done at once."""
    x = two_tones()
    out = in_blocks(Hearing(RATE, "both", filter_), x, size=1000)
    reference = np.stack([np.convolve(x[:, c], kernel(filter_, RATE))[:len(x)] for c in range(2)], axis=1)
    assert np.abs(out - reference).max() < 1e-5


def test_what_the_filters_let_through():
    x = two_tones()
    bass = in_blocks(Hearing(RATE, "both", "bass"), x)[RATE:]
    no_bass = in_blocks(Hearing(RATE, "both", "no_bass"), x)[RATE:]
    assert np.abs(bass[:, 0]).max() > 0.98 and np.abs(bass[:, 1]).max() < 0.001  # (100 Hz pasa; 2 kHz no)
    assert np.abs(no_bass[:, 0]).max() < 0.001 and np.abs(no_bass[:, 1]).max() > 0.49
    assert delay("bass", RATE) == delay("no_bass", RATE) > 0 and delay("none", RATE) == 0


def test_channels():
    frames = np.array([[0.5, 0.1], [0.2, 0.2]], np.float32)
    assert mix(frames, "both") is frames
    assert np.allclose(mix(frames, "left"), [[0.5, 0.5], [0.2, 0.2]])
    assert mix(frames, "right")[:, 0].tolist() == pytest.approx([0.1, 0.2])
    assert mix(frames, "mono")[:, 1].tolist() == pytest.approx([0.3, 0.2])
    assert mix(frames, "no_centre")[:, 0].tolist() == pytest.approx([0.28, 0.0])  # (lo que es igual se anula)
    assert mix(frames[:, :1], "left").shape == (2, 1)  # (un archivo mono, tal cual)


def test_plain_is_the_sound_itself():
    x = two_tones(0.5)
    hearing = Hearing(RATE)
    assert all(hearing.process(x[i:i + 512]) is not None for i in range(0, len(x), 512))
    assert np.array_equal(in_blocks(Hearing(RATE), x), x)


def test_changing_has_no_click():
    """A change of the way of hearing, while it sounds, goes from one to the other in a fade: no jump."""
    t = np.arange(RATE * 2) / RATE
    x = np.repeat((0.5 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)[:, None], 2, axis=1)
    hearing = Hearing(RATE)
    out = []
    for n, i in enumerate(range(0, len(x), 1024)):
        if n == 40:
            hearing.set("both", "bass")  # (con su retraso de 20 ms)
        if n == 60:
            hearing.set("left", "none")
        out.append(hearing.process(x[i:i + 1024]))
    out = np.concatenate(out)
    step = np.abs(np.diff(out[:, 0])).max()
    assert step < 2 * np.abs(np.diff(x[:, 0])).max()  # (como mucho el paso de la onda misma)


def test_player_hears_one_channel(tmp_path, output):
    import time

    path = tmp_path / "two.wav"
    left_only = tone(3.0)
    left_only[:, 1] = 0.0
    write(path, left_only)
    audio = Audio(path)
    audio.wait(10)
    player = Player(output)
    player.load(audio)

    def heard(seconds: float) -> np.ndarray:
        # Lo que suena desde que se pide hasta SECONDS después (la cola ya hecha se oye antes: unos 0,15 s)
        pieces = []
        start = player.position
        while player.position < start + seconds:
            pieces.append(output.pull(512))
            time.sleep(0.001)
        return np.concatenate(pieces)

    player.hearing = ("right", "none")
    player.play()
    heard(0.3)
    assert np.abs(heard(0.5)).max() == 0.0  # (el derecho está en silencio)
    player.hearing = ("left", "none")
    heard(0.3)
    later = heard(0.5)
    assert np.abs(later[:, 1]).max() > 0.01 and np.array_equal(later[:, 0], later[:, 1])  # (el izquierdo, a los dos lados)
    player.unload()
    audio.close()
