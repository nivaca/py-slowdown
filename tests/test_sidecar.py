"""El XML de cada archivo: con su mismo nombre, junto a él o en una carpeta, y viaja con él."""

import os
import xml.etree.ElementTree as ET

import pytest
from conftest import tone, write

from py_slowdown import sidecar
from py_slowdown.bookmarks import Bookmark, Loop
from py_slowdown.sidecar import FileState


def state() -> FileState:
    return FileState(83.25, {"speed": 0.75, "pitch": -2.0, "formants": True, "hearing": ["left", "bass"],
                             "selection": [95.0, 103.5], "repeat": True, "countin": {"bpm": 96, "offset": 0.25}},
                     [Bookmark(21.5, "Second verse"), Bookmark(3.0, "")], [Loop(95.0, 103.5, "Bridge")])


def test_round_trip(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x" * 10)
    path = sidecar.save(audio, state())
    assert path == tmp_path / "song.xml"
    root = ET.parse(path).getroot()
    assert root.find("file").get("path") == str(audio.resolve()) and root.find("file").get("size") == "10"
    again = sidecar.load(audio)
    assert again.position == 83.25 and again.settings == state().settings
    assert [(b.time, b.label) for b in again.bookmarks] == [(3.0, ""), (21.5, "Second verse")]
    assert again.loops == [Loop(95.0, 103.5, "Bridge")]
    assert sidecar.load(tmp_path / "other.mp3") is None


def test_two_files_of_the_same_name(tmp_path):
    """song.mp3 and song.flac in one folder: the first is song.xml, the second song.flac.xml; each reads its own."""
    mp3, flac = tmp_path / "song.mp3", tmp_path / "song.flac"
    mp3.write_bytes(b"1")
    flac.write_bytes(b"2")
    assert sidecar.save(mp3, FileState(1.0)) == tmp_path / "song.xml"
    assert sidecar.save(flac, FileState(2.0)) == tmp_path / "song.flac.xml"
    assert sidecar.load(mp3).position == 1.0 and sidecar.load(flac).position == 2.0
    assert sidecar.save(mp3, FileState(5.0)) == tmp_path / "song.xml"  # (el suyo, otra vez)


def test_moved_with_its_file(tmp_path):
    """Moved to another folder with its XML, the file finds its settings by its name."""
    old, new = tmp_path / "a", tmp_path / "b"
    old.mkdir()
    new.mkdir()
    (old / "song.mp3").write_bytes(b"x")
    sidecar.save(old / "song.mp3", state())
    for name in ("song.mp3", "song.xml"):
        os.replace(old / name, new / name)
    assert sidecar.load(new / "song.mp3").position == 83.25
    assert sidecar.save(new / "song.mp3", FileState(9.0)) == new / "song.xml"  # (y ahora nombra la ruta nueva)
    assert ET.parse(new / "song.xml").getroot().find("file").get("path") == str((new / "song.mp3").resolve())


def test_in_a_folder(tmp_path):
    """In a folder of their own: two song.mp3 of different folders do not take each other's XML."""
    keep = tmp_path / "settings"
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "song.mp3").write_bytes(b"1")
    (two / "song.mp3").write_bytes(b"2")
    assert sidecar.save(one / "song.mp3", FileState(1.0), keep) == keep / "song.xml"
    second = sidecar.save(two / "song.mp3", FileState(2.0), keep)
    assert second == keep / "song.mp3.xml"
    assert sidecar.load(one / "song.mp3", keep).position == 1.0 and sidecar.load(two / "song.mp3", keep).position == 2.0
    assert not (one / "song.xml").exists()


def test_damaged_or_foreign_xml(tmp_path):
    """An XML of the same name that is not ours (or is damaged) is left alone, and ours gets another name."""
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x")
    (tmp_path / "song.xml").write_text("<score><part/></score>")
    assert sidecar.load(audio) is None
    assert sidecar.save(audio, FileState(4.0)) == tmp_path / "song.mp3.xml"
    assert (tmp_path / "song.xml").read_text() == "<score><part/></score>"


def test_the_window_keeps_it(tmp_path, monkeypatch, output):
    """Closing a file writes its XML beside it; opened again, even with bookmarks.json gone, all comes back; in a
    folder chosen, the XML goes there; Not saved writes none."""
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
    w.open_file(song)
    w.audio.wait(10)
    w.set_speed(0.7)
    w.add_bookmark_at(1.5)
    w.set_selection((1.0, 2.0))
    w.save_loop()
    w._loop_renamed(0, "Lick")
    w.seek(2.5)
    w.close_file()
    xml = music / "song.xml"
    assert xml.is_file() and ET.parse(xml).getroot().find("playback").get("speed") == "0.7"
    w.close()

    w = window("two.json")  # (otro bookmarks.json, vacío: lo que vuelve es del XML)
    w.open_file(song)
    w.audio.wait(10)
    w._tick()
    app.processEvents()
    assert w.player.speed == 0.7 and [b.time for b in w.bookmarks] == [1.5] and [x.label for x in w.loops] == ["Lick"]
    assert abs(w.player.position - 2.5) < 0.05 and w.selection == (1.0, 2.0)
    keep = tmp_path / "kept"
    monkeypatch.setattr("py_slowdown.window.QFileDialog.getExistingDirectory", lambda *args: str(keep))
    w.a_sidecar["folder"].trigger()
    assert w.a_sidecar["folder"].isChecked() and str(keep) in w.a_sidecar["folder"].text()
    w.close_file()
    assert (keep / "song.xml").is_file()
    w.a_sidecar["off"].trigger()
    xml.unlink()
    (keep / "song.xml").unlink()
    w.open_file(song)
    w.close_file()
    assert not xml.exists() and not (keep / "song.xml").exists()
    w.close()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permissions of POSIX, not as root")
def test_a_folder_that_cannot_be_written(tmp_path, monkeypatch, output):
    """Where the XML cannot be written, the status bar says so, and the rest goes on (bookmarks.json keeps it)."""
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
        assert not (locked / "song.xml").exists() and any("song.wav" in m for m in messages)
        assert w.store.settings(song)["speed"] == 0.6
        w.close()
    finally:
        locked.chmod(0o755)
