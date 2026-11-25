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
    window.a_ask_save.setChecked(False)  # (lo que se hace se guarda en el momento)
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


def test_pause_goes_back(window, app, wav, output):
    """For practising: Space pauses and takes the position back to where playing started, to hear the passage
    again; Continue from the pause (Shift+Space) goes on from where it was paused, and pausing then goes back to
    the same start. Moved while it plays, it goes back to the new place; at the end of the file, too."""

    def play_for(seconds):
        # (la tarjeta falsa pide sonido hasta que la posición avanza SECONDS, o el archivo se acaba)
        until = window.player.position + seconds
        for _ in range(3000):
            output.pull()
            time.sleep(0.001)
            if window.player.position >= until or window.player.ended:
                break
        app.processEvents()

    loaded(window, app, wav)
    assert not window.a_continue.isEnabled()
    window.seek(1.0)
    window.toggle()
    play_for(1.0)
    paused = window.player.position
    assert paused > 1.5
    window.toggle()
    assert not window.player.playing and window.player.position == pytest.approx(1.0)
    assert window._paused_at == pytest.approx(paused) and window.a_continue.isEnabled()
    window._tick()
    assert window.wave.pause_mark == pytest.approx(paused)  # (la línea de puntos de la pausa)
    window.grab()
    window.toggle()  # (otra vez el mismo pasaje)
    play_for(0.5)
    window.toggle()
    assert window.player.position == pytest.approx(1.0)
    # Seguir desde la pausa, como antes; pausar vuelve al principio de siempre
    window.a_continue.trigger()
    assert window.player.playing and window.player.position >= window._paused_at - 0.01
    window._tick()
    assert window.wave.pause_mark is None  # (sonando, no se muestra)
    resumed = window._paused_at
    play_for(0.5)
    window.toggle()
    assert window.player.position == pytest.approx(1.0) and window._paused_at > resumed
    # Llevada a otro lugar mientras suena: vuelve allí
    window.toggle()
    window.seek(3.0)
    play_for(0.3)
    window.toggle()
    assert window.player.position == pytest.approx(3.0)
    # Al final del archivo, también vuelve
    window.seek(5.5)
    window.toggle()
    play_for(1.0)
    window._tick()
    assert not window.player.playing and window.player.position == pytest.approx(5.5)
    window.stop()
    assert window.player.position == 0.0 and not window.a_continue.isEnabled()
    window._tick()
    assert window.wave.pause_mark is None


def test_volume_knob_and_boost(window, app, wav, output):
    """The volume is a knob from 0 to 100%. Boost multiplies the sound (by 1.8 at first; Settings > Volume boost
    changes it) and leaves the knob's number as it is; where that makes it louder than the recording, the knob's
    value and pointer are red, and the sound is clipped at full scale, never wrapped. A file kept by a 1.3 version
    above 100% opens boosted."""
    import numpy as np

    assert window.volume.maximum() == 100 and window.volume.text() == "100%"
    assert window.boost_factor == 1.8 and window.a_boosts[1.8].isChecked()
    window.volume.setValue(70)
    assert window.player.volume == pytest.approx(0.49)
    window.boost.setChecked(True)
    assert window.volume.value() == 70 and window.volume.text() == "70%"  # (el número no cambia)
    assert window.player.volume == pytest.approx(0.882) and window.settings.value("volume_boost", type=bool)
    assert "times 1.8" in window.volume.toolTip() and "distort" not in window.volume.toolTip()
    assert "times 1.8" in window.boost.toolTip()

    def reds():
        image = window.volume.grab().toImage()
        return sum(1 for x in range(image.width()) for y in range(image.height())
                   if image.pixelColor(x, y).red() > 150 and image.pixelColor(x, y).green() < 80)

    assert reds() == 0  # (70 %, reforzado: 0,88, todavía no pasa de la grabación)
    window.volume.setValue(80)
    assert window.player.volume == pytest.approx(1.152) and "distort" in window.volume.toolTip() and reds() > 10
    window.a_boosts[1.5].trigger()  # (Configuración > Refuerzo del volumen)
    assert window.boost_factor == 1.5 and window.settings.value("volume_boost_factor", type=float) == 1.5
    assert window.player.volume == pytest.approx(0.96) and reds() == 0 and "times 1.5" in window.boost.toolTip()
    window.a_boosts[1.8].trigger()
    window.boost.setChecked(False)
    assert window.player.volume == pytest.approx(0.64) and window.volume.value() == 80 and reds() == 0
    loaded(window, app, wav)
    window.boost.setChecked(True)
    window.volume.setValue(100)  # (después de abrir: cada archivo empieza en 100 %)
    window.toggle()
    loudest = 0.0
    for _ in range(300):
        loudest = max(loudest, float(np.abs(output.pull()).max()))
        time.sleep(0.001)
    assert loudest == pytest.approx(1.0)  # (los golpes de 0,9, por 1,8, recortados en 1)
    window.boost.setChecked(False)
    window._apply_file_settings({"volume": 150})  # (de una versión 1.3)
    assert window.boost.isChecked() and window.volume.value() == 100


def test_count_in_clicks_menu(window, app):
    """Count-in > Clicks: how many clicks the count-in gives (4 at first), the one chosen ticked; the dialog's
    number is the same, and one chosen there that is not in the list is added to it."""
    menu = {a.text(): a.menu() for a in window.menuBar().actions()}["&Count-in"]
    assert window.clicks_menu in [a.menu() for a in menu.actions()]
    window._fill_clicks_menu()
    ticked = [a.text() for a in window.clicks_menu.actions() if a.isChecked()]
    assert ticked == ["4"] and window.count.beats == 4
    next(a for a in window.clicks_menu.actions() if a.text() == "3").trigger()
    assert window.count.beats == 3 and "3 clicks" in window.a_count.statusTip()
    from py_slowdown.countin import CountIn

    assert CountIn.load(window.settings).beats == 3
    window.set_count_beats(10)
    window._fill_clicks_menu()
    assert [a.text() for a in window.clicks_menu.actions() if a.isChecked()] == ["10"]


def test_speed_controls(window, app, wav):
    loaded(window, app, wav)
    window.a_slower.trigger()
    assert window.player.speed == 0.95 and window.speed_knob.value() == 95 and window.speed_knob.text() == "95%"
    window.speed_knob.setValue(50)
    assert window.player.speed == 0.5
    window.a_normal.trigger()
    assert window.player.speed == 1.0 and window.speed_knob.value() == 100
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
    assert not w.speed_knob.isEnabled() and not w.a_faster.isEnabled()
    assert not w.semitone_dial.isEnabled() and not w.cent_dial.isEnabled() and not w.a_higher.isEnabled()
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
    # Sin selección, se repite el archivo entero (leído ya: el final se sabe)
    assert window.player.loop == pytest.approx((0.0, 6.0)) and window.wave.selection is None
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
    assert window.a_count.isChecked() and window.count.on
    window.set_speed(0.5)
    window.toggle()
    assert calls[-1] == (4, 50.0, 0.0)  # cuatro golpes, 100 BPM a 0,5×, sin desplazar la grabación
    assert CountIn.load(window.settings).on  # (se guarda)
    dialog = CountInDialog(CountIn(True, 3, 120, False), 0.5, window)
    assert "120" in dialog.note.text() and dialog.value() == CountIn(True, 3, 120, False)
    dialog.on.setChecked(False)
    assert not dialog.bpm.isEnabled()


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
    """The pitch in semitones and cents (hundredths of a semitone), each with a slider and a box: Ctrl+↑ and
    Ctrl+↓ move it a semitone and keep the cents; the cents never make the semitones jump while they move."""
    loaded(window, app, wav)
    assert window.semitone_dial.value() == 0 and window.cent_dial.value() == 0 and not window.b_pitch.isEnabled()
    assert window.semitone_dial.maximum() == 12 and window.cent_dial.maximum() == 50
    window.a_higher.trigger()
    window.a_higher.trigger()
    assert window.player.pitch == 2.0 and window.semitone_dial.value() == 2 and window.b_pitch.isEnabled()
    assert window.semitone_dial.value() == 2
    window.a_lower.trigger()
    assert window.player.pitch == 1.0
    window.cent_dial.setValue(-15)  # (para afinar una grabación con el instrumento)
    assert window.player.pitch == pytest.approx(0.85) and window.cent_dial.value() == -15
    assert window.semitone_dial.text() == "+1 st" and window.cent_dial.text() == "−15 ¢"
    assert not hasattr(window, "pitch_box") and not hasattr(window, "semitone_box")  # (solo barras)
    window.a_higher.trigger()
    assert window.player.pitch == pytest.approx(1.85)
    assert (window.semitone_dial.value(), window.cent_dial.value()) == (2, -15)  # (los cents se quedan)
    window.semitone_dial.setValue(-3)
    assert window.player.pitch == pytest.approx(-3.15)
    window.cent_dial.setValue(50)
    assert window.player.pitch == pytest.approx(-2.5)
    assert (window.semitone_dial.value(), window.cent_dial.value()) == (-3, 50)  # (sin saltar a -2 y -50)
    window.set_pitch(2.25)  # (de un archivo: el semitono más cercano)
    assert (window.semitone_dial.value(), window.cent_dial.value()) == (2, 25)
    window.set_pitch(40)
    assert window.player.pitch == 12.0 and (window.semitone_dial.value(), window.cent_dial.value()) == (12, 0)
    window.cent_dial.setValue(30)  # (pasaría de 12: se queda en 12)
    assert window.player.pitch == 12.0 and window.cent_dial.value() == 0
    window.a_original_pitch.trigger()
    assert window.player.pitch == 0.0 and not window.b_pitch.isEnabled()
    assert window.semitone_dial.value() == 0 and window.cent_dial.value() == 0
    assert window.player.speed == 1.0  # (la velocidad no cambió)


def test_pitch_dials(window, app, wav):
    """The pitch dials: one step for each notch of the mouse wheel (a touchpad's pieces of a notch add up),
    and a double click takes a dial back to 0."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QWheelEvent

    from py_slowdown.window import PitchDial

    loaded(window, app, wav)
    assert isinstance(window.semitone_dial, PitchDial) and isinstance(window.cent_dial, PitchDial)

    def wheel(dial, dy):
        here = QPointF(18, 18)
        app.sendEvent(dial, QWheelEvent(here, dial.mapToGlobal(here), QPoint(), QPoint(0, dy),
                                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                        Qt.ScrollPhase.NoScrollPhase, False))

    wheel(window.semitone_dial, 120)
    wheel(window.semitone_dial, 120)
    assert window.player.pitch == 2.0 and window.semitone_dial.text() == "+2 st"
    for _ in range(3):
        wheel(window.cent_dial, -40)  # (tres tercios de muesca: un cent)
    assert window.player.pitch == pytest.approx(1.99) and window.cent_dial.text() == "−1 ¢"
    here = QPointF(18, 18)
    app.sendEvent(window.semitone_dial, QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, here,
                                                    window.semitone_dial.mapToGlobal(here),
                                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                                    Qt.KeyboardModifier.NoModifier))
    assert window.player.pitch == pytest.approx(-0.01) and window.semitone_dial.text() == "0 st"


def test_each_file_starts_from_the_defaults(window, app, wav, tmp_path):
    """A file with nothing kept opens with the usual speed, pitch, formants, way of hearing and count-in tempo, not
    with those of the file before, and the count-in off and the volume at 100%; one with settings kept gets its
    own (the volume too)."""
    from conftest import tone, write

    other = tmp_path / "other.wav"
    write(other, tone(3.0))
    loaded(window, app, wav)
    window.set_speed(0.6)
    window.set_pitch(-2.15)
    window.a_formants.setChecked(True)
    window.set_hearing("left", "bass")
    window.count.bpm = 140
    window.a_count.setChecked(True)
    window.volume.setValue(70)
    window.dropEvent(type("Drop", (), {"mimeData": lambda self: type("M", (), {
        "urls": lambda self: [__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(str(other))]})()})())
    window.audio.wait(10)
    assert window.audio.path.name == "other.wav"
    assert window.player.speed == 1.0 and window.player.pitch == 0.0 and not window.player.formants
    assert window.player.hearing == ("both", "none") and window.count.bpm == 100
    assert (window.semitone_dial.value(), window.cent_dial.value()) == (0, 0) and window.speed_knob.value() == 100
    assert window.volume.value() == 100 and not window.count.on  # (el volumen y la cuenta, como siempre)
    loaded(window, app, wav)  # (el primero, con lo suyo guardado)
    assert window.player.speed == 0.6 and window.player.pitch == pytest.approx(-2.15)
    assert window.player.hearing == ("left", "bass") and window.count.bpm == 140 and window.count.on
    assert window.volume.value() == 70


def test_go_to_the_start(window, app, wav):
    """Go to the start (Home, the button): with the count-in on and a first beat, to the first beat; with the
    count-in off, or no first beat, to the beginning of the file. Its tooltip says which."""
    loaded(window, app, wav)
    window.a_count.setChecked(True)
    window.seek(3.0)
    window.a_start.trigger()
    assert window.player.position == 0.0  # (sin primer pulso)
    window.set_first_beat(1.25)
    window.seek(4.0)
    window.a_start.trigger()
    assert window.player.position == pytest.approx(1.25) and "first beat, 0:01.2" in window.b_start.toolTip()
    window.seek(4.0)
    window.b_start.click()
    assert window.player.position == pytest.approx(1.25)
    window.a_count.setChecked(False)
    window.a_start.trigger()
    assert window.player.position == 0.0 and window.b_start.toolTip() == "Go to the start (Home)"


def test_starts_with_the_count_in_on(app, output, tmp_path, monkeypatch):
    """With the count-in left on in the settings, the window opens without an error (its actions are made before
    the tooltips they change), and says so. (An error in a slot is only printed by PySide: it is caught here.)"""
    import sys

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *info: errors.append(info))
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue("countin/on", True)
    w = Window(player=Player(output), store=Store(tmp_path / "b.json"), settings=settings)
    assert errors == []
    assert w.a_count.isChecked() and w.count.on and "clicks at" in w.a_count_settings.statusTip()
    w.close()


def test_ask_to_save(window, app, wav, tmp_path, monkeypatch):
    """Settings > Ask to save before closing a file (on at first): changes (bookmarks, loops, how it is played,
    not the position) are saved only when asked, the title marks them; closing asks: Save, Don't save (the
    position only), or Cancel (the file stays open, the program too). Off, all is saved as it is done."""
    from py_slowdown import sidecar
    from conftest import tone, write

    answers = []
    monkeypatch.setattr(Window, "_ask_save", lambda self, name: answers.pop(0))
    assert window.a_ask_save.isChecked()
    loaded(window, app, wav)
    assert not window._changed() and not window.windowTitle().startswith("•")
    window.seek(2.0)
    window._tick()
    assert not window._changed()  # (la posición no es un cambio)
    window.add_bookmark_at(1.0)
    window.set_speed(0.7)
    window._tick()
    assert window._changed() and window.windowTitle().startswith("• ")
    assert window.store.bookmarks(wav) == [] and sidecar.find(wav) is None  # (nada escrito todavía)
    # Cancelar: el archivo sigue abierto, también al salir
    answers.append("cancel")
    other = tmp_path / "other.wav"
    write(other, tone(2.0))
    assert not window.open_file(other) and window.audio.path == wav.resolve()
    answers.append("cancel")
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and window.audio is not None
    # No guardar: la posición sí, lo demás como estaba
    answers.append("discard")
    window.close_file()
    assert window.store.bookmarks(wav) == [] and window.store.settings(wav) == {} and sidecar.find(wav) is None
    assert window.store.position(wav) == pytest.approx(2.0)
    # Guardar (Ctrl+S, o al cerrar)
    loaded(window, app, wav)
    window.add_bookmark_at(1.5)
    window.a_save_slx.trigger()
    assert not window._changed() and [b.time for b in sidecar.read(sidecar.find(wav)).bookmarks] == [1.5]
    assert [b.time for b in window.store.bookmarks(wav)] == [1.5]
    window.add_bookmark_at(2.5)
    answers.append("save")
    window.close_file()
    assert [b.time for b in sidecar.read(sidecar.find(wav)).bookmarks] == [1.5, 2.5] and answers == []
    # Apagado: todo se guarda en el momento, sin preguntar
    loaded(window, app, wav)
    window.a_ask_save.setChecked(False)
    assert window.settings.value("ask_save", type=bool) is False
    window.add_bookmark_at(3.5)
    assert [b.time for b in sidecar.read(sidecar.find(wav)).bookmarks] == [1.5, 2.5, 3.5]
    window.close_file()  # (sin respuestas: no pregunta)


def test_close_and_quit_keys(window, app, wav):
    """Ctrl+W (or Ctrl+F4) closes the file and the program stays open; Alt+F4 (or Ctrl+Q) quits."""
    assert [k.toString() for k in window.a_close.shortcuts()] == ["Ctrl+W", "Ctrl+F4"]
    assert [k.toString() for k in window.a_quit.shortcuts()] == ["Ctrl+Q", "Alt+F4"]
    loaded(window, app, wav)
    window.a_close.trigger()
    assert window.audio is None and window.isVisible()
    window.a_quit.trigger()
    assert not window.isVisible()


def test_pitch_knobs_evenly_spaced(window, app):
    """The semitone knob, the cents knob and the button 0 are the same distance apart; each knob has its value
    written inside."""
    window.resize(1100, 480)
    app.processEvents()
    st, ct, zero = window.semitone_dial.geometry(), window.cent_dial.geometry(), window.b_pitch.geometry()
    assert ct.x() - (st.x() + st.width()) == zero.x() - (ct.x() + ct.width())
    assert st.width() == st.height() == 52 and window.b_pitch.text() == "ø"  # (más grandes: su valor va dentro)
    ticks = [sum(1 for v in range(d.minimum(), d.maximum() + 1) if v % d.tick == 0)
             for d in (window.semitone_dial, window.cent_dial)]
    assert ticks == [9, 21]  # (menos marcas en la de los semitonos que en la de los cents)
    window.cent_dial.setValue(-45)
    window.grab()
    assert window.cent_dial.text() == "−45 ¢" and not hasattr(window, "cent_label")


def test_knob_ticks_show_on_a_dark_theme(app):
    """The ticks of the pitch knobs are drawn in the text colour, so they show on a dark theme whose Mid colour is
    that of the background (as KDE's NordicDarker): they did not, in 1.3.0."""
    from PySide6.QtGui import QColor, QPalette

    from py_slowdown.window import PitchDial

    dial = PitchDial(" st", 3)
    dial.setRange(-12, 12)
    palette = QPalette()
    for role, rgb in ((QPalette.ColorRole.Window, (46, 52, 64)), (QPalette.ColorRole.Mid, (46, 52, 64)),
                      (QPalette.ColorRole.Button, (60, 68, 84)), (QPalette.ColorRole.WindowText, (216, 222, 233))):
        palette.setColor(role, QColor(*rgb))
    dial.setPalette(palette)
    dial.setAutoFillBackground(True)
    image = dial.grab().toImage()
    # La marca del 0, arriba, entre la cara de la perilla y el borde.
    top = QColor(image.pixel(dial.width() // 2, 2))
    assert top.lightness() > QColor(46, 52, 64).lightness() + 40


def test_split_pitch():
    from py_slowdown.window import split_pitch

    assert split_pitch(2.25) == (2, 25) and split_pitch(-2.25) == (-2, -25)
    assert split_pitch(2.5) == (3, -50) and split_pitch(2.5, 50) == (2, 50)
    assert split_pitch(3.85, -15) == (4, -15) and split_pitch(12.0, 30) == (12, 0)


def test_count_in_settings_are_easy_to_reach(window, app, monkeypatch):
    """The count-in has its own menu (Count-in: count in, tap the tempo, its settings), and its settings are also in
    the arrow of its button; Hear has its own menu too, the same that its button opens; the button's tooltip says
    what the settings are now."""
    from py_slowdown.countin import CountIn

    assert not hasattr(window, "b_count") and not hasattr(window, "b_hear") and hasattr(window, "b_tap")
    menus = {a.text(): a.menu() for a in window.menuBar().actions()}
    assert list(menus) == ["&File", "&Playback", "H&ear", "&Count-in", "&Bookmarks", "&View", "&Settings", "&Help"]
    assert menus["&Count-in"].actions()[:2] == [window.a_count, window.a_tap]
    assert window.a_count_settings in menus["&Count-in"].actions()
    assert window.a_count not in menus["&Playback"].actions() and window.a_count_settings not in menus["&Settings"].actions()
    assert menus["H&ear"] is window.hear_menu and window.a_filters["bass"] in menus["H&ear"].actions()
    assert "4 clicks at 100 BPM, following the speed" in window.a_count.statusTip()

    class Accepting:
        def __init__(self, *args):
            pass

        def exec(self):
            return True

        def value(self):
            return CountIn(True, 3, 132, False)

    monkeypatch.setattr("py_slowdown.window.CountInDialog", Accepting)
    window.a_count_settings.trigger()
    assert window.count == CountIn(True, 3, 132, False) and window.a_count.isChecked()
    assert "3 clicks at 132 BPM." in window.a_count_settings.statusTip()
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
    assert "2 clicks" not in window.a_count.statusTip() and "120 BPM" in window.a_count.statusTip()
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
    window.a_count_settings.trigger()
    assert CountIn.load(window.settings).offset == 0.15  # (guardado)
    assert "+0.15 s off the beat" in window.a_count.statusTip()
    calls = []
    monkeypatch.setattr(window.player, "play", lambda *args: calls.append(args))
    window.toggle()
    assert calls == [(4, 120.0, 0.15)]


def test_grid_offset():
    """With a first beat, the recording comes in on the nearest beat of its grid; earlier than the count allows, on
    the beat before."""
    from py_slowdown.countin import grid_offset

    # 100 BPM: un pulso cada 0,6 s; el primero en 2,3: ... 1,1  1,7  2,3  2,9  3,5 ...
    assert grid_offset(2.0, 2.3, 100, 1.0, 0.5) == pytest.approx(-0.3)  # (entra 0,3 s antes del pulso 2,3)
    assert grid_offset(3.0, 2.3, 100, 1.0, 0.5) == pytest.approx(0.1)  # (0,1 s después del pulso 2,9)
    assert grid_offset(0.1, 2.3, 100, 1.0, 0.5) == pytest.approx(0.2)  # (antes del primero: la rejilla sigue, -0,1)
    assert grid_offset(2.3, 2.3, 100, 1.0, 0.5) == 0.0
    # A 0,5× la grabación se oye el doble: 0,3 s son 0,6 oídos, más de lo que cabe; entra 0,3 s después del 1,7
    assert grid_offset(2.0, 2.3, 100, 0.5, 0.5) == pytest.approx(0.3)


def test_first_beat(window, app, wav, monkeypatch):
    """Count-in > The first beat is here (or the right click on the waveform): a bookmark of its own, one per file,
    kept with the others; the count-in brings the recording in on the nearest beat of its grid, wherever it is
    played from. Removed, the count-in goes back to the offset of its settings."""
    window.a_ask_save.setChecked(False)  # (lo que se hace se guarda en el momento)
    loaded(window, app, wav)
    menu = {a.text(): a.menu() for a in window.menuBar().actions()}["&Count-in"]
    assert window.a_first_beat in menu.actions() and window.a_no_first_beat in menu.actions()
    assert window.a_first_beat.isEnabled() and not window.a_no_first_beat.isEnabled()
    window.count.bpm = 100  # (un pulso cada 0,6 s)
    window.seek(2.0)
    window.wave.firstBeatRequested.emit(2.3)  # (el menú del clic derecho, sobre 2,3 s)
    assert [(b.time, b.label, b.first_beat) for b in window.bookmarks] == [(2.3, "First beat", True)]
    assert window.count.on and window.a_count.isChecked() and window.a_no_first_beat.isEnabled()
    assert "first beat at 0:02.3" in window.statusBar().currentMessage()
    assert "on the beats of the first beat (0:02.3)" in window.a_count.statusTip()
    assert window.store.bookmarks(wav)[0].first_beat  # (guardado, con los marcadores)
    assert window.count_offset() == pytest.approx(-0.3)
    window._tick()
    assert window.wave.first_beat == pytest.approx(2.3)  # (la línea, donde entra la grabación)
    window.grab()
    calls = []
    monkeypatch.setattr(window.player, "play", lambda *args: calls.append(args))
    window.toggle()
    assert calls == [(4, 100.0, pytest.approx(-0.3))]
    # Lejos del primer pulso, en el más cercano de la rejilla: 2,9
    window.seek(3.0)
    assert window.count_offset() == pytest.approx(0.1)
    window.count.offset = 0.7  # (el desfase de los ajustes no cuenta mientras haya un primer pulso)
    window.seek(4.1)
    assert window.count_offset() == pytest.approx(0.0)
    window._tick()
    assert window.wave.first_beat is None  # (en el pulso: sin línea aparte)
    # En la posición, con el menú: se mueve (hay uno solo)
    window.seek(1.0)
    window.a_first_beat.trigger()
    assert [(b.time, b.first_beat) for b in window.bookmarks] == [(1.0, True)]
    # Sobre un marcador que ya estaba: se vuelve el primer pulso, con su nombre
    window.add_bookmark_at(4.0)
    window._renamed(1, "Chorus")
    window.wave.firstBeatRequested.emit(4.02)
    assert [(b.time, b.label, b.first_beat) for b in window.bookmarks] == [(4.0, "Chorus", True)]
    # Al cerrar y abrir, sigue allí (y la cuenta, aunque esté apagada, guarda su tempo)
    window.a_count.setChecked(False)
    window.close_file()
    window.count.bpm = 80
    loaded(window, app, wav)
    assert window.first_beat().time == 4.0 and window.count.bpm == 100 and not window.count.on
    window.a_no_first_beat.trigger()
    assert window.first_beat() is None and window.bookmarks == [] and not window.a_no_first_beat.isEnabled()
    assert window.count_offset() == pytest.approx(0.7)


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


def test_hearing_in_the_window(window, app, wav, tmp_path):
    """Hear > a channel and a filter: the player hears them, the button says them, and they are remembered; a mono
    file has no channels to choose."""
    loaded(window, app, wav)
    window.a_channels["left"].trigger()
    window.a_filters["bass"].trigger()
    assert window.player.hearing == ("left", "bass")
    assert window.a_channels["left"].isChecked() and window.a_filters["bass"].isChecked()
    assert window.settings.value("hearing/channels") == "left"
    window.a_channels["both"].trigger()
    window.a_filters["none"].trigger()
    assert window.a_channels["both"].isChecked()
    from conftest import tone, write

    mono = tmp_path / "mono.wav"
    write(mono, tone(2.0, channels=1))
    loaded(window, app, mono)
    assert not window.a_channels["left"].isEnabled() and window.a_filters["bass"].isEnabled()


def test_export_the_audio(window, app, wav, tmp_path, monkeypatch):
    """File > Export the audio: the selection, at the speed and pitch chosen, as it is heard, into the file named."""
    from py_slowdown import exportdialog, window as window_module
    from py_slowdown.audio import Audio

    loaded(window, app, wav)
    window.set_speed(0.5)
    window.set_selection((1.0, 3.0))
    window.a_filters["bass"].trigger()
    chosen = {}

    def accept(dialog):
        chosen["sound"] = dialog.sound.text()
        chosen["hearing"] = dialog.hearing.isChecked()
        dialog.format.setCurrentIndex(dialog.format.findData("flac"))
        return True

    monkeypatch.setattr(exportdialog.ExportDialog, "exec", accept)
    out = tmp_path / "slow.flac"
    monkeypatch.setattr(window_module.QFileDialog, "getSaveFileName",
                        lambda *args, **kwargs: (str(out), ""))
    window.export_audio()
    assert chosen == {"sound": "At 0.5×, at the pitch of the recording.", "hearing": True}
    assert out.exists() and window.settings.value("export/format") == "flac"
    again = Audio(out)
    again.wait(10)
    assert abs(again.duration - 4.0) < 0.05  # (dos segundos a 0,5×)
    again.close()
    assert exportdialog.suggested_name(wav, 0.75, -2.0, "mp3") == "clicks (0.75×, −2 st).mp3"


def test_loops_in_the_window(window, app, wav):
    """Save the selection as a loop, name it, and later repeat it with a double click; it is there when the file is
    opened again."""
    window.a_ask_save.setChecked(False)  # (lo que se hace se guarda en el momento)
    loaded(window, app, wav)
    assert not window.a_save_loop.isEnabled()
    window.set_selection((1.0, 2.5))
    window.save_loop()
    window.loop_panel._filling = False
    window.loop_panel.table.item(0, 2).setText("Riff")
    assert [(x.start, x.end, x.label) for x in window.loops] == [(1.0, 2.5, "Riff")]
    window.save_loop()  # (la misma: no se repite)
    assert len(window.loops) == 1
    window.set_selection(None)
    window.a_repeat.setChecked(False)
    window.repeat_loop(0)
    assert window.selection == (1.0, 2.5) and window.a_repeat.isChecked() and window.player.loop == (1.0, 2.5)
    window.close_file()
    loaded(window, app, wav)
    assert [x.label for x in window.loops] == ["Riff"] and window.loop_panel.table.rowCount() == 1
    window.remove_loop(0)
    assert window.loops == [] and window.store.loops(wav) == []


def test_settings_of_each_file(window, app, wav, tmp_path):
    """The speed, the pitch, the formants, how it is heard, the selection repeated and the count-in of a file come
    back when it is opened again; a file with nothing kept starts from the usual ones."""
    from conftest import tone, write

    loaded(window, app, wav)
    window.set_speed(0.6)
    window.set_pitch(-3.0)
    window.a_formants.setChecked(True)
    window.set_hearing("mono", "no_bass")
    window.set_selection((1.0, 2.0))
    window.a_repeat.setChecked(True)
    window.count.bpm = 88
    window.count.offset = 0.25
    window.a_count.setChecked(True)
    other = tmp_path / "other.wav"
    write(other, tone(3.0))
    loaded(window, app, other)  # (nada guardado: lo de siempre, no lo del anterior)
    assert window.player.speed == 1.0 and window.player.hearing == ("both", "none") and window.count.bpm == 100
    window.set_speed(1.0)
    window.set_pitch(0.0)
    window.a_formants.setChecked(False)
    window.set_hearing("both", "none")
    window.a_count.setChecked(False)
    window.count.bpm = 120
    window.close_file()
    assert window.store.settings(other) == {}  # (lo de siempre no se guarda)
    loaded(window, app, wav)
    window._tick()
    assert (window.player.speed, window.player.pitch, window.player.formants) == (0.6, -3.0, True)
    assert window.player.hearing == ("mono", "no_bass") and window.a_channels["mono"].isChecked()
    assert window.selection == (1.0, 2.0) and window.a_repeat.isChecked() and window.player.loop == (1.0, 2.0)
    assert (window.count.on, window.count.bpm, window.count.offset) == (True, 88, 0.25)


def test_keyboard_shortcuts(window, app, monkeypatch, tmp_path, output):
    """Settings > Keyboard shortcuts: new keys for an action are used, kept, and there the next time; keys given to
    two actions are refused; the defaults come back; Help shows the keys as they are."""
    from PySide6.QtGui import QKeySequence

    from py_slowdown import shortcuts

    assert shortcuts.clashes(window.default_shortcuts) == []  # (las de siempre no chocan)
    dialog = shortcuts.ShortcutsDialog(window.shortcut_actions, window.default_shortcuts, window)
    dialog.edits["a_mark"].setKeySequence(QKeySequence("M"))
    dialog.edits["a_tap"].setKeySequence(QKeySequence("F5"))
    dialog.accept()
    assert dialog.result() == 1
    shortcuts.save(window.shortcut_actions, window.default_shortcuts, window.settings)
    assert window.a_mark.shortcuts() == [QKeySequence("M")]  # (cambiada: solo la nueva)
    assert window.a_slower.shortcuts() == [QKeySequence("Down"), QKeySequence("-")]  # (sin cambiar: las dos)
    assert ("Add a bookmark", "M") in window.current_shortcut_rows()
    assert window.settings.value("shortcuts/a_mark") in ("M", ["M"]) and window.settings.value("shortcuts/a_play") is None

    # Otra ventana, con la misma configuración
    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    from py_slowdown.engine import Player
    from py_slowdown.window import Window

    again = Window(player=Player(output), store=window.store, settings=window.settings)
    assert again.a_tap.shortcuts() == [QKeySequence("F5")]
    clash = shortcuts.ShortcutsDialog(again.shortcut_actions, again.default_shortcuts, again)
    clash.edits["a_stop"].setKeySequence(QKeySequence("F5"))
    warned = []
    monkeypatch.setattr(shortcuts.QMessageBox, "warning", lambda *args: warned.append(args[2]))
    clash.accept()
    assert warned and "Tap the tempo" in warned[0] and again.a_stop.shortcuts() == [QKeySequence("S")]
    clash.restore_defaults()
    clash.accept()
    shortcuts.save(again.shortcut_actions, again.default_shortcuts, again.settings)
    assert again.a_tap.shortcuts() == [QKeySequence("T")] and again.settings.value("shortcuts/a_tap") is None
    again.close()


def test_playback_quality(window, app, wav):
    """Settings > Playback quality: the player stretches with it, and it is remembered."""
    loaded(window, app, wav)
    assert window.player.quality == "high" and window.a_qualities["high"].isChecked()
    window.a_qualities["r2"].trigger()
    assert window.player.quality == "r2" and window.settings.value("quality") == "r2"


def test_parse_speeds():
    from py_slowdown.window import parse_speeds

    assert parse_speeds("50, 75%, 100,125") == [50, 75, 100, 125]
    assert parse_speeds("100 50; 50") == [50, 100]  # (en orden, cada una una vez)
    assert parse_speeds("20, 100") is None and parse_speeds("301") is None  # (fuera de 25 a 300)
    assert parse_speeds("75.5") is None and parse_speeds("fast") is None and parse_speeds(" , ") is None


def test_speed_presets(window, app, wav, monkeypatch):
    """The button Speeds: its speeds, the one playing ticked; one chosen is the speed; the list is changed, kept
    and restored; the slider stays."""
    from py_slowdown import window as window_module

    loaded(window, app, wav)
    assert window.b_speeds.menu() is window.speed_menu and window.speed_knob.isVisible()
    playback = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Playback")
    assert window.speed_menu.menuAction() in playback.actions()  # (también en Reproducción)
    window._fill_speed_menu()
    speeds = [a for a in window.speed_menu.actions() if a.isCheckable()]
    assert [a.text() for a in speeds] == ["50%", "60%", "70%", "75%", "80%", "90%", "100%", "110%", "125%", "150%"]
    assert next(a for a in speeds if a.text() == "100%").isChecked()
    next(a for a in speeds if a.text() == "75%").trigger()
    assert window.player.speed == 0.75 and window.speed_knob.value() == 75
    monkeypatch.setattr(window_module.QInputDialog, "getText", lambda *args, **kwargs: ("40, 85%, 120", True))
    window.edit_speed_presets()
    assert window.speed_presets() == [40, 85, 120]
    window._fill_speed_menu()
    assert [a.text() for a in window.speed_menu.actions() if a.isCheckable()] == ["40%", "85%", "120%"]
    warned = []
    monkeypatch.setattr(window_module.QInputDialog, "getText", lambda *args, **kwargs: ("10, 500", True))
    monkeypatch.setattr(window_module.QMessageBox, "warning", lambda *args: warned.append(args))
    window.edit_speed_presets()
    assert warned and window.speed_presets() == [40, 85, 120]  # (lo que no sirve no se guarda)
    window.restore_speed_presets()
    assert window.speed_presets() == list(window_module.SPEED_PRESETS)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_each_menu_letter_once(app, output, tmp_path, monkeypatch, lang):
    """In each menu, in both languages, no two entries share the letter of Alt (the one after &)."""
    import re

    from PySide6.QtCore import QSettings

    monkeypatch.setattr("py_slowdown.window.Output", type(output))
    interface.use(lang)
    try:
        w = Window(player=Player(output), store=Store(tmp_path / "b.json"),
                   settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
        w._fill_speed_menu()
        menus = [("bar", w.menuBar())]
        clashes = []
        while menus:
            name, menu = menus.pop()
            letters: dict[str, list[str]] = {}
            for action in menu.actions():
                if action.menu() is not None:
                    menus.append((action.text(), action.menu()))
                found = re.search(r"&([^&])", action.text().replace("&&", ""))
                if found:
                    letters.setdefault(found.group(1).lower(), []).append(action.text())
            clashes += [(name, texts) for texts in letters.values() if len(texts) > 1]
        assert clashes == []
        w.close()
    finally:
        interface.use("en")


def test_formants_only_with_the_pitch_moved(window, app, wav):
    """Formants (only in the menu, Playback > Keep the formants: no button) can be chosen only when the pitch is
    moved; at 0 it is greyed out but keeps its state; a button that is on is drawn filled (the theme's
    highlight)."""
    loaded(window, app, wav)
    assert not hasattr(window, "b_formants") and "timbre" in window.a_formants.statusTip()
    assert not window.a_formants.isEnabled()
    window.set_pitch(3.0)
    assert window.a_formants.isEnabled()
    window.a_formants.trigger()
    window.set_pitch(0.0)
    assert not window.a_formants.isEnabled() and window.a_formants.isChecked() and window.player.formants
    assert "QToolButton:checked" in window.transport.styleSheet()


def test_the_speed_knob(window, app, wav):
    """The speed is a knob with 100% straight up: 25% to 100% on its left half, 100% to 300% on its right; the
    pointer follows the mouse on that uneven scale; the wheel moves it by 5%; a double click goes back to 100%."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QWheelEvent

    loaded(window, app, wav)
    knob = window.speed_knob
    assert knob.degrees(100) == 90.0 and knob.degrees(25) == 240.0 and knob.degrees(300) == -60.0
    assert knob.degrees(50) == pytest.approx(190.0)  # (un tercio de la mitad izquierda)
    middle = knob.width() / 2
    assert knob.value_at(middle, 2) == 100  # (arriba)
    assert knob.value_at(middle + 20, middle) == 220  # (a la derecha, a 0°: 100 + 200·90/150)
    assert knob.value_at(middle - 20, middle) == 55  # (a la izquierda, a 180°: 25 + 75·60/150)
    assert knob.value_at(middle - 5, middle + 30) == 25 and knob.value_at(middle + 5, middle + 30) == 300  # (abajo)

    def wheel(dy):
        here = QPointF(18, 18)
        app.sendEvent(knob, QWheelEvent(here, knob.mapToGlobal(here), QPoint(), QPoint(0, dy),
                                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                        Qt.ScrollPhase.NoScrollPhase, False))

    wheel(-120)
    assert window.player.speed == 0.95 and knob.text() == "95%"
    here = QPointF(middle - 20, middle)
    app.sendEvent(knob, QMouseEvent(QMouseEvent.Type.MouseButtonPress, here, knob.mapToGlobal(here),
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert window.player.speed == 0.55
    app.sendEvent(knob, QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, here, knob.mapToGlobal(here),
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert window.player.speed == 1.0


def test_repeat_the_whole_file(window, app, wav, tmp_path):
    """Repeat without a selection repeats the whole file, once it is read (its end is known); kept with the file."""
    from py_slowdown import sidecar

    window.a_ask_save.setChecked(False)
    assert window.open_file(wav)
    window.a_repeat.setChecked(True)
    if not window.audio.done:
        assert window.player.loop is None  # (todavía se lee: no se sabe dónde termina)
    window.audio.wait(10)
    window._tick()
    assert window.player.loop == pytest.approx((0.0, 6.0)) and window.selection is None
    window.close_file()
    assert window.store.settings(wav)["repeat"] is True and "selection" not in window.store.settings(wav)
    assert sidecar.read(sidecar.find(wav)).settings["repeat"] is True
    loaded(window, app, wav)
    assert window.a_repeat.isChecked() and window.player.loop == pytest.approx((0.0, 6.0))


def test_the_arrow_of_save(window, app, wav, tmp_path, monkeypatch):
    """The question before closing a file with changes: its Save has an arrow with three choices. Always for this
    recording saves now and from then on as things are done, without asking; Never for this recording saves
    nothing of it again (the title says so); Always for all recordings turns Ask to save off. Settings > Changes
    of this recording shows the recording's choice and takes it back."""
    from py_slowdown import sidecar
    from py_slowdown.window import SaveDialog
    from conftest import tone, write

    dialog = SaveDialog("song.mp3", window)
    menu = dialog.save.menu()
    assert dialog.save.popupMode() == dialog.save.ToolButtonPopupMode.MenuButtonPopup
    assert [a.text() for a in menu.actions()] == ["Always save, for this &recording", "Always save, for &all recordings",
                                                  "&Never save this recording's changes"]
    dialog.a_never_file.trigger()
    assert dialog.answer == "never_file" and dialog.result() == 1
    dialog.close()

    answers = []
    monkeypatch.setattr(Window, "_ask_save", lambda self, name: answers.pop(0))
    loaded(window, app, wav)
    assert window.file_saving_menu.isEnabled() and window.a_file_saving[""].isChecked()
    window.add_bookmark_at(1.0)
    answers.append("always_file")
    window.close_file()
    assert window.store.saving(wav) == "always" and [b.time for b in window.store.bookmarks(wav)] == [1.0]
    loaded(window, app, wav)
    assert window.a_file_saving["always"].isChecked()
    window.add_bookmark_at(2.0)  # (guardado al hacerlo, sin preguntar)
    assert [b.time for b in sidecar.read(sidecar.find(wav)).bookmarks] == [1.0, 2.0] and not window._changed()
    window.close_file()  # (sin respuestas: no pregunta)

    other = tmp_path / "other.wav"
    write(other, tone(2.0))
    loaded(window, app, other)
    assert window.a_file_saving[""].isChecked()  # (la elección es de cada grabación)
    window.add_bookmark_at(0.5)
    answers.append("never_file")
    window.close_file()
    assert window.store.saving(other) == "never" and window.store.bookmarks(other) == []
    loaded(window, app, other)
    assert "(changes not saved)" in window.windowTitle() and window.a_file_saving["never"].isChecked()
    window.add_bookmark_at(0.7)
    assert not window._changed()
    window.close_file()  # (no pregunta, y no guarda)
    assert window.store.bookmarks(other) == []
    loaded(window, app, other)
    window.a_file_saving[""].trigger()  # (como en todas: vuelve a preguntar)
    assert window.store.saving(other) == "" and "(changes not saved)" not in window.windowTitle()
    window.add_bookmark_at(0.9)
    answers.append("always_all")
    window.close_file()
    assert not window.a_ask_save.isChecked() and [b.time for b in window.store.bookmarks(other)] == [0.9]
    assert answers == [] and not window.file_saving_menu.isEnabled()


def test_the_equalizer(window, app, wav):
    """The button EQ (and Hear > Equalizer) opens the equalizer: its five knobs change the sound as they turn, On
    hears it with or without them, Flat takes them all back to 0; the button is on while the equalizer changes the
    sound; the bands are kept with the file (in its .slx too) and a new file starts flat."""
    from py_slowdown import sidecar
    from py_slowdown.window import EqualizerPanel

    loaded(window, app, wav)
    assert not window.b_eq.isChecked() and window.player.eq == (0, 0, 0, 0, 0)
    window.b_eq.click()
    dialog = window.eq_panel
    assert isinstance(dialog, EqualizerPanel) and window.sound_dock.isVisible() and not window.b_eq.isChecked()
    assert [k.text() for k in dialog.knobs] == ["0 dB"] * 5 and dialog.on.isChecked()
    dialog.knobs[0].setValue(4)
    dialog.knobs[4].setValue(-6)
    assert window.player.eq == (4, 0, 0, 0, -6) and window.b_eq.isChecked() and "12 kHz -6" in window.b_eq.toolTip()
    dialog.on.setChecked(False)  # (sin él, para comparar: las perillas se quedan)
    assert window.player.eq == (0, 0, 0, 0, 0) and not window.b_eq.isChecked() and dialog.knobs[0].value() == 4
    dialog.on.setChecked(True)
    window._apply_file_settings({})
    kept = window._file_settings()
    assert kept["eq"] == [4, 0, 0, 0, -6] and "eq_on" not in kept
    window.close_file()
    assert sidecar.read(sidecar.find(wav)).settings["eq"] == [4, 0, 0, 0, -6]
    window.set_eq((1, 1, 1, 1, 1))
    loaded(window, app, wav)
    assert window.player.eq == (4, 0, 0, 0, -6) and [k.value() for k in dialog.knobs] == [4, 0, 0, 0, -6]
    dialog.flatten()
    assert window.player.eq == (0, 0, 0, 0, 0) and not window.b_eq.isChecked()
    menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "H&ear")
    assert window.a_equalizer in menu.actions()
    dialog.close()


def test_the_drawn_icons(window, app):
    """The buttons (playing, repeat, Bookmark, Speeds, EQ) and the speaker show icons of the program's own
    (glyphs.py), drawn in the theme's button text, also a dark one, and in the text on the selection when a button
    is on."""
    from PySide6.QtGui import QColor, QIcon, QPalette

    from py_slowdown import glyphs

    for button in (window.b_mark, window.b_speeds, window.b_eq):
        assert not button.icon().isNull() and button.toolButtonStyle() == button.toolButtonStyle().ToolButtonIconOnly
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(236, 239, 244))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 0, 0))
    icon = glyphs.icon("equalizer", palette)

    def colours(state):
        image = icon.pixmap(48, 48, QIcon.Mode.Normal, state).toImage()
        return {image.pixelColor(x, y).name() for x in range(48) for y in range(48) if image.pixelColor(x, y).alpha() == 255}

    assert colours(QIcon.State.Off) == {"#eceff4"} and colours(QIcon.State.On) == {"#ff0000"}
    assert set(glyphs.SHAPES) == {"equalizer", "bookmark", "speed", "play", "pause", "stop", "start", "end", "back",
                                  "forward", "repeat", "volume"}
    for button in (window.b_start, window.b_back, window.b_play, window.b_stop, window.b_forward, window.b_end,
                   window.b_repeat):
        assert not button.icon().isNull()
    assert not window.speaker.pixmap().isNull()


def test_play_and_pause_icons(window, app, wav, output):
    """The button Play shows a triangle, and two bars while it plays."""
    loaded(window, app, wav)
    still = window.b_play.icon().pixmap(24, 24).toImage()
    window.toggle()
    playing = window.b_play.icon().pixmap(24, 24).toImage()
    assert window.player.playing and still != playing
    window.toggle()
    assert window.b_play.icon().pixmap(24, 24).toImage() == still


def test_reset_the_sound(window, app, wav):
    """Playback > Reset the sound (Ctrl+Shift+N): speed 100%, the recording's pitch, the formants off, both channels
    without a filter, the equalizer flat; the volume stays."""
    loaded(window, app, wav)
    window.set_speed(0.6)
    window.set_pitch(-2.3)
    window.a_formants.setChecked(True)
    window.set_hearing("left", "bass")
    window.set_eq((3, 0, 0, 0, -3), False)
    window.volume.setValue(70)
    assert window.a_reset_sound.shortcut().toString() == "Ctrl+Shift+N"
    window.a_reset_sound.trigger()
    player = window.player
    assert (player.speed, player.pitch, player.formants, player.hearing) == (1.0, 0.0, False, ("both", "none"))
    assert player.eq == (0, 0, 0, 0, 0) and window.eq_gains == (0, 0, 0, 0, 0) and window.eq_on
    assert window.volume.value() == 70


def test_values_shown_on_the_waveform(window, app, wav):
    """A speed or a pitch changed from the keyboard (or a speed of the menu) is shown large on the waveform for a
    moment, then goes; one turned on its knob is not (the knob shows it)."""
    import time as clock

    loaded(window, app, wav)
    window.speed_knob.setValue(80)
    assert window.wave.flash is None
    window.a_slower.trigger()
    assert window.wave.flash == "75%"
    window.a_higher.trigger()
    assert window.wave.flash == "+1 st  0 ¢"
    window.wave.grab()  # (se dibuja sin errores)
    end = clock.time() + 2.5
    while window.wave.flash is not None and clock.time() < end:
        app.processEvents()
        clock.sleep(0.02)
    assert window.wave.flash is None


def test_loops_on_the_waveform(window, app, wav):
    """The saved loops are bands of colour at the foot of the waveform, with their names; a click on one selects
    it, repeats it and goes to its start."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from py_slowdown.bookmarks import Loop
    from py_slowdown.waveform import LANE

    loaded(window, app, wav)
    window.loops = [Loop(1.0, 2.0, "Intro"), Loop(3.0, 5.0, "Riff")]
    window._show_loops()
    wave = window.wave
    assert [x.label for x in wave.loops] == ["Intro", "Riff"]
    y = wave.height() - LANE // 2
    assert wave.loop_at(wave.x_of(4.0), y) == 1 and wave.loop_at(wave.x_of(4.0), 40) is None
    wave.grab()
    QTest.mouseClick(wave, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(wave.x_of(4.0)), y))
    assert window.selection == (3.0, 5.0) and window.a_repeat.isChecked() and window.player.loop == (3.0, 5.0)
    window.remove_loop(0)
    assert [x.label for x in wave.loops] == ["Riff"]


def test_speed_knob_detents(window, app, monkeypatch):
    """Dragged, the speed knob stops at the speeds chosen beforehand when it passes within a few degrees of one;
    the detents follow the list when it changes."""
    from py_slowdown import window as window_module

    knob = window.speed_knob
    assert knob.detents == window_module.SPEED_PRESETS
    import math

    def point(value):
        # Un punto en la dirección de VALUE, a 20 píxeles del centro
        angle = math.radians(knob.degrees(value))
        return knob.width() / 2 + 20 * math.cos(angle), knob.height() / 2 - 20 * math.sin(angle)

    assert knob.dragged_to(*point(77)) == 75  # (cerca de 75: se queda allí)
    assert knob.dragged_to(*point(84)) == 84  # (lejos de 80 y de 90: donde está)
    monkeypatch.setattr(window_module.QInputDialog, "getText", lambda *args, **kwargs: ("65, 100", True))
    window.edit_speed_presets()
    assert knob.detents == (65, 100) and knob.dragged_to(*point(77)) == 77
    window.restore_speed_presets()
    assert knob.detents == window_module.SPEED_PRESETS


def test_the_menus_of_the_knobs(window, app, wav, monkeypatch):
    """A right click on a knob: back to its usual value, and its usual values (the one now ticked); one chosen is
    set as if the knob had been turned there."""
    loaded(window, app, wav)
    assert window.speed_knob.menu_values() == list(window.speed_presets())
    assert window.semitone_dial.menu_values() == [-12, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 12]
    assert window.cent_dial.menu_values() == [-50, -25, -10, -5, 0, 5, 10, 25, 50]
    assert window.volume.menu_values() == [0, 25, 50, 75, 100]
    menu = window.semitone_dial.knob_menu()
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts[0] == "Back to 0 st" and [a.text() for a in menu.actions() if a.isChecked()] == ["0 st"]
    next(a for a in menu.actions() if a.text() == "+5 st").trigger()
    assert window.player.pitch == 5.0


def test_knobs_with_the_keyboard(window, app, wav):
    """A knob is reached with Tab; with the focus, the arrows move it a step (not the window's shortcuts), Page
    Up and Down more, Home back to its usual value; the pointer over it is a hand, and its rim lights up."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    loaded(window, app, wav)
    knob = window.speed_knob
    assert knob.focusPolicy() == Qt.FocusPolicy.TabFocus and knob.cursor().shape() == Qt.CursorShape.PointingHandCursor
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    override.ignore()
    knob.event(override)
    assert override.isAccepted()  # (la flecha es de la perilla)
    ctrl = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    ctrl.ignore()
    knob.event(ctrl)
    assert not ctrl.isAccepted()  # (Ctrl+↑ sigue siendo de la ventana)
    for key, speed in ((Qt.Key.Key_Down, 0.95), (Qt.Key.Key_PageDown, 0.7), (Qt.Key.Key_Up, 0.75),
                       (Qt.Key.Key_Home, 1.0)):
        knob.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        assert window.player.speed == speed
    plain = knob.grab().toImage()
    knob.setFocus()
    app.processEvents()
    if knob.hasFocus():  # (fuera de la pantalla, el foco depende de la plataforma)
        assert knob.grab().toImage() != plain


def test_the_equalizer_curve_and_presets(window, app, wav, monkeypatch):
    """The equalizer draws its curve, and has presets: its own (for music), and the user's, saved by name and
    removed again; one chosen sets the knobs and the sound."""
    from py_slowdown import window as window_module

    loaded(window, app, wav)
    window.show_equalizer()
    dialog = window.eq_panel
    dialog.knobs[0].setValue(6)
    assert dialog.curve.gains == (6, 0, 0, 0, 0) and dialog.curve.on
    dialog.curve.grab()
    dialog._fill_presets()
    names = [a.text() for a in dialog.presets.menu().actions() if a.text()]
    assert names[:3] == ["Flat", "Bass up", "Hear the bass line"] and "&Save as preset…" in names
    next(a for a in dialog.presets.menu().actions() if a.text() == "Cut the hiss").trigger()
    assert window.player.eq == (0, 0, 0, -2, -8) and [k.value() for k in dialog.knobs] == [0, 0, 0, -2, -8]
    monkeypatch.setattr(window_module.QInputDialog, "getText", lambda *args, **kwargs: ("My bass", True))
    dialog.save_preset()
    assert dialog.own_presets() == {"My bass": [0, 0, 0, -2, -8]}
    dialog._fill_presets()
    assert "My bass" in [a.text() for a in dialog.presets.menu().actions()]
    dialog.remove_preset("My bass")
    assert dialog.own_presets() == {}
    dialog.close()


def test_the_overview_strip(window, app, wav):
    """Zoomed in, a strip above the waveform shows the whole file, the part in view shaded; a click there moves the
    view to that point (not the position); the whole file again, the strip goes."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    loaded(window, app, wav)
    overview = window.view.overview
    assert overview.isHidden()
    window.wave.zoom(4.0, 0)
    app.processEvents()
    assert overview.isVisible()
    overview.grab()
    position = window.player.position
    QTest.mouseClick(overview, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(overview.width() * 3 // 4, overview.height() // 2))
    middle = (window.wave.start + window.wave.visible_frames() / 2) / window.audio.rate
    assert middle == pytest.approx(4.5, abs=0.1) and window.player.position == position
    window.wave.fit()
    window.view._update_bar()
    assert overview.isHidden()


def test_the_clock_switches(window, app, wav):
    """A click on the time switches it: elapsed, remaining, and, with a first beat, bars and beats (from the
    count-in's tempo and clicks); remembered."""
    from py_slowdown.window import bar_and_beat

    assert bar_and_beat(1.0, 1.0, 120, 4) == (1, 1) and bar_and_beat(3.0, 1.0, 120, 4) == (2, 1)
    assert bar_and_beat(3.6, 1.0, 120, 4) == (2, 2) and bar_and_beat(0.5, 1.0, 120, 4) is None
    loaded(window, app, wav)
    window.seek(2.0)
    assert window.time_label.text() == "0:02.0 / 0:06.0"
    window.time_label.clicked.emit()
    assert window.time_label.text() == "−0:04.0 / 0:06.0" and window.settings.value("clock") == "remaining"
    window.time_label.clicked.emit()
    assert window.settings.value("clock") == "elapsed"  # (sin primer pulso, no hay compases)
    window.count.bpm, window.count.beats = 120, 4
    window.set_first_beat(1.0)
    window.time_label.clicked.emit()
    window.time_label.clicked.emit()
    assert window.settings.value("clock") == "bars"
    window._tick()
    assert window.time_label.text() == "Bar 1 · beat 3"  # (2 s, un segundo después del primer pulso, a 120)


def test_the_sound_panel(window, app, wav, tmp_path):
    """The panel Sound, at the side, hidden at first: the channels and the filter (as the menu Hear, the two always
    agreeing) and the equalizer; the button EQ and Hear > Equalizer show it, and View > Sound too."""
    from conftest import tone, write

    loaded(window, app, wav)
    panel = window.sound_panel
    assert window.sound_dock.isHidden()
    window.a_equalizer.trigger()
    assert window.sound_dock.isVisible()
    panel.channels.setCurrentIndex(panel.channels.findData("left"))
    panel.filter.setCurrentIndex(panel.filter.findData("bass"))
    assert window.player.hearing == ("left", "bass") and window.a_channels["left"].isChecked()
    window.a_channels["mono"].trigger()
    assert panel.channels.currentData() == "mono"  # (el menú y el panel, de acuerdo)
    view = next(a.menu() for a in window.menuBar().actions() if a.text() == "&View")
    assert window.sound_dock.toggleViewAction() in view.actions()
    mono = tmp_path / "mono.wav"
    write(mono, tone(2.0, channels=1))
    loaded(window, app, mono)
    assert not panel.channels.isEnabled()


def test_compact_mode(window, app, wav):
    """View > Compact mode (Ctrl+Shift+M): only the controls and a short waveform, without the side panels and the
    status bar, on top of other windows; off, the window as it was; closed while compact, the window before is
    the one remembered."""
    from PySide6.QtCore import Qt

    loaded(window, app, wav)
    window.show_equalizer()
    app.processEvents()
    before = window.size()
    window.a_compact.trigger()
    app.processEvents()
    assert window.dock.isHidden() and window.sound_dock.isHidden() and window.statusBar().isHidden()
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint and window.height() < before.height()
    assert window.a_compact.shortcut().toString() == "Ctrl+Shift+M"
    window.a_compact.trigger()
    app.processEvents()
    assert not window.dock.isHidden() and not window.sound_dock.isHidden() and not window.statusBar().isHidden()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    window.a_compact.trigger()
    window.close()
    assert window.settings.value("geometry") == window._normal[0]
