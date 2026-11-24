import json

from py_slowdown.bookmarks import Bookmark, Store, export_text
from py_slowdown.timefmt import clock, parse


def test_store_round_trip(tmp_path):
    path = tmp_path / "b.json"
    audio = tmp_path / "x.mp3"
    store = Store(path)
    store.set_bookmarks(audio, [Bookmark(12.5, "two"), Bookmark(3.25, "one")])
    store.set_position(audio, 7.0)
    again = Store(path)
    assert again.bookmarks(audio) == [Bookmark(3.25, "one"), Bookmark(12.5, "two")]
    assert again.position(audio) == 7.0
    data = json.loads(path.read_text())
    assert list(data["files"]) == [str(audio.resolve())]


def test_empty_entries_go_away(tmp_path):
    store = Store(tmp_path / "b.json")
    audio = tmp_path / "x.mp3"
    store.set_bookmarks(audio, [Bookmark(1.0)])
    store.set_bookmarks(audio, [])
    store.set_position(audio, 0.0)
    assert json.loads((tmp_path / "b.json").read_text())["files"] == {}


def test_damaged_file(tmp_path):
    path = tmp_path / "b.json"
    path.write_text("{ not json")
    store = Store(path)
    assert store.bookmarks(tmp_path / "x.mp3") == []
    store.set_position(tmp_path / "x.mp3", 3.0)
    assert Store(path).position(tmp_path / "x.mp3") == 3.0


def test_export():
    text = export_text([Bookmark(5.0, "a"), Bookmark(3725.37, "")], "talk.mp3")
    assert text == "# talk.mp3\n0:05.0\ta\n1:02:05.3\t\n"


def test_clock_and_parse():
    assert clock(0) == "0:00"
    assert clock(83.46, tenths=True) == "1:23.4"
    assert clock(3600 * 2 + 5) == "2:00:05"
    assert parse("83") == 83 and parse("1:23.5") == 83.5 and parse("1:01:23") == 3683
    assert parse("1,5") == 1.5 and parse("abc") is None


def test_folders_of_each_system(monkeypatch, tmp_path):
    """The bookmarks and the decoded sound go where each system keeps such things."""
    import sys

    from py_slowdown import audio, bookmarks

    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert bookmarks.data_dir() == tmp_path / "Roaming" / "py-slowdown"
    assert audio.cache_dir() == tmp_path / "Local" / "py-slowdown" / "cache"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert bookmarks.data_dir() == tmp_path / "Library" / "Application Support" / "py-slowdown"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert bookmarks.data_dir() == tmp_path / "data" / "py-slowdown"
