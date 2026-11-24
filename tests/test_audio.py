import shutil
import wave

import numpy as np
import pytest
from conftest import RATE, tone, write

from py_slowdown import audio as audio_module
from py_slowdown.audio import BUCKET, Audio, AudioError, Peaks


def decoders():
    """The decoders there are here: PyAV if installed, the ffmpeg program if installed."""
    found = []
    try:
        import av  # noqa: F401
        found.append("av")
    except ImportError:
        pass
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        found.append("ffmpeg")
    return found


@pytest.fixture(params=decoders())
def decoder(request, monkeypatch):
    monkeypatch.setenv("PY_SLOWDOWN_DECODER", request.param)
    return request.param


@pytest.mark.parametrize("suffix", [".wav", ".flac", ".mp3", ".m4a", ".opus"])
def test_formats(tmp_path, suffix, decoder):
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


def test_samples_exact(wav, decoder):
    audio = Audio(wav)
    audio.wait(10)
    expected = tone(6.0)
    got = audio.frames(0, audio.decoded)
    assert got.shape == expected.shape
    assert np.abs(got - expected).max() < 1e-4  # (16 bits)
    audio.close()


def test_kept_in_16_bits(wav, decoder):
    """The decoded samples are kept in 16 bits (half the space of float32): those of a 16-bit file exactly,
    and what goes past full scale is clipped."""
    audio = Audio(wav)
    audio.wait(10)
    assert audio._data.dtype == np.int16
    with wave.open(str(wav)) as source:  # (las muestras que el WAV guarda, en 16 bits)
        raw = np.frombuffer(source.readframes(source.getnframes()), "<i2").reshape(-1, source.getnchannels())
    assert np.array_equal(audio._data[:audio.decoded], raw)
    assert np.array_equal(audio.frames(0, audio.decoded), raw / np.float32(32768))
    assert audio.frames(0, 10).dtype == np.float32
    audio.close()
    loud = Audio(wav)
    loud.wait(10)
    before = loud.decoded
    loud._take(np.array([[1.5, -1.5], [0.25, -1.0]], np.float32))
    assert loud.frames(before, before + 2).tolist() == [[32767 / 32768, -1.0], [0.25, -1.0]]
    loud.close()


def test_peaks_of_16_bit_samples():
    """The readers give 16-bit samples: their peaks, found in the integers, are those of the same samples as floats."""
    rng = np.random.default_rng(5)
    ints = rng.integers(-32768, 32768, (BUCKET * 7 + 30, 2)).astype(np.int16)
    floats = ints.astype(np.float32) / 32768
    a, b = Peaks(10), Peaks(10)
    for start in range(0, len(ints), 500):
        a.add(ints[start:start + 500])
        b.add(floats[start:start + 500])
    a.finish()
    b.finish()
    assert a.count == b.count == 8
    assert np.array_equal(a.lo[:8], b.lo[:8]) and np.array_equal(a.hi[:8], b.hi[:8])


def test_mono_and_resampled(tmp_path, decoder):
    path = tmp_path / "mono.flac"
    write(path, tone(2.0, channels=1))
    audio = Audio(path, rate=48000)
    audio.wait(10)
    assert audio.channels == 1 and audio.rate == 48000
    assert abs(audio.duration - 2.0) < 0.01
    audio.close()


def test_longer_than_announced(wav, monkeypatch, decoder):
    # Un archivo que anuncia menos de lo que dura: el archivo temporal crece y nada se pierde.
    monkeypatch.setattr(Audio, "_announced_seconds", lambda self: 0.5)
    audio = Audio(wav)
    audio.wait(10)
    assert audio.decoded == 6 * RATE
    assert np.abs(audio.frames(0, audio.decoded) - tone(6.0)).max() < 1e-4
    audio.close()


def test_not_audio(tmp_path, decoder):
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


def test_decoder_choice(monkeypatch):
    monkeypatch.setenv("PY_SLOWDOWN_DECODER", "ffmpeg")
    assert audio_module.decoder() == "ffmpeg"
    monkeypatch.delenv("PY_SLOWDOWN_DECODER")
    assert audio_module.decoder() in ("av", "ffmpeg")


def test_damaged_halfway(tmp_path, decoder):
    """A file cut short: what could be read stays, and the error is told."""
    path = tmp_path / "cut.flac"
    write(path, tone(4.0))
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    audio = Audio(path)
    assert audio.wait(10)
    assert 0.5 < audio.duration < 3.5
    audio.close()
