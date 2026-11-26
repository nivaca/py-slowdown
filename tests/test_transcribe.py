"""Los archivos de Transcribe! (.xsc): lo que se lee de ellos, y cómo los abre la ventana."""

import pytest

from py_slowdown import transcribe

XSC = """\
Transcribe!,6089,Seventh String Software
Transcribe!,GTK,9,60,7,S,0

SectionStart,Main
SaveDate,2026-07-28 20:06
SoundFileName,{name},Nix,/nowhere/{name}
Loops,0:0,0:0
SectionEnd,Main

SectionStart,View0
FX_Tuning,1,0,0,0,-32,0,60,50,0,440
FX_Transposition,1,1,0,0,0
FX_Speed,1,0,75000,0
SelectionLeft,48000,0:00:01.000000
SelectionRight,96000,0:00:02.500000
SectionEnd,View0

SectionStart,Markers
Howmany,7
S,7350,1,,0,0:00:00.500000
B,45829,1,,0,0:00:01.000000
M,86471,1,,0,0:00:01.500000
S,118105,0,Head\\C again,0,0:00:02.000000
B,147432,1,,0,0:00:02.500000
M,176400,0,Coda,0,0:00:03.000000
S,204503,1,,0,0:00:04.000000
SectionEnd,Markers

SectionStart,Loops
Howmany,3
MostRecent,-1
L,1,0,0,0,The bridge,White,,0:00:01.000000,0:00:03.000000
L,2,0,0,0,,White,,0:00:00.000000,0:00:00.000000
L,3,0,0,0,,Red,,0:00:04.000000,0:00:05.250000
SectionEnd,Loops
"""


def make(tmp_path, audio, text=XSC):
    path = tmp_path / "song.xsc"
    path.write_text(text.format(name=audio.name), encoding="utf-8")
    return path


def test_read(tmp_path, wav):
    audio, state = transcribe.read(make(tmp_path, wav))
    assert audio == wav  # (no está en su ruta: el del mismo nombre junto al .xsc)
    assert state.settings["speed"] == 0.75 and state.settings["pitch"] == -0.32
    assert state.settings["selection"] == [1.0, 2.5] and state.position == 1.0
    # Las secciones (A, B… las que no tienen nombre), el compás con nombre, y el primer pulso
    assert [(m.time, m.label, m.first_beat) for m in state.bookmarks] == [
        (0.5, "A", False), (1.0, "First beat", True), (2.0, "Head, again", False), (3.0, "Coda", False),
        (4.0, "C", False)]
    # Pulsos y compases cada 0.5 s: 120 BPM, con la cuenta apagada
    assert state.settings["countin"] == {"bpm": 120, "offset": 0.0, "on": False}
    assert [(x.start, x.end, x.label) for x in state.loops] == [(1.0, 3.0, "The bridge"), (4.0, 5.25, "")]


def test_read_little(tmp_path, wav):
    # Sin marcadores ni bucles, a 1×, sin afinar, sin selección: solo la posición
    text = XSC.split("SectionStart,Markers")[0].replace("75000", "100000").replace(",-32,", ",0,")
    text = text.replace("0:00:02.500000", "0:00:01.000000")
    audio, state = transcribe.read(make(tmp_path, wav, text))
    assert state.settings == {} and state.position == 1.0 and not state.bookmarks and not state.loops


def test_not_transcribe(tmp_path, wav):
    path = tmp_path / "other.xsc"
    path.write_text("Something else\n", encoding="utf-8")
    with pytest.raises(transcribe.TranscribeError):
        transcribe.read(path)
    with pytest.raises(transcribe.TranscribeError, match="missing.wav"):
        transcribe.read(make(tmp_path, tmp_path / "missing.wav"))


def test_seconds():
    assert transcribe.seconds("1:02:03.5") == 3723.5 and transcribe.seconds("White") is None


def test_open_in_the_window(tmp_path, wav, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from py_slowdown import sidecar
    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player
    from py_slowdown.window import Window

    from conftest import FakeOutput

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("py_slowdown.window.Output", FakeOutput)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = Window(player=Player(FakeOutput()), store=Store(tmp_path / "bookmarks.json"), settings=settings)
    try:
        assert window.open_file(make(tmp_path, wav))
        window.audio.wait(10)
        window._tick()
        app.processEvents()
        assert window.audio.path == wav and window.player.speed == 0.75 and window.player.pitch == -0.32
        assert window.selection == (1.0, 2.5) and len(window.bookmarks) == 5 and len(window.loops) == 2
        assert window.first_beat().time == 1.0 and window.count.bpm == 120
        assert window._changed()  # (lo importado es un cambio: se pregunta al cerrar)
        assert window.close_file()  # (y se guarda: la respuesta de las pruebas)
        kept = sidecar.load(wav)
        assert kept is not None and len(kept.bookmarks) == 5 and kept.settings["speed"] == 0.75
    finally:
        window.close()
