import itertools
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


def test_count_in_block():
    from py_slowdown.engine import COUNT_LEAD, count_in

    block = count_in(RATE, 2, 4, 120)
    lead, beat, beats = block.count
    assert (beat, beats) == (RATE // 2, 4) and lead == int(COUNT_LEAD * RATE)
    assert len(block.frames) == lead + 4 * beat and block.step == 0.0
    loud = np.abs(block.frames[:, 0])
    starts = [lead + n * beat for n in range(4)]
    assert all(loud[s:s + 200].max() > 0.2 for s in starts)  # a click at each beat
    assert loud[starts[0]:starts[0] + 400].max() > loud[starts[1]:starts[1] + 400].max()
    # Antes del primer golpe, y entre los golpes, un soplo casi inaudible, nunca silencio exacto (para los
    # auriculares Bluetooth que se silencian mientras no les llega nada)
    lead_part = loud[: lead - 10]
    assert 0 < lead_part.max() < 0.003 and (lead_part > 0).mean() > 0.99
    between = loud[starts[0] + 4000: starts[1] - 10]
    assert 0 < between.max() < 0.002
    assert count_in(RATE, 1, 99, 1000).count[2] == 16  # (limits)


def test_player_counts_in(audio, output):
    player = Player(output)
    player.load(audio)
    try:
        player.seek(2.0)
        wait_for(player, output, lambda: player._queued > 0)
        player.play(beats=2, bpm=240)  # two beats of a quarter of a second each, after the lead
        assert player.counting() == (0, 2)  # (antes del primer golpe)
        heard, beats = [], []
        for _ in range(60):  # about 0.7 s: the lead and the two beats; the position stays
            heard.append(output.pull(512))
            beats.append(player.counting())
            time.sleep(0.001)
        assert [b for b in dict.fromkeys(beats) if b] == [(0, 2), (1, 2), (2, 2)] and player.position == 2.0
        assert np.abs(np.concatenate(heard)).max() > 0.3  # the clicks are heard
        assert wait_for(player, output, lambda: player.position > 2.05)  # then the recording
        assert player.counting() is None
        # Una pausa en medio de la cuenta, y otra vez a tocar: una cuenta nueva, no dos
        player.pause()
        output.pull()
        player.play(beats=3, bpm=100)
        assert sum(1 for b in player._queue if b.count) == 1
        player.play()  # (sin cuenta: la que había se quita)
        assert not any(b.count for b in player._queue)
    finally:
        player.unload()


def loop_blocks(renderer, seconds):
    blocks, total = [], 0
    while total < seconds * RATE:
        block, _seam = renderer.render()
        assert block is not None
        if len(block.frames):
            blocks.append(block)
            total += len(block.frames)
    return blocks


def test_loop_at_normal_speed(audio):
    """The selection is repeated sample after sample, its end running into its start through a short fade."""
    renderer = Renderer(audio)
    a, b = int(1.5 * RATE), int(2.5 * RATE)
    renderer.set_loop((a, b))
    renderer.seek(a)
    blocks = loop_blocks(renderer, 3.2)
    out = np.concatenate([x.frames for x in blocks])[:, 0]
    starts = [x.start for x in blocks]
    assert all(a <= s < b for s in starts)
    # Tres vueltas y algo: cada vuelta dura lo que la selección; la segunda empieza otra vez en a
    one = b - a
    source = audio.frames(0, audio.decoded)[:, 0]
    assert np.allclose(out[FADE + 10:one - 1000], source[a + FADE + 10:b - 1000], atol=1e-6)
    assert np.allclose(out[one + 10:2 * one - 1000], source[a + 10:b - 1000], atol=1e-6)
    # Sin chasquidos en las costuras: el tono cambia poco de una muestra a otra, también allí
    for seam in (one, 2 * one, 3 * one):
        assert np.abs(np.diff(out[seam - 600:seam + 600])).max() < 0.01


@pytest.mark.parametrize("speed", [0.5, 1.5])
def test_loop_while_stretching(audio, speed):
    renderer = Renderer(audio)
    renderer.set_speed(speed)
    a, b = int(1.5 * RATE), int(2.5 * RATE)
    renderer.set_loop((a, b))
    renderer.seek(a)
    blocks = loop_blocks(renderer, 3 * 1.0 / speed)
    assert all(a <= x.start < b for x in blocks)
    # El tictac de 2.0 s se oye una vez por vuelta, en su lugar (contados por el tiempo de salida: en el del
    # archivo, todos están en el mismo punto)
    found, last, out = [], -RATE, 0
    for block in blocks:
        for i in np.flatnonzero(np.abs(block.frames[:, 0]) > 0.15):
            if out + i - last > 0.3 * RATE:
                found.append((block.start + i * block.step) / RATE)
            last = out + i
        out += len(block.frames)
    assert len(found) >= 2 and found == pytest.approx([2.0] * len(found), abs=0.02)
    # Las vueltas duran lo que deben: la selección estirada
    wraps = [i for i in range(1, len(blocks)) if blocks[i].start < blocks[i - 1].start]
    lengths = [sum(len(x.frames) for x in blocks[i:j]) for i, j in itertools.pairwise(wraps)]
    assert lengths and all(abs(n - (b - a) / speed) < 0.02 * RATE for n in lengths)


def test_player_loop(audio, output):
    player = Player(output)
    player.load(audio)
    try:
        player.set_loop((4.0, 3.0))  # (en cualquier orden)
        assert player.loop == (3.0, 4.0) and player.position == 3.0  # fuera de ella: va a su principio
        player.set_loop((3.0, 3.05))  # demasiado corta: no se repite
        assert player.loop is None
        player.set_loop((3.0, 4.0))
        player.play()
        seen = []
        for _ in range(600):  # unos 7 s de sonido: más de seis vueltas
            output.pull(512)
            seen.append(player.position)
            time.sleep(0.001)
        assert min(seen) >= 3.0 - 1e-6 and max(seen) < 4.0 and player.playing
        player.set_loop(None)
        assert player.loop is None
    finally:
        player.unload()


def dominant(frames: np.ndarray, speed: float = 1.0) -> float:
    """The main frequency of FRAMES, measured between two clicks of the test file (at 1.1 s of it, as heard at
    SPEED): a click inside the window spreads over the whole spectrum."""
    start = int(1.1 / speed * RATE)
    part = frames[start: start + 16384, 0] * np.hanning(16384)
    spectrum = np.log(np.abs(np.fft.rfft(part)) + 1e-12)
    k = int(np.argmax(spectrum))
    # Entre dos bins de la FFT (2,7 Hz): la parábola que pasa por el pico y sus vecinos
    a, b, c = spectrum[k - 1], spectrum[k], spectrum[k + 1]
    return float((k + 0.5 * (a - c) / (a - 2 * b + c)) * RATE / 16384)


@pytest.mark.parametrize(("semitones", "speed"), [(12, 1.0), (-5, 1.0), (7, 0.75), (-12, 1.5)])
def test_pitch_shift(audio, semitones, speed):
    from py_slowdown.engine import pitch_scale

    renderer = Renderer(audio)
    renderer.set_speed(speed)
    renderer.set_pitch(semitones)
    assert not renderer.plain
    blocks = render_all(renderer)
    out = np.concatenate([b.frames for b in blocks])
    # El tono de 220 Hz sube o baja lo pedido (a un cuarto de semitono: entre 6 y 12 Hz, según la nota)
    assert dominant(out, speed) == pytest.approx(220 * pitch_scale(semitones), rel=0.007)
    # La duración la decide la velocidad, no la altura; y cada tictac sigue en su lugar
    assert 6.0 / speed - 0.05 < len(out) / RATE < 6.0 / speed + 0.25
    assert clicks(blocks) == pytest.approx([1, 2, 3, 4, 5], abs=0.02)


def test_pitch_back_to_zero_is_the_file_itself(audio):
    renderer = Renderer(audio)
    renderer.set_pitch(3)
    renderer.render()
    renderer.set_pitch(0)
    assert renderer.plain
    block, seam = renderer.render()
    assert seam and block.step == 1.0  # (de Rubber Band a la copia, con su rampa)
    rest = render_all(renderer)
    start = round(rest[0].start)
    out = np.concatenate([b.frames for b in rest])
    assert np.array_equal(out, audio.frames(start, start + len(out)))


def test_player_pitch(audio, output):
    from py_slowdown.engine import clamp_pitch

    assert clamp_pitch(30) == 12 and clamp_pitch(-30) == -12 and clamp_pitch(0.333) == 0.33
    player = Player(output)
    player.load(audio)
    try:
        player.pitch = -2
        assert player.pitch == -2
        player.play()
        assert wait_for(player, output, lambda: player.position > 0.5)
        assert 0.4 < player.position < 1.5  # (la altura no cambia el paso del tiempo)
    finally:
        player.unload()


def test_pitch_changes_while_playing_without_a_click(audio):
    """With Rubber Band's option for pitch that changes as it plays, moving it a few semitones up and down in
    the middle makes no jump in the sound."""
    renderer = Renderer(audio)
    renderer.set_speed(0.75)
    renderer.seek(1.03 * RATE)
    out = []
    # Seis alturas, nueve bloques cada una (algo más de 0,2 s): todo entre dos tictacs del archivo, sin saltos
    for semitones in (0, 3, 5, -2, 0, 4):
        renderer.set_pitch(semitones)
        for _ in range(9):
            block, _seam = renderer.render()
            out.append(block.frames[:, 0])
    assert renderer.pos < 1.99 * RATE
    heard = np.concatenate(out)[2000:]  # (sin la rampa de entrada)
    # El tono (0.05 a 220 Hz, o a 280 Hz a +4) cambia menos de 0.003 por muestra; un salto, mucho más
    jumps = np.abs(np.diff(heard))
    assert jumps.max() < 0.01
