"""El .slx de cada archivo: con su mismo nombre, junto a él o en una carpeta, y viaja con él."""

import os
import xml.etree.ElementTree as ET

import pytest
from conftest import tone, write

from py_slowdown import sidecar
from py_slowdown.bookmarks import Bookmark, Loop
from py_slowdown.sidecar import FileState


def state() -> FileState:
    return FileState(83.25, {"speed": 0.75, "pitch": -2.0, "formants": True, "hearing": ["left", "bass"],
                             "selection": [95.0, 103.5], "repeat": True, "countin": {"bpm": 96, "offset": 0.25, "on": True}, "volume": 120},
                     [Bookmark(21.5, "Second verse"), Bookmark(3.0, ""), Bookmark(0.8, "Downbeat", first_beat=True)],
                     [Loop(95.0, 103.5, "Bridge")])


def test_round_trip(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x" * 10)
    path = sidecar.save(audio, state())
    assert path == tmp_path / "song.slx"
    root = ET.parse(path).getroot()
    assert root.find("file").get("path") == str(audio.resolve()) and root.find("file").get("size") == "10"
    again = sidecar.load(audio)
    assert again.position == 83.25 and again.settings == state().settings
    assert [(b.time, b.label, b.first_beat) for b in again.bookmarks] == [
        (0.8, "Downbeat", True), (3.0, "", False), (21.5, "Second verse", False)]
    assert root.find("bookmarks/bookmark").get("first-beat") == "true"
    assert again.loops == [Loop(95.0, 103.5, "Bridge")]
    assert sidecar.load(tmp_path / "other.mp3") is None


def test_the_pitch_tracked(tmp_path):
    """The pitch tracked in a part (Notes > Track the pitch): its curve where it was found, and its notes."""
    import numpy as np

    from py_slowdown.pitch import Note, Track

    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x")
    times = np.array([95.0, 95.02, 95.04, 95.06])
    track = Track(95.0, 103.5, times, np.array([196.0213, 0.0, 196.5, 197.0]), [Note(95.0, 95.06, 196.0193)])
    first = state()
    first.pitch = track
    path = sidecar.save(audio, first)
    again = sidecar.read(path).pitch
    assert (again.start, again.end) == (95.0, 103.5)
    assert list(again.times) == [95.0, 95.04, 95.06] and list(again.hz) == [196.021, 196.5, 197.0]
    assert again.notes == [Note(95.0, 95.06, 196.0193)]
    # Sin altura seguida, no hay <pitch>; uno que no se entiende no se lee.
    assert sidecar.read(sidecar.save(audio, state())).pitch is None
    for broken in ('<pitch start="5" end="2">', '<pitch start="1" end="2"><curve>a b</curve>'):
        path.write_text(f'<?xml version="1.0"?><py-slowdown>{broken}</pitch></py-slowdown>')
        assert sidecar.read(path).pitch is None


def test_two_files_of_the_same_name(tmp_path):
    """song.mp3 and song.flac in one folder: the first is song.slx, the second song.flac.slx; each reads its own."""
    mp3, flac = tmp_path / "song.mp3", tmp_path / "song.flac"
    mp3.write_bytes(b"1")
    flac.write_bytes(b"2")
    assert sidecar.save(mp3, FileState(1.0)) == tmp_path / "song.slx"
    assert sidecar.save(flac, FileState(2.0)) == tmp_path / "song.flac.slx"
    assert sidecar.load(mp3).position == 1.0 and sidecar.load(flac).position == 2.0
    assert sidecar.save(mp3, FileState(5.0)) == tmp_path / "song.slx"  # (el suyo, otra vez)


def test_moved_with_its_file(tmp_path):
    """Moved to another folder with its .slx, the file finds its settings by its name."""
    old, new = tmp_path / "a", tmp_path / "b"
    old.mkdir()
    new.mkdir()
    (old / "song.mp3").write_bytes(b"x")
    sidecar.save(old / "song.mp3", state())
    for name in ("song.mp3", "song.slx"):
        os.replace(old / name, new / name)
    assert sidecar.load(new / "song.mp3").position == 83.25
    assert sidecar.save(new / "song.mp3", FileState(9.0)) == new / "song.slx"  # (y ahora nombra la ruta nueva)
    assert ET.parse(new / "song.slx").getroot().find("file").get("path") == str((new / "song.mp3").resolve())


def test_in_a_folder(tmp_path):
    """In a folder of their own: two song.mp3 of different folders do not take each other's .slx."""
    keep = tmp_path / "settings"
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "song.mp3").write_bytes(b"1")
    (two / "song.mp3").write_bytes(b"2")
    assert sidecar.save(one / "song.mp3", FileState(1.0), keep) == keep / "song.slx"
    second = sidecar.save(two / "song.mp3", FileState(2.0), keep)
    assert second == keep / "song.mp3.slx"
    assert sidecar.load(one / "song.mp3", keep).position == 1.0 and sidecar.load(two / "song.mp3", keep).position == 2.0
    assert not (one / "song.slx").exists()


def test_damaged_or_foreign_xml(tmp_path):
    """A file of the same name that is not ours (or is damaged) is left alone, and ours gets another name."""
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x")
    (tmp_path / "song.slx").write_text("<score><part/></score>")
    (tmp_path / "song.xml").write_text("<score><part/></score>")  # (un XML de otro programa, de 1.2.0 o no)
    assert sidecar.load(audio) is None
    assert sidecar.save(audio, FileState(4.0)) == tmp_path / "song.mp3.slx"
    assert (tmp_path / "song.slx").read_text() == "<score><part/></score>"
    assert (tmp_path / "song.xml").read_text() == "<score><part/></score>"


def test_the_xml_of_1_2_0(tmp_path):
    """The .xml files of py-slowdown 1.2.0 are still read; once a file's .slx is written, its .xml goes, and not
    another file's."""
    mp3, flac = tmp_path / "song.mp3", tmp_path / "song.flac"
    mp3.write_bytes(b"x")
    flac.write_bytes(b"y")
    # Como los dejó 1.2.0: song.xml de song.flac, song.mp3.xml de song.mp3.
    os.replace(sidecar.save(flac, FileState(7.0)), tmp_path / "song.xml")
    os.replace(sidecar.save(mp3, state()), tmp_path / "song.mp3.xml")
    assert sidecar.load(mp3).position == 83.25 and sidecar.load(flac).position == 7.0
    assert sidecar.save(mp3, FileState(9.0)) == tmp_path / "song.slx"
    assert not (tmp_path / "song.mp3.xml").exists() and (tmp_path / "song.xml").is_file()
    assert sidecar.load(mp3).position == 9.0 and sidecar.load(flac).position == 7.0
    assert sidecar.save(flac, FileState(8.0)) == tmp_path / "song.flac.slx"
    assert not (tmp_path / "song.xml").exists() and sidecar.load(flac).position == 8.0


def test_owner(tmp_path):
    """The recording a .slx is of: where it says, or beside it if moved with it; None if neither, or not ours."""
    folder, moved = tmp_path / "a", tmp_path / "b"
    folder.mkdir()
    moved.mkdir()
    (folder / "song.mp3").write_bytes(b"x")
    slx = sidecar.save(folder / "song.mp3", state())
    assert sidecar.owner(slx) == (folder / "song.mp3").resolve()
    for name in ("song.mp3", "song.slx"):
        os.replace(folder / name, moved / name)
    assert sidecar.owner(moved / "song.slx") == moved / "song.mp3"
    (moved / "song.mp3").unlink()
    assert sidecar.owner(moved / "song.slx") is None
    (moved / "other.slx").write_text("<score/>")
    assert sidecar.owner(moved / "other.slx") is None and sidecar.read(moved / "other.slx") is None



def test_owners_both_places(tmp_path, monkeypatch, output):
    """A .slx copied to another folder with a recording of the same name, while the one it names is still where it
    says: both are offered, and the window asks which to open (Cancel opens nothing); the same file by two paths,
    a link or the same folder, is offered once and opened without asking."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player
    from py_slowdown.window import Window

    folder, copy = tmp_path / "a", tmp_path / "b"
    folder.mkdir()
    copy.mkdir()
    write(folder / "song.wav", tone(2.0))
    slx = sidecar.save(folder / "song.wav", state())
    assert sidecar.owners(slx) == [folder / "song.wav"]
    (copy / "song.slx").write_bytes(slx.read_bytes())
    write(copy / "song.wav", tone(2.0))
    assert sidecar.owners(copy / "song.slx") == [copy / "song.wav", (folder / "song.wav").resolve()]
    assert sidecar.owner(copy / "song.slx") == (folder / "song.wav").resolve()  # (sin preguntar: la de la ruta)
    link = tmp_path / "link"
    link.symlink_to(folder)
    assert sidecar.owners(link / "song.slx") == [link / "song.wav"]

    QApplication.instance() or QApplication([])
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    w = Window(player=Player(output), store=Store(tmp_path / "b.json"),
               settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w.a_ask_save.setChecked(False)
    asked = []
    answers = [None, copy / "song.wav", (folder / "song.wav").resolve()]
    monkeypatch.setattr(Window, "_choose_recording", lambda self, slx, choices: asked.append(choices) or answers.pop(0))
    assert not w.open_file(copy / "song.slx") and w.audio is None
    assert w.open_file(copy / "song.slx") and w.audio.path == (copy / "song.wav").resolve()
    assert w.open_file(copy / "song.slx") and w.audio.path == (folder / "song.wav").resolve()
    assert len(asked) == 3 and asked[0] == sidecar.owners(copy / "song.slx")
    assert w.open_file(link / "song.slx") and len(asked) == 3  # (un solo archivo: no pregunta)
    w.close_file()
    w.close()

def test_the_window_keeps_it(tmp_path, monkeypatch, output):
    """Closing a file writes its .slx beside it; opened again, even with bookmarks.json gone, all comes back; in a
    folder chosen, the .slx goes there; Not saved writes none. Opening the .slx opens its recording."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player
    from py_slowdown.window import Window

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    music = tmp_path / "music"
    music.mkdir()
    song = music / "song.wav"
    write(song, tone(4.0))

    def window(store_name: str) -> Window:
        settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
        return Window(player=Player(output), store=Store(tmp_path / store_name), settings=settings)

    w = window("one.json")
    assert w.a_sidecar["beside"].isChecked()
    w.a_ask_save.setChecked(False)  # (cada cambio al .slx en el momento)
    w.open_file(song)
    w.audio.wait(10)
    w.set_speed(0.7)
    w.add_bookmark_at(1.5)
    # (cada marcador va al .slx en el momento, no solo al cerrar)
    marks = ET.parse(music / "song.slx").getroot().findall("bookmarks/bookmark")
    assert [m.get("time") for m in marks] == ["1.5"]
    w.set_selection((1.0, 2.0))
    w.save_loop()
    w._loop_renamed(0, "Lick")
    assert ET.parse(music / "song.slx").getroot().find("loops/loop").text == "Lick"
    w.seek(2.5)
    w.close_file()
    xml = music / "song.slx"
    assert xml.is_file() and ET.parse(xml).getroot().find("playback").get("speed") == "0.7"
    w.close()

    w = window("two.json")  # (otro bookmarks.json, vacío: lo que vuelve es del .slx)
    w.open_file(song)
    w.audio.wait(10)
    w._tick()
    app.processEvents()
    assert w.player.speed == 0.7 and [b.time for b in w.bookmarks] == [1.5] and [x.label for x in w.loops] == ["Lick"]
    assert abs(w.player.position - 2.5) < 0.05 and w.selection == (1.0, 2.0)
    w.close_file()
    w.close()

    w = window("three.json")  # (abrir el .slx abre su grabación, como el .slx dice)
    assert w.open_file(xml) and w.audio.path == song.resolve()
    w.audio.wait(10)
    w._tick()
    app.processEvents()
    assert w.player.speed == 0.7 and [b.time for b in w.bookmarks] == [1.5]
    (music / "lost.slx").write_text("<score/>")
    warnings = []
    monkeypatch.setattr("py_slowdown.window.QMessageBox.warning", lambda *args: warnings.append(args[2]))
    assert not w.open_file(music / "lost.slx") and "lost.slx" in warnings[0] and w.audio is not None
    keep = tmp_path / "kept"
    monkeypatch.setattr("py_slowdown.window.QFileDialog.getExistingDirectory", lambda *args: str(keep))
    w.a_sidecar["folder"].trigger()
    assert w.a_sidecar["folder"].isChecked() and str(keep) in w.a_sidecar["folder"].text()
    w.close_file()
    assert (keep / "song.slx").is_file()
    w.a_sidecar["off"].trigger()
    xml.unlink()
    (keep / "song.slx").unlink()
    w.open_file(song)
    w.close_file()
    assert not xml.exists() and not (keep / "song.slx").exists()
    # Archivo > Guardar el .slx (Ctrl+S): ahora, sin cerrar; con «No se guardan», junto a la grabación
    w.open_file(song)
    w.audio.wait(10)
    w.set_speed(0.8)
    assert w.a_save_slx.isEnabled() and w.a_save_slx.shortcut().toString() == "Ctrl+S"
    w.a_save_slx.trigger()
    assert ET.parse(xml).getroot().find("playback").get("speed") == "0.8"
    assert str(xml) in w.statusBar().currentMessage() and w.audio is not None
    w.close_file()
    assert not w.a_save_slx.isEnabled()
    w.close()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permissions of POSIX, not as root")
def test_a_folder_that_cannot_be_written(tmp_path, monkeypatch, output):
    """Where the .slx cannot be written, the status bar says so, and the rest goes on (bookmarks.json keeps it)."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player
    from py_slowdown.window import Window

    QApplication.instance() or QApplication([])
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    locked = tmp_path / "locked"
    locked.mkdir()
    song = locked / "song.wav"
    write(song, tone(2.0))
    locked.chmod(0o555)
    try:
        w = Window(player=Player(output), store=Store(tmp_path / "b.json"),
                   settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
        w.open_file(song)
        w.audio.wait(10)
        w.set_speed(0.6)
        messages = []
        monkeypatch.setattr(w.statusBar(), "showMessage", lambda text, *args: messages.append(text))
        w.close_file()
        assert not (locked / "song.slx").exists() and any("song.wav" in m for m in messages)
        assert w.store.settings(song)["speed"] == 0.6
        w.close()
    finally:
        locked.chmod(0o755)
