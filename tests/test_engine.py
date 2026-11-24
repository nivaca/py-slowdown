import time

import numpy as np
import pytest
from conftest import RATE

from py_slowdown.audio import Audio
from py_slowdown.engine import FADE, Player, Renderer, clamp_speed


@pytest.fixture
def audio(wav):
    a = Audio(wav)
    a.wait(10)
    yield a
    a.close()


def render_all(renderer):
    blocks = []
    while True:
        block, _seam = renderer.render()
        if block is None:
            return blocks
        if len(block.frames):
            blocks.append(block)


def clicks(blocks):
    """The file times (seconds) of the clicks heard in BLOCKS, from each block's own position."""
    found, last = [], -10.0
    for block in blocks:
        # (a 3×, Rubber Band reparte el tictac de 40 muestras y baja su pico a menos de 0.3; el tono no pasa de 0.05)
        for i in np.flatnonzero(np.abs(block.frames[:, 0]) > 0.15):
            t = (block.start + i * block.step) / RATE
            if t - last > 0.5:
                found.append(t)
            last = t
    return found


def test_speed_one_is_the_file_itself(audio):
    blocks = render_all(Renderer(audio))
    out = np.concatenate([b.frames for b in blocks])
    reference = audio.frames(0, audio.decoded).copy()
    reference[:FADE] *= np.linspace(0, 1, FADE, dtype=np.float32)[:, None]  # (la rampa de entrada)
    assert np.array_equal(out, reference)


@pytest.mark.parametrize("speed", [0.25, 0.5, 0.8, 1.25, 2.0, 3.0])
def test_stretch_length_and_place(audio, speed):
    renderer = Renderer(audio)
    renderer.set_speed(speed)
    blocks = render_all(renderer)
    seconds = sum(len(b.frames) for b in blocks) / RATE
    # La salida dura lo que debe, más la cola del estirador (poco).
    assert 6.0 / speed - 0.05 < seconds < 6.0 / speed + 0.25
    # Cada tictac se oye cuando la posición del bloque dice que está en el segundo justo (con 20 ms de margen:
    # a 0.25× el tictac estirado empieza a sonar un poco antes, y la línea de la posición no se mueve tan fino).
    assert clicks(blocks) == pytest.approx([1, 2, 3, 4, 5], abs=0.02)


def test_pitch_is_kept(audio):
    renderer = Renderer(audio)
    renderer.set_speed(0.5)
    out = np.concatenate([b.frames for b in render_all(renderer)])[:, 0]
    part = out[RATE // 4: RATE // 4 + 8192] * np.hanning(8192)
    spectrum = np.abs(np.fft.rfft(part))
    assert abs(np.argmax(spectrum) * RATE / 8192 - 220) < 6  # el tono sigue en 220 Hz


def test_seek_and_switch(audio):
    renderer = Renderer(audio)
    renderer.set_speed(0.5)
    renderer.seek(3.5 * RATE)
    block, seam = renderer.render()
    assert seam and block.start == 3.5 * RATE
    assert np.abs(block.frames[0]).max() == 0.0  # empieza con la rampa
    renderer.set_speed(1.0)  # de Rubber Band a la copia
    nxt, seam = renderer.render()
    assert seam and nxt.step == 1.0
    assert abs(nxt.start - (block.start + len(block.frames) * 0.5)) <= 1
    assert clicks([nxt] + render_all(renderer)) == pytest.approx([4, 5], abs=0.003)


def test_clamp_speed():
    assert clamp_speed(0.1) == 0.25 and clamp_speed(9) == 3.0 and clamp_speed(1.2345) == 1.234


def wait_for(player, output, condition, pulls=400):
    for _ in range(pulls):
        if condition():
            return True
        output.pull()
        time.sleep(0.002)
    return condition()


def test_player(audio, output):
    player = Player(output)
    player.load(audio)
    try:
        assert player.position == 0.0
        silent = output.pull()
        assert not silent.any()  # en pausa no suena nada ni se mueve
        player.play()
        assert wait_for(player, output, lambda: player.position > 0.5)
        player.pause()
        output.pull()  # (la rampa de salida)
        here = player.position
        output.pull()
        assert player.position == here
        player.seek(4.0)
        assert player.position == 4.0
        player.speed = 2.0
        player.play()
        assert wait_for(player, output, lambda: player.ended, pulls=2000)
        assert not player.playing and player.position == pytest.approx(6.0)
        player.play()  # desde el final, vuelve a empezar
        assert player.position == 0.0
        player.stop()
        assert not player.playing and player.position == 0.0
    finally:
        player.unload()


def test_seek_while_playing_has_no_click(audio, output):
    player = Player(output)
    player.load(audio)
    try:
        player.play()
        wait_for(player, output, lambda: player.position > 0.3)
        player.seek(2.5)
        heard = []
        for _ in range(40):
            heard.append(output.pull(256)[:, 0])
            time.sleep(0.002)  # (el hilo productor también corre)
        # No click: the tone (0.05 at 220 Hz) changes less than 0.002 per sample; a hard cut, up to 0.1.
        assert np.abs(np.diff(np.concatenate(heard))).max() < 0.01
        assert 2.5 <= player.position < 3.0
    finally:
        player.unload()


def test_rubberband_binding():
    """The binding to the Rubber Band Library: the R3 engine, and audio in and out."""
    from py_slowdown import rubberband
    from py_slowdown.engine import OPTIONS

    stretcher = rubberband.Stretcher(RATE, 2, OPTIONS, 2.0)
    assert stretcher.engine_version == 3
    stretcher.time_ratio = 2.0
    pad = stretcher.get_preferred_start_pad()
    assert pad > 0 and stretcher.get_start_delay() > 0
    noise = np.random.default_rng(2).uniform(-0.5, 0.5, (2, RATE)).astype(np.float32)
    stretcher.process(noise, final=True)
    out = [stretcher.retrieve(max(0, stretcher.available()))]
    while stretcher.available() > 0:
        out.append(stretcher.retrieve(stretcher.available()))
    got = np.concatenate(out, axis=1)
    assert got.shape[0] == 2 and abs(got.shape[1] - 2 * RATE) < 0.1 * RATE
    assert stretcher.available() == -1  # todo entregado


def test_rubberband_missing(monkeypatch, tmp_path):
    from py_slowdown import rubberband

    monkeypatch.setattr(rubberband, "_lib", None)
    monkeypatch.setattr(rubberband, "_candidates", lambda: [str(tmp_path / "nothing.so")])
    with pytest.raises(rubberband.RubberBandError, match="not found"):
        rubberband.library()
