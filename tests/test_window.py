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
    assert not w.pitch_box.isEnabled() and not w.a_higher.isEnabled()
    assert "Rubber Band" in w.statusBar().currentMessage()
    w.change_speed(0.5)
    assert w.player.speed == 1.0
    assert w.open_file(wav)
    w.close()


def test_files_sent_by_the_system(app, wav):
    """macOS sends the files of Open With as events (FileOpen): to the window, or kept until there is one."""
    from types import SimpleNamespace

    from PySide6.QtGui import QFileOpenEvent

    from py_slowdown.app import application_class

    opened = []
    event = application_class().event  # (on a stand-in: there is only one QApplication per process)
    early = SimpleNamespace(window=None, waiting=[])
    assert event(early, QFileOpenEvent(str(wav))) is True
    assert early.waiting == [str(wav)]
    ready = SimpleNamespace(window=SimpleNamespace(open_file=opened.append), waiting=[])
    assert event(ready, QFileOpenEvent(str(wav))) is True
    assert opened == [str(wav)] and ready.waiting == []


def test_finder_argument_is_ignored(monkeypatch):
    """An old macOS adds -psn_0_12345 when it opens an application: it is not taken as an unknown option."""
    from py_slowdown import app

    seen = []
    monkeypatch.setattr(app, "build_parser", lambda: SimpleParser(seen))
    monkeypatch.setattr(app, "application_class", lambda: (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        app.main(["-psn_0_12345", "talk.mp3"])
    assert seen == [["talk.mp3"]]


class SimpleParser:
    def __init__(self, seen):
        self.seen = seen

    def parse_args(self, argv):
        self.seen.append(argv)


def test_selection_and_repeat(window, app, wav):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    loaded(window, app, wav)
    assert not window.a_repeat.isChecked() and window.player.loop is None
    window.set_selection((3.0, 2.0))  # (en cualquier orden)
    assert window.selection == (2.0, 3.0) and window.wave.selection == (2.0, 3.0)
    assert window.player.loop is None  # seleccionada, pero sin repetir
    window.a_repeat.trigger()
    assert window.b_repeat.isChecked() and window.player.loop == pytest.approx((2.0, 3.0))
    window.set_selection(None)
    assert window.player.loop is None and window.wave.selection is None
    # I y O ponen el principio y el final en la posición
    window.seek(1.0)
    window.a_sel_start.trigger()
    window.seek(4.0)
    window.a_sel_end.trigger()
    assert window.selection == pytest.approx((1.0, 4.0)) and window.player.loop == pytest.approx((1.0, 4.0))
    window.a_sel_clear.trigger()
    assert window.selection is None
    # Mayús+arrastrar sobre la forma de onda
    wave = window.wave
    x0, x1 = round(wave.x_of(2.0)), round(wave.x_of(5.0))
    y = wave.height() // 2
    QTest.mousePress(wave, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x0, y))
    QTest.mouseMove(wave, QPoint(x1, y))
    QTest.mouseRelease(wave, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(x1, y))
    assert window.selection == pytest.approx((2.0, 5.0), abs=0.05)
    window.a_repeat.trigger()
    assert window.player.loop is None and window.selection is not None  # (la selección queda, sin repetir)
    window.close_file()
    assert window.selection is None


def test_count_in(window, app, wav, output, monkeypatch):
    from py_slowdown.countin import CountIn, CountInDialog

    loaded(window, app, wav)
    calls = []
    monkeypatch.setattr(window.player, "play", lambda *args: calls.append(args))
    window.toggle()
    assert calls == [()]  # sin cuenta previa
    window.a_count.trigger()
    assert window.b_count.isChecked() and window.count.on
    window.set_speed(0.5)
    window.toggle()
    assert calls[-1] == (4, 50.0, 0.0)  # cuatro golpes, 100 BPM a 0,5×, sin desplazar la grabación
    assert CountIn.load(window.settings).on  # (se guarda)
    dialog = CountInDialog(CountIn(True, 3, 120, False), 0.5, window)
    assert "120" in dialog.note.text() and dialog.value() == CountIn(True, 3, 120, False)
    dialog.on.setChecked(False)
    assert not dialog.bpm.isEnabled()
    dialog.close()


def test_count_shown_on_the_waveform(window, app, wav, output):
    loaded(window, app, wav)
    window.a_count.setChecked(True)
    window.toggle()
    window._tick()
    assert window.wave.count is None  # (el soplo antes del primer golpe: todavía nada)
    block = window.player._queue[0]
    block.used = block.count[0]  # (como si ya sonara el primer golpe)
    window._tick()
    assert window.wave.count == 1
    window.grab()  # (se dibuja)
    window.toggle()
    window._tick()
    assert window.wave.count is None


def test_moving_the_position_does_not_redraw_the_wave(app):
    """The waveform is drawn once into images, and a move of the position only copies them: drawing it each
    time (a polygon of thousands of peaks) took more than 100 ms with the GIL held, and the sound broke off
    every time the line advanced a pixel in a long file."""
    import time as clock
    from types import SimpleNamespace

    import numpy as np

    from py_slowdown.audio import Peaks
    from py_slowdown.waveform import Waveform

    # Una grabación de 20 minutos, solo en picos (lo que la vista entera usa)
    count = 20 * 60 * RATE // 256
    peaks = Peaks(count)
    peaks.lo[:count] = -np.abs(np.sin(np.arange(count) / 50)).astype(np.float32)
    peaks.hi[:count] = -peaks.lo[:count]
    peaks.count = count
    audio = SimpleNamespace(rate=RATE, decoded=count * 256, done=True, length=count * 256, duration=count * 256 / RATE,
                            peaks=peaks, frames=lambda a, b: np.zeros((0, 2), np.float32))
    wave = Waveform()
    wave.resize(1600, 500)
    wave.set_audio(audio)
    wave.grab()
    images = wave._cache
    assert images is not None
    start = clock.perf_counter()
    for seconds in range(60, 600, 60):
        wave.set_position(float(seconds))
        wave.grab()
    assert wave._cache is images  # (copiadas, no dibujadas otra vez)
    assert (clock.perf_counter() - start) / 9 < 0.05


def test_the_wave_follows_the_reading(app, monkeypatch):
    """The waveform drawn when the file was opened, half read, stayed so (not filling the window) until something
    else redrew it; and so did the scale of the announced length, once the real one, shorter, was known. While
    the file is read it is redrawn at most every READ_REDRAW seconds, and at once when the reading ends."""
    from types import SimpleNamespace

    import numpy as np

    from py_slowdown import waveform
    from py_slowdown.audio import Peaks
    from py_slowdown.waveform import READ_REDRAW, Waveform

    now = [100.0]
    monkeypatch.setattr(waveform.time, "monotonic", lambda: now[0])
    # Anunciada de 60 s, mide 50; al abrirla solo se han leído 10.
    count = 50 * RATE // 256
    peaks = Peaks(count)
    peaks.lo[:count] = -0.5
    peaks.hi[:count] = 0.5
    audio = SimpleNamespace(rate=RATE, decoded=0, done=False, length=60 * RATE, duration=60.0, peaks=peaks,
                            frames=lambda a, b: np.zeros((0, 2), np.float32))

    def read(seconds):
        peaks.count = int(seconds * RATE) // 256
        audio.decoded = peaks.count * 256

    def drawn(wave):
        # Las columnas en que hay onda, en la imagen de lo que no ha sonado
        wave.grab()
        image = wave._cache[1]
        return sum(1 for x in range(image.width()) if image.pixel(x, image.height() // 2) >> 24)

    wave = Waveform()
    wave.resize(1000, 300)
    read(10)
    wave.set_audio(audio)
    assert abs(drawn(wave) - 1000 * 10 / 60) <= 2
    calls = []
    update = wave.update
    wave.update = lambda: calls.append(1)
    wave.follow_reading()
    calls.clear()
    wave.follow_reading()
    assert not calls  # (sin cambios, nada que redibujar)
    read(20)
    now[0] += READ_REDRAW / 2
    wave.follow_reading()
    assert not calls  # (demasiado pronto: espera)
    now[0] += READ_REDRAW
    wave.follow_reading()
    assert calls  # (se leyó más: se redibuja)
    calls.clear()
    read(50)
    audio.done, audio.length, audio.duration = True, audio.decoded, 50.0
    wave.follow_reading()
    assert calls  # (terminó, con su largo real: enseguida)
    wave.update = update
    assert drawn(wave) >= 998  # (la onda entera llena la ventana)
    calls.clear()
    wave.update = lambda: calls.append(1)
    now[0] += READ_REDRAW
    wave.follow_reading()
    assert not calls  # (sin cambios, nada que redibujar)


def test_reading_elsewhere_does_not_redraw_the_wave(app):
    """While the file is read, a view of a part already read keeps its images when the position moves: only the
    column where the reading ends within the view, and the loudest peak (the scale), make them again."""
    from types import SimpleNamespace

    import numpy as np

    from py_slowdown.audio import Peaks
    from py_slowdown.waveform import Waveform

    count = 600 * RATE // 256
    peaks = Peaks(count)
    peaks.lo[:count] = -0.5
    peaks.hi[:count] = 0.5
    peaks.count = count // 4
    audio = SimpleNamespace(rate=RATE, decoded=peaks.count * 256, done=False, length=count * 256,
                            duration=600.0, peaks=peaks, frames=lambda a, b: np.zeros((0, 2), np.float32))
    wave = Waveform()
    wave.resize(1000, 300)
    wave.set_audio(audio)
    wave.zoom(50, 0)  # (los primeros 12 segundos, ya leídos)
    wave.grab()
    images = wave._cache
    for seconds in (2, 4, 6):
        peaks.count += 1000
        audio.decoded = peaks.count * 256
        wave.set_position(float(seconds))
        wave.grab()
    assert wave._cache is images
    peaks.hi[peaks.count] = 0.9  # (un pico mayor cambia la escala)
    peaks.count += 1
    audio.decoded = peaks.count * 256
    wave.grab()
    assert wave._cache is not images


def test_pitch_controls(window, app, wav):
    loaded(window, app, wav)
    assert window.pitch_box.value() == 0.0 and not window.b_pitch.isEnabled()
    window.a_higher.trigger()
    window.a_higher.trigger()
    assert window.player.pitch == 2.0 and window.pitch_box.value() == 2.0 and window.b_pitch.isEnabled()
    window.a_lower.trigger()
    assert window.player.pitch == 1.0
    window.pitch_box.setValue(-3.5)  # (con decimales: para afinar una grabación con el instrumento)
    assert window.player.pitch == -3.5
    window.set_pitch(40)
    assert window.player.pitch == 12.0 and window.pitch_box.value() == 12.0
    window.a_original_pitch.trigger()
    assert window.player.pitch == 0.0 and not window.b_pitch.isEnabled()
    assert window.player.speed == 1.0  # (la velocidad no cambió)


def test_count_in_settings_are_easy_to_reach(window, app, monkeypatch):
    """The settings of the count-in: in the arrow of its button, in Playback and in Settings; the button's tooltip
    says what they are now."""
    from PySide6.QtWidgets import QToolButton

    from py_slowdown.countin import CountIn

    assert window.b_count.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
    assert window.a_count_settings in window.b_count.menu().actions()
    menus = {a.text(): a.menu() for a in window.menuBar().actions()}
    assert window.a_count_options in menus["&Settings"].actions()
    assert window.a_count_settings in menus["&Playback"].actions()
    assert "4 clicks at 100 BPM, following the speed" in window.b_count.toolTip()

    class Accepting:
        def __init__(self, *args):
            pass

        def exec(self):
            return True

        def value(self):
            return CountIn(True, 3, 132, False)

    monkeypatch.setattr("py_slowdown.window.CountInDialog", Accepting)
    window.a_count_options.trigger()
    assert window.count == CountIn(True, 3, 132, False) and window.b_count.isChecked()
    assert "3 clicks at 132 BPM." in window.b_count.toolTip()
    assert CountIn.load(window.settings) == CountIn(True, 3, 132, False)  # (guardados)


def test_tap_tempo():
    from py_slowdown.countin import TapTempo, recording_tempo

    tapper = TapTempo()
    assert tapper.tap(10.0) is None  # (one tap: no tempo yet)
    assert tapper.tap(10.5) == pytest.approx(120)
    # Uneven by a few hundredths, and one tap late: the median keeps 120
    for when in (11.0, 11.52, 11.98, 12.6, 13.0, 13.5):
        bpm = tapper.tap(when)
    assert bpm == pytest.approx(120, abs=2)
    # A pause of more than two seconds begins a new measure
    assert tapper.tap(20.0) is None and tapper.taps == 1
    assert tapper.tap(20.75) == pytest.approx(80)
    # Only the last eight taps count: a change of tempo is followed
    for k in range(1, 9):
        bpm = tapper.tap(20.75 + k * 0.4)
    assert bpm == pytest.approx(150)
    # Tapped at 0.75×, following the speed: the recording is faster
    assert recording_tempo(90, 0.75, True) == 120 and recording_tempo(90, 0.75, False) == 90
    assert recording_tempo(1000, 1.0, False) == 300


def test_tap_in_the_window(window, app, wav, monkeypatch):
    import time as clock

    loaded(window, app, wav)
    now = [100.0]
    monkeypatch.setattr(clock, "monotonic", lambda: now[0])
    window.set_speed(0.5)
    for _ in range(4):
        window.a_tap.trigger()
        now[0] += 1.0  # 60 BPM heard, at half speed
    assert window.count.bpm == 120  # (el de la grabación: la cuenta sigue la velocidad)
    assert "60 BPM heard" in window.statusBar().currentMessage()
    assert "2 clicks" not in window.b_count.toolTip() and "120 BPM" in window.b_count.toolTip()
    window.b_tap.click()
    assert window.count.bpm == 120


def test_tap_in_the_dialog(app, monkeypatch):
    import time as clock

    from py_slowdown.countin import CountIn, CountInDialog

    now = [5.0]
    monkeypatch.setattr(clock, "monotonic", lambda: now[0])
    dialog = CountInDialog(CountIn(True, 4, 100, False), 1.0)
    for _ in range(3):
        dialog.tap_button.click()
        now[0] += 0.4
    assert dialog.bpm.value() == 150
    dialog.close()


def test_count_in_offset_setting(window, app, wav, monkeypatch):
    from py_slowdown.countin import CountIn, CountInDialog

    loaded(window, app, wav)
    dialog = CountInDialog(CountIn(True, 4, 120, True, -0.2), 1.0, window)
    assert dialog.offset.value() == -0.2 and dialog.value().offset == -0.2
    dialog.offset.setValue(-1.5)  # (más que lo que cabe antes del pulso a 120 BPM)
    assert "at most" in dialog.note.text()
    dialog.close()

    class Accepting:
        def __init__(self, *args):
            pass

        def exec(self):
            return True

        def value(self):
            return CountIn(True, 4, 120, True, 0.15)

    monkeypatch.setattr("py_slowdown.window.CountInDialog", Accepting)
    window.a_count_options.trigger()
    assert CountIn.load(window.settings).offset == 0.15  # (guardado)
    assert "+0.15 s off the beat" in window.b_count.toolTip()
    calls = []
    monkeypatch.setattr(window.player, "play", lambda *args: calls.append(args))
    window.toggle()
    assert calls == [(4, 120.0, 0.15)]


def test_first_beat_on_the_waveform(window, app, wav, monkeypatch):
    """Right click > Count-in: the first beat is here: the offset from the position to that point."""
    from py_slowdown.countin import CountIn

    loaded(window, app, wav)
    window.seek(2.0)
    window.wave.firstBeatRequested.emit(2.3)  # (el menú del clic derecho, sobre 2.3 s)
    assert window.count.on and window.a_count.isChecked()
    assert window.count.offset == pytest.approx(-0.3)  # (la grabación entra 0,3 s antes del pulso)
    assert "0.3 s before the beat" in window.statusBar().currentMessage()
    assert CountIn.load(window.settings).offset == pytest.approx(-0.3)
    window._tick()
    assert window.wave.first_beat == pytest.approx(2.3)  # (la línea verde, donde la espera)
    window.grab()
    # Antes de la posición: entra después
    window.wave.firstBeatRequested.emit(1.9)
    assert window.count.offset == pytest.approx(0.1) and "after" in window.statusBar().currentMessage()
    # Demasiado lejos: no cambia
    window.wave.firstBeatRequested.emit(5.0)
    assert window.count.offset == pytest.approx(0.1) and "within" in window.statusBar().currentMessage()
    # Más antes de lo que cabe a este tempo (100 BPM: unas 0,53 s): lo dice
    window.wave.firstBeatRequested.emit(3.5)
    assert window.count.offset == pytest.approx(-1.5) and "at most" in window.statusBar().currentMessage()
    # En la posición: sin desfase, y sin línea
    window.wave.firstBeatRequested.emit(None)
    window._tick()
    assert window.count.offset == 0.0 and window.wave.first_beat is None


def test_reopen_the_last_file(app, output, tmp_path, monkeypatch, wav):
    """Settings > Reopen the last file when starting: the last file is opened again, unless another is named,
    or it is gone; off (as at first), nothing is opened."""
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)

    def window():
        return Window(player=Player(output), store=Store(tmp_path / "b.json"), settings=settings)

    first = window()
    assert not first.a_reopen.isChecked()
    first.open_file(wav)
    first.close()
    second = window()
    second.open_at_start(None)
    assert second.audio is None  # (apagado: nada)
    second.a_reopen.trigger()
    second.close()
    third = window()
    assert third.a_reopen.isChecked()
    third.open_at_start(None)
    assert third.audio is not None and third.audio.path == wav
    third.close()
    other = tmp_path / "other.wav"
    other.write_bytes(wav.read_bytes())
    fourth = window()
    fourth.open_at_start(str(other))  # (uno nombrado en la línea de órdenes, primero)
    assert fourth.audio.path == other
    fourth.close()
    other.unlink()  # (el último ya no está: nada, sin error)
    fifth = window()
    fifth.open_at_start(None)
    assert fifth.audio is None
    fifth.close()
