import numpy as np
import pytest

from py_slowdown import notes
from py_slowdown.engine import Player
from py_slowdown.notes import Tone, ToneSettings

RATE = 44100


def sound(*midis, seconds=1.5, amps=(1.0, 0.5, 0.3, 0.2, 0.1), cents=0.0, a4=notes.A4):
    t = np.arange(int(RATE * seconds)) / RATE
    wave = np.zeros(len(t))
    for midi in midis:
        f = notes.frequency(midi + cents / 100, a4)
        wave += sum(a * np.sin(2 * np.pi * f * h * t) for h, a in enumerate(amps, 1))
    wave /= np.abs(wave).max()
    return np.stack([wave, wave], axis=1).astype(np.float32) * 0.5


def test_names_and_frequencies():
    assert notes.name(60) == "C4" and notes.name(69) == "A4" and notes.name(46) == "B♭2"
    assert notes.frequency(69) == 440.0 and notes.frequency(57) == pytest.approx(220.0)
    assert notes.frequency(69, 442.0) == 442.0
    midi, cents = notes.nearest(261.63 * 2 ** (12 / 1200))
    assert midi == 60 and cents == pytest.approx(12, abs=0.1)
    assert notes.cents_text(-12.4) == "−12 ¢" and notes.cents_text(2) == "" and notes.cents_text(7.6) == "+8 ¢"


@pytest.mark.parametrize("midi", [28, 40, 45, 60, 72, 84])
def test_finds_the_note(midi):
    found = notes.find(sound(midi), RATE)
    assert found.midi == midi and abs(found.cents) < 2 and found.others == []


def test_cents_and_tuning():
    found = notes.find(sound(57, cents=-20), RATE)
    assert found.midi == 57 and found.cents == pytest.approx(-20, abs=2)
    assert found.text() == "A3 −20 ¢"
    # (afinado a 415 Hz, la misma nota es un A justo; con 440, casi un semitono más bajo)
    baroque = sound(57, a4=415.0)
    assert notes.find(baroque, RATE, a4=415.0).text() == "A3"
    assert notes.find(baroque, RATE).midi == 56


def test_a_chord_and_noise():
    found = notes.find(sound(60, 64, 67), RATE)
    assert found.midi == 60 and set(found.others) == {64, 67}
    noisy = sound(55) + np.random.default_rng(1).normal(0, 0.3, (int(RATE * 1.5), 2)).astype(np.float32)
    assert notes.find(noisy, RATE).midi == 55


def test_nothing_to_find():
    assert notes.find(np.zeros((RATE, 2), np.float32), RATE) is None
    assert notes.find(sound(60, seconds=0.05), RATE) is None  # (muy corto)


def test_long_parts_are_quick():
    import time

    long = np.tile(sound(50, seconds=2), (60, 1))  # dos minutos
    start = time.perf_counter()
    assert notes.find(long, RATE).midi == 50
    assert time.perf_counter() - start < 2.0


def test_tone_partials():
    settings = ToneSettings(midi=57, chord="major", timbre="pure", volume=100, on=True)
    hz, amps = settings.partials(RATE)
    assert hz == pytest.approx([220.0, notes.frequency(61), notes.frequency(64)])
    assert amps.sum() == pytest.approx(notes.LOUDEST)
    off = ToneSettings(on=False).partials(RATE)
    assert not off[1].any()


def test_tone_sounds_its_note_without_clicks():
    tone = Tone(RATE)
    assert tone.silent
    tone.set(ToneSettings(midi=69, timbre="pure", volume=100, on=True))
    wave = np.concatenate([tone.render(512) for _ in range(200)])
    spectrum = np.abs(np.fft.rfft(wave[RATE // 2:RATE // 2 + 32768]))
    assert np.argmax(spectrum) * RATE / 32768 == pytest.approx(440, abs=2)
    assert np.abs(wave).max() <= notes.LOUDEST + 1e-6
    # Otra nota, otro volumen, apagado: sin saltos entre una muestra y la siguiente
    tone.set(ToneSettings(midi=64, timbre="pure", volume=100, on=True))
    more = [tone.render(512) for _ in range(20)]
    tone.set(ToneSettings(midi=64, timbre="pure", volume=30, on=True))
    more += [tone.render(512) for _ in range(20)]
    tone.set(ToneSettings(midi=64, timbre="pure", volume=30, on=False))
    more += [tone.render(512) for _ in range(5)]
    whole = np.concatenate([wave, *more])
    step = 2 * np.pi * 440 / RATE * notes.LOUDEST  # (lo más que cambia, de una muestra a la otra, el La a todo volumen)
    assert np.abs(np.diff(whole)).max() < step * 1.05
    assert tone.silent and not np.any(tone.render(512))


def test_player_tone_sounds_while_paused(wav, output):
    from py_slowdown.audio import Audio

    audio = Audio(wav)
    audio.wait(10)
    player = Player(output)
    player.load(audio)
    try:
        assert not output.pull(512).any()  # (en pausa y sin tono: nada)
        player.set_tone(ToneSettings(midi=69, timbre="pure", volume=100, on=True))
        for _ in range(4):
            out = output.pull(512)
        assert np.abs(out).max() > 0.1 and np.allclose(out[:, 0], out[:, 1])
        player.set_tone(ToneSettings(midi=69, on=False))
        output.pull(512)
        assert not output.pull(512).any()
        # (lo elegido antes de abrir un archivo suena al abrirlo)
        player.set_tone(ToneSettings(midi=60, on=True))
        player.load(audio)
        output.pull(512)
        assert np.abs(output.pull(512)).max() > 0.01
    finally:
        player.unload()
        audio.close()
