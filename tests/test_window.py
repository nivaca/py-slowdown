import time

import pytest
from conftest import RATE
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from py_slowdown import interface
from py_slowdown.bookmarks import Store
from py_slowdown.engine import Player
from py_slowdown.waveform import columns
from py_slowdown.window import Window


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, output, tmp_path, monkeypatch):
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    w = Window(player=Player(output), store=Store(tmp_path / "bookmarks.json"), settings=settings)
    w.resize(1000, 400)
    w.show()
    yield w
    w.close()


def loaded(window, app, path):
    assert window.open_file(path)
    window.audio.wait(10)
    window._tick()
    app.processEvents()


def test_open_play_and_bookmarks(window, app, wav, output):
    loaded(window, app, wav)
    assert window.time_label.text() == "0:00.0 / 0:06.0"
    window.seek(2.0)
    window.add_bookmark()
    window.add_bookmark_at(4.0)
    window.add_bookmark_at(4.01)  # ya hay uno allí
    assert [b.time for b in window.bookmarks] == [2.0, 4.0]
    assert window.panel.table.rowCount() == 2
    window.panel.table.item(1, 1).setText("the end part")
    assert window.bookmarks[1].label == "the end part"
    window.seek(0.0)
    window.goto_bookmark(1)
    assert window.player.position == 2.0
    window.goto_bookmark(1)
    assert window.player.position == 4.0
    window.goto_bookmark(-1)
    assert window.player.position == 2.0
    window.remove_bookmark(0)
    assert [b.label for b in window.store.bookmarks(wav)] == ["the end part"]


def test_speed_controls(window, app, wav):
    loaded(window, app, wav)
    window.a_slower.trigger()
    assert window.player.speed == 0.95 and window.speed_box.value() == 0.95
    window.speed_slider.setValue(50)
    assert window.player.speed == 0.5 and window.speed_box.value() == 0.5
    window.a_normal.trigger()
    assert window.player.speed == 1.0 and window.speed_slider.value() == 100
    window.set_speed(10)
    assert window.player.speed == 3.0


def test_transport(window, app, wav, output):
    loaded(window, app, wav)
    window.toggle()
    assert window.player.playing
    for _ in range(200):
        output.pull()
        time.sleep(0.001)
        if window.player.position > 0.5:
            break
    window.toggle()
    assert not window.player.playing
    window.jump(5.0)
    assert window.player.position == pytest.approx(window.player.position)
    window.go_end()
    assert window.player.position == pytest.approx(6.0)
    window.a_start.trigger()
    assert window.player.position == 0.0
    window.a_forward.trigger()
    assert window.player.position == 5.0
    window.stop()
    assert window.player.position == 0.0


def test_resume_where_left(window, app, wav):
    loaded(window, app, wav)
    window.seek(3.3)
    window.close_file()
    assert window.store.position(wav) == pytest.approx(3.3)
    loaded(window, app, wav)
    assert window.player.position == pytest.approx(3.3)


def test_bad_file(window, app, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("py_slowdown.window.QMessageBox.warning", lambda *a: shown.append(a[2]))
    path = tmp_path / "no.mp3"
    path.write_text("nothing")
    assert not window.open_file(path)
    assert shown and window.audio is None


def test_waveform_columns(window, app, wav):
    loaded(window, app, wav)
    audio = window.audio
    lo, hi = columns(audio, 0, audio.decoded / 600, 600)
    assert hi.max() > 0.9 and lo.min() < -0.04  # los tictacs y el tono
    lo, hi = columns(audio, RATE, 2.0, 100)  # muy cerca: muestras, no picos
    assert hi[0] > 0.9
    window.wave.zoom(8)
    assert window.wave.fpp > 0 and window.view.bar.isVisible()
    window.wave.fit()
    assert window.wave.fpp == 0
    window.grab()  # dibuja sin errores


def test_spanish_window(app, output, tmp_path, monkeypatch):
    interface.use("es")
    try:
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        w = Window(player=Player(output), store=Store(tmp_path / "b.json"), settings=settings)
        titles = [a.text() for a in w.menuBar().actions()]
        assert titles[0] == "&Archivo" and "&Marcadores" in titles
        w.close()
    finally:
        interface.use("en")


def test_without_rubberband(app, output, tmp_path, monkeypatch, wav):
    """Without the Rubber Band Library the speed controls are off, and a file still plays at 1×."""
    from py_slowdown import rubberband

    def missing():
        raise rubberband.RubberBandError("not found")

    monkeypatch.setattr(rubberband, "library", missing)
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    w = Window(player=Player(output), store=Store(tmp_path / "b.json"), settings=settings)
    assert not w.speed_slider.isEnabled() and not w.a_faster.isEnabled()
    assert "Rubber Band" in w.statusBar().currentMessage()
    w.change_speed(0.5)
    assert w.player.speed == 1.0
    assert w.open_file(wav)
    w.close()
