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
    window.toggle()  # (otra vez el mismo pasaje)
    play_for(0.5)
    window.toggle()
    assert window.player.position == pytest.approx(1.0)
    # Seguir desde la pausa, como antes; pausar vuelve al principio de siempre
    window.a_continue.trigger()
    assert window.player.playing and window.player.position >= window._paused_at - 0.01
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


def test_volume_up_to_150(window, app, wav, output):
    """The volume goes up to 150%; above 100 (louder than the recording) the slider's filled part and the
    number beside it are red, and the sound is clipped at full scale, never wrapped."""
    import numpy as np

    assert window.volume.maximum() == 150 and window.volume_label.text() == "100%"
    window.volume.setValue(120)
    assert window.player.volume == pytest.approx(1.44) and window.volume_label.text() == "120%"
    assert window.volume.palette().highlight().color().name() == "#c81e1e"
    assert "c81e1e" in window.volume_label.styleSheet() and "distort" in window.volume.toolTip()
    assert window.settings.value("volume", type=int) == 120
    window.volume.setValue(150)
    loaded(window, app, wav)
    window.toggle()
    loudest = 0.0
    for _ in range(300):
        loudest = max(loudest, float(np.abs(output.pull()).max()))
        time.sleep(0.001)
    assert loudest == pytest.approx(1.0)  # (los golpes de 0,9, a 2,25×, recortados en 1)
    window.volume.setValue(80)
    assert window.volume_label.styleSheet() == "" and "distort" not in window.volume.toolTip()
    assert window.volume.palette().highlight().color() == window.palette().highlight().color()


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
    assert window.a_count.isChecked() and window.count.on
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
    assert window.semitone_label.text() == "+1 st" and window.cent_label.text() == "−15 ¢"
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
    assert window.player.pitch == 2.0 and window.semitone_label.text() == "+2 st"
    for _ in range(3):
        wheel(window.cent_dial, -40)  # (tres tercios de muesca: un cent)
    assert window.player.pitch == pytest.approx(1.99) and window.cent_label.text() == "−1 ¢"
    here = QPointF(18, 18)
    app.sendEvent(window.semitone_dial, QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, here,
                                                    window.semitone_dial.mapToGlobal(here),
                                                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                                    Qt.KeyboardModifier.NoModifier))
    assert window.player.pitch == pytest.approx(-0.01) and window.semitone_label.text() == "0 st"


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
    back when it is opened again; a file with nothing kept leaves them as they are."""
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
    loaded(window, app, other)  # (nada guardado: sigue como estaba)
    assert window.player.speed == 0.6 and window.player.hearing == ("mono", "no_bass")
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
    assert window.b_speeds.menu() is window.speed_menu and window.speed_slider.isVisible()
    playback = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Playback")
    assert window.speed_menu.menuAction() in playback.actions()  # (también en Reproducción)
    window._fill_speed_menu()
    speeds = [a for a in window.speed_menu.actions() if a.isCheckable()]
    assert [a.text() for a in speeds] == ["50%", "60%", "70%", "75%", "80%", "90%", "100%", "110%", "125%", "150%"]
    assert next(a for a in speeds if a.text() == "100%").isChecked()
    next(a for a in speeds if a.text() == "75%").trigger()
    assert window.player.speed == 0.75 and window.speed_slider.value() == 75
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
