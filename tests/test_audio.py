import numpy as np
import pytest
from conftest import RATE, tone, write

from py_slowdown import audio as audio_module
from py_slowdown.audio import BUCKET, Audio, AudioError, Peaks


@pytest.mark.parametrize("suffix", [".wav", ".flac", ".mp3", ".m4a", ".opus"])
def test_formats(tmp_path, suffix):
    path = tmp_path / f"a{suffix}"
    rate = 48000 if suffix == ".opus" else RATE  # Opus solo usa 48 kHz
    write(path, tone(3.0, rate=rate), rate=rate)
    audio = Audio(path)
    try:
        assert audio.wait(20)
        assert audio.rate == rate and audio.channels == 2
        # Los códecs con pérdida agregan algo de relleno al principio o al final.
        assert abs(audio.duration - 3.0) < 0.1
        assert audio.peaks.count == -(-audio.decoded // BUCKET)
        assert not audio.error
    finally:
        audio.close()


def test_samples_exact(wav):
    audio = Audio(wav)
    audio.wait(10)
    expected = tone(6.0)
    got = audio.frames(0, audio.decoded)
    assert got.shape == expected.shape
    assert np.abs(got - expected).max() < 1e-4  # (16 bits)
    audio.close()


def test_mono_and_resampled(tmp_path):
    path = tmp_path / "mono.flac"
    write(path, tone(2.0, channels=1))
    audio = Audio(path, rate=48000)
    audio.wait(10)
    assert audio.channels == 1 and audio.rate == 48000
    assert abs(audio.duration - 2.0) < 0.01
    audio.close()


def test_longer_than_announced(wav, monkeypatch):
    # Un archivo que anuncia menos de lo que dura: el archivo temporal crece y nada se pierde.
    monkeypatch.setattr(Audio, "_announced_seconds", lambda self: 0.5)
    audio = Audio(wav)
    audio.wait(10)
    assert audio.decoded == 6 * RATE
    assert np.abs(audio.frames(0, audio.decoded) - tone(6.0)).max() < 1e-4
    audio.close()


def test_not_audio(tmp_path):
    path = tmp_path / "text.mp3"
    path.write_text("not audio at all")
    with pytest.raises(AudioError):
        Audio(path)


def test_samples_live_in_cache(wav):
    audio = Audio(wav)
    audio.wait(10)
    # El archivo temporal no tiene nombre: nada queda en la carpeta, ni antes ni después de cerrar.
    assert list(audio_module.cache_dir().iterdir()) == []
    audio.close()


def test_peaks_in_pieces():
    rng = np.random.default_rng(1)
    data = rng.uniform(-1, 1, (BUCKET * 10 + 17, 2)).astype(np.float32)
    whole, pieces = Peaks(4), Peaks(4)
    whole.add(data)
    whole.finish()
    for start in range(0, len(data), 333):
        pieces.add(data[start:start + 333])
    pieces.finish()
    assert whole.count == pieces.count == 11
    assert np.array_equal(whole.lo[:11], pieces.lo[:11])
    assert np.array_equal(whole.hi[:11], pieces.hi[:11])
    assert whole.hi[0] == data[:BUCKET].max()
