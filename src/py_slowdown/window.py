"""La ventana principal de py-slowdown.

Arriba, la forma de onda; debajo, los mandos de la reproducción (al principio,
atrás, tocar o pausar, detener, adelante, al final), el tiempo, la velocidad y
el volumen; a la derecha, el panel de los marcadores. Los menús repiten todo eso
con sus atajos de teclado.

La ventana tiene un solo archivo abierto a la vez. Al cerrarlo (o al abrir
otro, o al salir) guarda el punto donde iba, y al volver a abrirlo sigue de allí.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, interface, rubberband
from .audio import EXTENSIONS, Audio, AudioError
from .bookmarks import Bookmark, Store, export_text
from .countin import MAX_OFFSET, CountIn, CountInDialog, TapTempo, number, recording_tempo
from .engine import MAX_PITCH, MAX_SPEED, MIN_LOOP, MIN_SPEED, Output, Player, max_earlier
from .interface import tr
from .panel import BookmarkPanel
from .timefmt import clock
from .waveform import WaveformView

APP = "py-slowdown"
SPEED_STEP = 0.05
SKIPS = (1, 2, 5, 10, 15, 30, 60)
RECENT = 10
ICON = Path(__file__).resolve().parent / "icons" / "py-slowdown.svg"


def shortcut_rows() -> list[tuple[str, str]]:
    """(what, keys) of each keyboard shortcut: for Help > Keyboard shortcuts and the manual page."""
    return [
        (tr("Play or pause"), tr("Space")),
        (tr("Stop and go back to the start"), "S"),
        (tr("Go to the start / to the end"), tr("Home / End")),
        (tr("Back / forward (skip length)"), "← / →"),
        (tr("Back / forward one second"), tr("Shift+← / Shift+→")),
        (tr("Slower / faster"), "↓ / ↑   − / +"),
        (tr("Normal speed"), "N"),
        (tr("A semitone higher / lower"), tr("Ctrl+↑ / Ctrl+↓")),
        (tr("Original pitch"), tr("Shift+N")),
        (tr("Add a bookmark"), "B"),
        (tr("Previous / next bookmark"), tr("Ctrl+← / Ctrl+→   PgUp / PgDn")),
        (tr("Zoom in / out / whole file"), "Ctrl++ / Ctrl+− / Ctrl+0"),
        (tr("Zoom around the pointer"), tr("Ctrl+wheel")),
        (tr("Repeat the selection"), "L"),
        (tr("Select with the mouse"), tr("Shift+drag")),
        (tr("Start / end of the selection at the position"), "I / O"),
        (tr("Clear the selection"), tr("Esc")),
        (tr("Count in before playing"), "C"),
        (tr("Tap the tempo (with the beat)"), "T"),
        (tr("Open a file"), "Ctrl+O"),
    ]


class Window(QMainWindow):
    def __init__(self, player: Player | None = None, store: Store | None = None,
                 settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings(APP, APP)
        self.player = player or Player()
        self.store = store or Store()
        self.audio: Audio | None = None
        self.bookmarks: list[Bookmark] = []
        self._resume = 0.0  # where to go once the file is decoded that far
        self._announced: Audio | None = None  # the file whose end of reading was told
        self.skip = float(self.settings.value("skip", 5, type=float))
        self.count = CountIn.load(self.settings)
        self.tapper = TapTempo()
        self.selection: tuple[float, float] | None = None  # seconds
        self.setWindowTitle(APP)
        if ICON.is_file():
            self.setWindowIcon(QIcon(str(ICON)))
        self.setAcceptDrops(True)

        self.view = WaveformView(self)
        self.wave = self.view.wave
        self.panel = BookmarkPanel(self)
        self._build_transport()
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.transport)
        self.setCentralWidget(central)

        self.dock = QDockWidget(tr("Bookmarks"), self)
        self.dock.setObjectName("bookmarks")
        self.dock.setWidget(self.panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

        self._build_actions()
        self._build_menus()
        self._connect()

        self.timer = QTimer(self)
        self.timer.setInterval(33)  # unas 30 veces por segundo
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 520)
        state = self.settings.value("state")
        if state is not None:
            self.restoreState(state)
        self.volume.setValue(int(self.settings.value("volume", 100, type=int)))
        self._update_enabled()
        self._check_rubberband()
        self.wave.setFocus()

    def _check_rubberband(self) -> None:
        """Without the Rubber Band Library, the files play only at 1× (and the window says why)."""
        try:
            rubberband.library()
        except rubberband.RubberBandError:
            self.stretching = False
            why = tr("The Rubber Band Library is not installed, so the speed stays at 1×.")
            for widget in (self.speed_slider, self.speed_box, self.b_normal, self.pitch_box, self.b_pitch):
                widget.setEnabled(False)
                widget.setToolTip(why)
            for action in (self.a_slower, self.a_faster, self.a_normal, self.a_higher, self.a_lower,
                           self.a_original_pitch):
                action.setEnabled(False)
            self.statusBar().showMessage(why)
        else:
            self.stretching = True

    # --- construcción

    def _tool(self, icon: QStyle.StandardPixmap, tip: str, repeat: bool = False) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(QSize(24, 24))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if repeat:
            # Held down, it keeps jumping: a way to run through the file.
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(400)
            button.setAutoRepeatInterval(120)
        return button

    def _build_transport(self) -> None:
        sp = QStyle.StandardPixmap
        self.transport = QWidget(self)
        # Dos filas: los mandos y el tiempo; debajo, la velocidad, la altura y el volumen (en una sola, la ventana
        # no cabía en una pantalla de 1366 píxeles).
        rows = QVBoxLayout(self.transport)
        rows.setContentsMargins(0, 4, 0, 0)
        rows.setSpacing(2)
        row = QHBoxLayout()
        rows.addLayout(row)
        self.b_start = self._tool(sp.SP_MediaSkipBackward, tr("Go to the start (Home)"))
        self.b_back = self._tool(sp.SP_MediaSeekBackward, "", repeat=True)
        self.b_play = self._tool(sp.SP_MediaPlay, tr("Play (Space)"))
        self.b_play.setIconSize(QSize(32, 32))
        self.b_stop = self._tool(sp.SP_MediaStop, tr("Stop and go back to the start (S)"))
        self.b_forward = self._tool(sp.SP_MediaSeekForward, "", repeat=True)
        self.b_end = self._tool(sp.SP_MediaSkipForward, tr("Go to the end (End)"))
        self.b_mark = QToolButton(self)
        self.b_mark.setText(tr("Bookmark"))
        self.b_mark.setToolTip(tr("Add a bookmark at the current position (B)"))
        self.b_mark.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for b in (self.b_start, self.b_back, self.b_play, self.b_stop, self.b_forward, self.b_end):
            row.addWidget(b)
        row.addSpacing(6)
        row.addWidget(self.b_mark)
        self.b_repeat = QToolButton(self)
        self.b_repeat.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.b_repeat.setCheckable(True)
        self.b_repeat.setAutoRaise(True)
        self.b_repeat.setToolTip(tr("Repeat the selection without a pause (L); Shift+drag on the waveform selects"))
        self.b_repeat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.b_count = QToolButton(self)
        self.b_count.setText(tr("Count-in"))
        self.b_count.setCheckable(True)
        self.b_count.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.b_count.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Un botón partido: el botón enciende o apaga la cuenta; la flecha de al lado abre sus ajustes.
        self.b_count.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.b_tap = QToolButton(self)
        self.b_tap.setText(tr("Tap"))
        self.b_tap.setToolTip(tr("Tap with the beat of the music (T), a few times: the tempo of the count-in is "
                                 "measured"))
        self.b_tap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.b_repeat)
        row.addWidget(self.b_count)
        row.addWidget(self.b_tap)
        row.addSpacing(12)

        self.time_label = QLabel("0:00.0 / 0:00.0", self)
        font = self.time_label.font()
        font.setFamily("monospace")
        font.setStyleHint(font.StyleHint.Monospace)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        self.time_label.setFont(font)
        self.time_label.setToolTip(tr("Position / length"))
        row.addWidget(self.time_label)
        row.addStretch()
        row = QHBoxLayout()
        rows.addLayout(row)

        row.addWidget(QLabel(tr("Speed"), self))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.speed_slider.setRange(round(MIN_SPEED * 100), round(MAX_SPEED * 100))
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(25)
        self.speed_slider.setValue(100)
        self.speed_slider.setMinimumWidth(160)
        self.speed_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_slider.setToolTip(tr("Slower (Down) or faster (Up); the pitch stays the same"))
        self.speed_box = QDoubleSpinBox(self)
        self.speed_box.setRange(MIN_SPEED, MAX_SPEED)
        self.speed_box.setSingleStep(SPEED_STEP)
        self.speed_box.setDecimals(2)
        self.speed_box.setSuffix("×")
        self.speed_box.setValue(1.0)
        self.speed_box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.b_normal = QToolButton(self)
        self.b_normal.setText("1×")
        self.b_normal.setToolTip(tr("Normal speed (N)"))
        self.b_normal.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.speed_slider)
        row.addWidget(self.speed_box)
        row.addWidget(self.b_normal)
        row.addSpacing(8)

        row.addWidget(QLabel(tr("Pitch"), self))
        self.pitch_box = QDoubleSpinBox(self)
        self.pitch_box.setRange(-MAX_PITCH, MAX_PITCH)
        self.pitch_box.setSingleStep(1.0)
        self.pitch_box.setDecimals(1)
        self.pitch_box.setSuffix(tr(" st"))
        self.pitch_box.setValue(0.0)
        self.pitch_box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.pitch_box.setToolTip(tr("The pitch, in semitones, up or down (Ctrl+↑, Ctrl+↓); the speed does not change"))
        self.b_pitch = QToolButton(self)
        self.b_pitch.setText("0")
        self.b_pitch.setToolTip(tr("Original pitch (Shift+N)"))
        self.b_pitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.b_pitch.setEnabled(False)
        row.addWidget(self.pitch_box)
        row.addWidget(self.b_pitch)
        row.addSpacing(12)

        speaker = QLabel(self)
        speaker.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume).pixmap(20, 20))
        row.addWidget(speaker)
        self.volume = QSlider(Qt.Orientation.Horizontal, self)
        self.volume.setRange(0, 100)
        self.volume.setMinimumWidth(70)
        self.volume.setMaximumWidth(110)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.setToolTip(tr("Volume"))
        row.addWidget(self.volume)
        row.addStretch()
        self._update_skip_tips()

    def _action(self, text: str, slot, keys=(), checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if keys:
            action.setShortcuts([QKeySequence(k) for k in keys])
        action.setCheckable(checkable)
        # (los que se marcan, por toggled: así responden también cuando un botón o el programa los cambia)
        (action.toggled if checkable else action.triggered).connect(slot)
        self.addAction(action)  # (los atajos valen aunque la barra de menús esté oculta)
        return action

    def _build_actions(self) -> None:
        a = self._action
        self.a_open = a(tr("&Open…"), self.open_dialog, [QKeySequence.StandardKey.Open])
        self.a_close = a(tr("&Close"), self.close_file, [QKeySequence.StandardKey.Close])
        self.a_quit = a(tr("&Quit"), self.close, [QKeySequence.StandardKey.Quit])
        self.a_play = a(tr("&Play/Pause"), self.toggle, ["Space"])
        self.a_stop = a(tr("&Stop"), self.stop, ["S"])
        self.a_start = a(tr("Go to the s&tart"), lambda: self.seek(0.0), ["Home"])
        self.a_end = a(tr("Go to the &end"), self.go_end, ["End"])
        self.a_back = a(tr("&Back"), lambda: self.jump(-self.skip), ["Left"])
        self.a_forward = a(tr("&Forward"), lambda: self.jump(self.skip), ["Right"])
        self.a_back_1 = a(tr("Back one second"), lambda: self.jump(-1.0), ["Shift+Left"])
        self.a_forward_1 = a(tr("Forward one second"), lambda: self.jump(1.0), ["Shift+Right"])
        self.a_slower = a(tr("S&lower"), lambda: self.change_speed(-SPEED_STEP), ["Down", "-"])
        self.a_faster = a(tr("F&aster"), lambda: self.change_speed(SPEED_STEP), ["Up", "+"])
        self.a_normal = a(tr("&Normal speed"), lambda: self.set_speed(1.0), ["N"])
        self.a_higher = a(tr("A se&mitone higher"), lambda: self.change_pitch(1.0), ["Ctrl+Up"])
        self.a_lower = a(tr("A semitone lo&wer"), lambda: self.change_pitch(-1.0), ["Ctrl+Down"])
        self.a_original_pitch = a(tr("Ori&ginal pitch"), lambda: self.set_pitch(0.0), ["Shift+N"])
        self.a_repeat = a(tr("&Repeat the selection"), self._set_repeat, ["L"], checkable=True)
        self.a_sel_start = a(tr("Select&ion starts here"), lambda: self.mark_selection(start=True), ["I"])
        self.a_sel_end = a(tr("Selection ends &here"), lambda: self.mark_selection(start=False), ["O"])
        self.a_sel_clear = a(tr("Clear the selecti&on"), lambda: self.set_selection(None), ["Esc"])
        self.a_count = a(tr("&Count in before playing"), self._set_count_on, ["C"], checkable=True)
        self.a_count.setChecked(self.count.on)
        self.a_count_settings = a(tr("Co&unt-in settings…"), self.count_settings)
        self.a_count_options = a(tr("&Count-in…"), self.count_settings)  # (el mismo, en Configuración)
        self.a_tap = a(tr("Tap the tempo"), self.tap_tempo, ["T"])
        self.a_mark = a(tr("&Add a bookmark"), self.add_bookmark, ["B", "Ctrl+B"])
        self.a_prev_mark = a(tr("&Previous bookmark"), lambda: self.goto_bookmark(-1), ["Ctrl+Left", "PgUp"])
        self.a_next_mark = a(tr("&Next bookmark"), lambda: self.goto_bookmark(1), ["Ctrl+Right", "PgDown"])
        self.a_export = a(tr("&Export the bookmarks…"), self.export_bookmarks)
        self.a_zoom_in = a(tr("Zoom &in"), lambda: self.wave.zoom(2.0), [QKeySequence.StandardKey.ZoomIn, "Ctrl+="])
        self.a_zoom_out = a(tr("Zoom &out"), lambda: self.wave.zoom(0.5), [QKeySequence.StandardKey.ZoomOut])
        self.a_fit = a(tr("&Whole file"), self.wave.fit, ["Ctrl+0"])
        self.a_follow = a(tr("&Follow the position"), self._set_follow, checkable=True)
        self.a_follow.setChecked(self.settings.value("follow", True, type=bool))
        self.wave.follow = self.a_follow.isChecked()
        self.a_shortcuts = a(tr("&Keyboard shortcuts"), self.show_shortcuts, ["F1"])
        self.a_about = a(tr("&About py-slowdown"), self.about)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file = bar.addMenu(tr("&File"))
        file.addAction(self.a_open)
        self.recent_menu = file.addMenu(tr("Open &recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        file.addAction(self.a_close)
        file.addSeparator()
        file.addAction(self.a_quit)

        play = bar.addMenu(tr("&Playback"))
        for action in (self.a_play, self.a_stop, None, self.a_start, self.a_back, self.a_back_1,
                       self.a_forward_1, self.a_forward, self.a_end, None,
                       self.a_slower, self.a_faster, self.a_normal, None,
                       self.a_higher, self.a_lower, self.a_original_pitch, None,
                       self.a_repeat, self.a_sel_start, self.a_sel_end, self.a_sel_clear, None,
                       self.a_count, self.a_count_settings, self.a_tap):
            play.addSeparator() if action is None else play.addAction(action)

        marks = bar.addMenu(tr("&Bookmarks"))
        for action in (self.a_mark, self.a_prev_mark, self.a_next_mark, None, self.a_export):
            marks.addSeparator() if action is None else marks.addAction(action)

        view = bar.addMenu(tr("&View"))
        for action in (self.a_zoom_in, self.a_zoom_out, self.a_fit, None, self.a_follow):
            view.addSeparator() if action is None else view.addAction(action)
        view.addSeparator()
        view.addAction(self.dock.toggleViewAction())

        settings = bar.addMenu(tr("&Settings"))
        settings.addAction(self.a_count_options)
        settings.addSeparator()
        skips = settings.addMenu(tr("&Skip length"))
        group = QActionGroup(self)
        for seconds in SKIPS:
            action = skips.addAction(tr("{n} s", n=seconds))
            action.setCheckable(True)
            action.setChecked(seconds == self.skip)
            action.triggered.connect(lambda _=False, s=seconds: self._set_skip(s))
            group.addAction(action)
        languages = settings.addMenu(tr("&Language"))
        group = QActionGroup(self)
        chosen = self.settings.value("interface", "")
        for code, name in interface.names().items():
            action = languages.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == (chosen or interface.current()))
            action.triggered.connect(lambda _=False, c=code: self._set_language(c))
            group.addAction(action)

        help_ = bar.addMenu(tr("&Help"))
        help_.addAction(self.a_shortcuts)
        help_.addAction(self.a_about)

    def _connect(self) -> None:
        self.b_play.clicked.connect(self.toggle)
        self.b_stop.clicked.connect(self.stop)
        self.b_start.clicked.connect(lambda: self.seek(0.0))
        self.b_end.clicked.connect(self.go_end)
        self.b_back.clicked.connect(lambda: self.jump(-self.skip))
        self.b_forward.clicked.connect(lambda: self.jump(self.skip))
        self.b_mark.clicked.connect(self.add_bookmark)
        self.b_normal.clicked.connect(lambda: self.set_speed(1.0))
        self.b_pitch.clicked.connect(lambda: self.set_pitch(0.0))
        self.pitch_box.valueChanged.connect(self.set_pitch)
        self.pitch_box.editingFinished.connect(self.wave.setFocus)
        self.speed_slider.valueChanged.connect(lambda v: self.set_speed(v / 100))
        self.speed_box.valueChanged.connect(self.set_speed)
        self.speed_box.editingFinished.connect(self.wave.setFocus)
        self.volume.valueChanged.connect(self._set_volume)
        self.wave.seekRequested.connect(self.seek)
        self.wave.addBookmarkRequested.connect(self.add_bookmark_at)
        self.wave.removeBookmarkRequested.connect(self.remove_bookmark)
        self.wave.renameBookmarkRequested.connect(self.rename_bookmark)
        self.wave.selectionChanged.connect(self.set_selection)
        self.wave.firstBeatRequested.connect(self.set_first_beat)
        self.b_repeat.toggled.connect(self.a_repeat.setChecked)
        self.a_repeat.toggled.connect(self.b_repeat.setChecked)
        self.b_count.toggled.connect(self.a_count.setChecked)
        self.a_count.toggled.connect(self.b_count.setChecked)
        self.b_count.setChecked(self.count.on)
        self.b_count.customContextMenuRequested.connect(lambda _pos: self.count_settings())
        self.b_tap.clicked.connect(self.tap_tempo)
        count_menu = QMenu(self.b_count)
        count_menu.addAction(self.a_count_settings)
        self.b_count.setMenu(count_menu)
        self._update_count_tip()
        self.panel.activated.connect(lambda row: self.seek(self.bookmarks[row].time))
        self.panel.addRequested.connect(self.add_bookmark)
        self.panel.removeRequested.connect(self.remove_bookmark)
        self.panel.renamed.connect(self._renamed)
        self.panel.exportRequested.connect(self.export_bookmarks)

    # --- archivos

    def open_dialog(self) -> None:
        patterns = " ".join(f"*.{e}" for e in EXTENSIONS)
        start = self.settings.value("folder", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open an audio file"), start,
            f"{tr('Audio and video files')} ({patterns});;{tr('All files')} (*)")
        if path:
            self.open_file(path)

    def open_file(self, path: str | Path) -> bool:
        path = Path(path)
        self.close_file()
        try:
            audio = Audio(path)
            if not Output.supports(audio.rate):
                # The sound card does not play that sample rate: decode again, at its own.
                rate = Output.default_rate()
                audio.close()
                audio = Audio(path, rate=rate)
            self.player.load(audio)
        except AudioError as error:
            QMessageBox.warning(self, APP, tr("Cannot read {name} as audio:\n{error}", name=path.name, error=error))
            return False
        except Exception as error:  # noqa: BLE001 (la tarjeta de sonido, sobre todo: PortAudio)
            self.player.unload()
            QMessageBox.warning(self, APP, tr("Cannot play {name}:\n{error}", name=path.name, error=error))
            return False
        self.audio = audio
        self.wave.set_audio(audio)
        self.selection = None
        self.wave.set_selection(None)
        self.bookmarks = self.store.bookmarks(path)
        self._show_bookmarks()
        self.set_speed(self.player.speed)
        # Sigue donde se dejó, cuando el archivo esté decodificado hasta allí (_tick).
        self._resume = self.store.position(path)
        self.setWindowTitle(f"{path.name} — {APP}")
        self.settings.setValue("folder", str(path.parent))
        self._remember(path)
        self._update_enabled()
        self.statusBar().showMessage(tr("Reading {name}…", name=path.name))
        return True

    def close_file(self) -> None:
        if self.audio is None:
            return
        self.store.set_position(self.audio.path, self._position_to_keep())
        audio = self.audio
        self.player.unload()
        audio.close()
        self.audio = None
        self.bookmarks = []
        self._resume = 0.0
        self.wave.set_audio(None)
        self.selection = None
        self.wave.set_selection(None)
        self._show_bookmarks()
        self.setWindowTitle(APP)
        self.statusBar().clearMessage()
        self._update_enabled()

    def _position_to_keep(self) -> float:
        # At the end, or nearly, the next time starts from the beginning.
        position = self.player.position
        if self.audio and self.audio.done and position >= self.audio.duration - 1.0:
            return 0.0
        return position

    def _remember(self, path: Path) -> None:
        recent = [p for p in self.settings.value("recent", [], type=list) if p != str(path)]
        self.settings.setValue("recent", [str(path)] + recent[: RECENT - 1])

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.value("recent", [], type=list)
        for p in recent:
            action = self.recent_menu.addAction(Path(p).name)
            action.setToolTip(p)
            action.setEnabled(Path(p).is_file())
            action.triggered.connect(lambda _=False, p=p: self.open_file(p))
        if not recent:
            self.recent_menu.addAction(tr("(none)")).setEnabled(False)

    # --- reproducción

    def toggle(self) -> None:
        if not self.audio:
            return
        if self.player.playing:
            self.player.pause()
        elif self.count.on:
            self.player.play(self.count.beats, self.count.tempo(self.player.speed), self.count.offset)
        else:
            self.player.play()
        self._update_play_button()

    # --- la cuenta previa y la selección repetida

    def _set_count_on(self, on: bool) -> None:
        self.count.on = on
        self.count.save(self.settings)

    def count_settings(self) -> None:
        dialog = CountInDialog(self.count, self.player.speed, self)
        if dialog.exec():
            self.count = dialog.value()
            self.count.save(self.settings)
            self.a_count.setChecked(self.count.on)
            self._update_count_tip()

    def tap_tempo(self) -> None:
        """A tap with the beat of the music: after a few, the tempo of the count-in. What is tapped is the tempo
        heard; with the count-in following the speed, the recording's own is kept (tapped / speed)."""
        heard = self.tapper.tap()
        if heard is None:
            self.statusBar().showMessage(tr("Tap again, with the beat…"), 3000)
            return
        speed = self.player.speed
        self.count.bpm = recording_tempo(heard, speed, self.count.follow)
        self.count.save(self.settings)
        self._update_count_tip()
        taps = self.tapper.taps
        if self.count.follow and speed != 1.0:
            message = tr("Tempo: {heard} BPM heard at {speed}×, {bpm} BPM in the recording ({taps} taps)",
                         heard=round(heard), speed=number(speed), bpm=self.count.bpm, taps=taps)
        else:
            message = tr("Tempo: {bpm} BPM ({taps} taps)", bpm=self.count.bpm, taps=taps)
        self.statusBar().showMessage(message, 4000)

    def set_first_beat(self, seconds: float | None) -> None:
        """The count-in's offset from the recording's first beat, at SECONDS (None: at the position): the
        recording then comes in on the beat after the count, from the position. The count-in is turned on."""
        if not self.audio:
            return
        offset = 0.0 if seconds is None else round(self.player.position - seconds, 2)
        if abs(offset) > MAX_OFFSET:
            self.statusBar().showMessage(tr("The first beat must be within {limit} s of the position (this is "
                                            "{seconds} s away).", limit=number(MAX_OFFSET),
                                            seconds=number(abs(offset))), 6000)
            return
        self.count.offset = offset
        self.a_count.setChecked(True)
        self.count.save(self.settings)
        self._update_count_tip()
        if offset == 0.0:
            message = tr("Count-in: the recording comes in on the beat, from the position.")
        else:
            message = tr("Count-in: the first beat at {time}; the recording comes in {seconds} s {when} the beat.",
                         time=clock(seconds, tenths=True), seconds=number(abs(offset)),
                         when=tr("before") if offset < 0 else tr("after"))
            heard = -offset / self.player.speed
            limit = max_earlier(self.audio.rate, self.count.tempo(self.player.speed))
            if heard > limit:
                message += " " + tr("At this tempo it can come in at most {seconds} s earlier.",
                                    seconds=number(limit * self.player.speed))
        self.statusBar().showMessage(message, 8000)

    def _update_count_tip(self) -> None:
        # Lo que la cuenta hace ahora, a la vista al pasar sobre el botón.
        count = self.count
        if count.follow:
            what = tr("{beats} clicks at {bpm} BPM, following the speed", beats=count.beats, bpm=count.bpm)
        else:
            what = tr("{beats} clicks at {bpm} BPM", beats=count.beats, bpm=count.bpm)
        if count.offset:
            signed = ("+" if count.offset > 0 else "−") + number(abs(count.offset))
            what += tr("; the recording {offset} s off the beat", offset=signed)
        self.b_count.setToolTip(tr("Count in before playing (C): {what}. The arrow beside it changes them.",
                                   what=what))

    def set_selection(self, selection: tuple[float, float] | None) -> None:
        """The selection (start and end, in seconds), or none; it is repeated if Repeat is on."""
        if selection is not None:
            start, end = sorted(selection)
            limit = self.audio.duration if self.audio else 0.0
            start, end = max(0.0, start), min(end, limit)
            selection = (start, end) if end - start >= MIN_LOOP else None
        self.selection = selection
        self.wave.set_selection(selection, self.a_repeat.isChecked())
        self._apply_loop()
        if selection:
            self.statusBar().showMessage(tr("Selection: {start} – {end}", start=clock(selection[0], tenths=True),
                                            end=clock(selection[1], tenths=True)), 4000)

    def mark_selection(self, start: bool) -> None:
        """The start (or the end) of the selection at the position; the other end stays, or is the file's."""
        if not self.audio:
            return
        here = self.player.position
        old = self.selection or (0.0, self.audio.duration)
        self.set_selection((here, old[1]) if start else (old[0], here))

    def _set_repeat(self, on: bool) -> None:
        self.wave.set_selection(self.selection, on)
        self._apply_loop()
        if on and not self.selection:
            self.statusBar().showMessage(tr("Select a part to repeat: Shift+drag on the waveform, or I and O"), 5000)

    def _apply_loop(self) -> None:
        if self.audio:
            loop = self.selection if self.a_repeat.isChecked() else None
            if loop != self.player.loop:
                self.player.set_loop(loop)

    def stop(self) -> None:
        self.player.stop()
        self._update_play_button()

    def seek(self, seconds: float) -> None:
        if self.audio:
            self.player.seek(seconds)
            self._resume = 0.0
            self._tick()

    def jump(self, seconds: float) -> None:
        if self.audio:
            self.seek(max(0.0, self.player.position + seconds))

    def go_end(self) -> None:
        if self.audio:
            self.seek(self.audio.duration)

    def set_speed(self, speed: float) -> None:
        speed = min(MAX_SPEED, max(MIN_SPEED, round(float(speed), 2)))
        self.player.speed = speed
        # Both controls are brought in line without calling this again.
        for widget, value in ((self.speed_slider, round(speed * 100)), (self.speed_box, speed)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.b_normal.setEnabled(speed != 1.0)

    def change_speed(self, delta: float) -> None:
        if self.stretching:
            self.set_speed(self.player.speed + delta)

    def set_pitch(self, semitones: float) -> None:
        """Move the pitch SEMITONES up (or down, below 0) from that of the recording."""
        if not self.stretching:
            return
        self.player.pitch = semitones
        self.pitch_box.blockSignals(True)
        self.pitch_box.setValue(self.player.pitch)
        self.pitch_box.blockSignals(False)
        self.b_pitch.setEnabled(self.player.pitch != 0.0)

    def change_pitch(self, delta: float) -> None:
        self.set_pitch(self.player.pitch + delta)

    def _set_volume(self, value: int) -> None:
        # A square curve: the steps of the slider sound more even to the ear.
        self.player.volume = (value / 100) ** 2
        self.settings.setValue("volume", value)

    def _tick(self) -> None:
        audio = self.audio
        if audio is None:
            return
        if self._resume and (audio.done or audio.decoded / audio.rate > self._resume + 1):
            self.player.seek(min(self._resume, audio.duration))
            self._resume = 0.0
        if self.player.ended:
            self.player.ended = False
            self._update_play_button()
        position = self.player.position
        self.wave.set_position(position, self.player.playing)
        counting = self.player.counting()
        self.wave.set_count(counting[0] if counting and counting[0] else None)
        # Con la cuenta previa, y sin sonar, dónde espera el primer pulso de la grabación.
        offset = self.count.offset
        beat = position - offset if self.count.on and offset and not self.player.playing else None
        self.wave.set_first_beat(beat if beat is None or beat >= 0 else None)
        self.time_label.setText(f"{clock(position, tenths=True)} / {clock(audio.duration, tenths=True)}")
        if self.b_play.property("playing") != self.player.playing:
            self._update_play_button()
        if audio.done and self._announced is not audio:
            self._announced = audio
            if audio.error:
                self.statusBar().showMessage(tr("{name}: read up to {time} ({error})", name=audio.path.name,
                                                time=clock(audio.duration), error=audio.error))
            else:
                self.statusBar().showMessage(self._describe(audio), 0)
            self.wave.viewChanged.emit()
        elif not audio.done and audio.estimated and audio.length:
            share = min(99, int(100 * audio.decoded / audio.length))
            self.statusBar().showMessage(tr("Reading {name}… {percent}%", name=audio.path.name, percent=share))

    def _describe(self, audio: Audio) -> str:
        channels = tr("mono") if audio.channels == 1 else tr("stereo")
        return f"{audio.path.name} · {audio.codec} · {audio.rate} Hz · {channels} · {clock(audio.duration)}"

    def _update_play_button(self) -> None:
        playing = self.player.playing
        self.b_play.setProperty("playing", playing)
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.b_play.setIcon(self.style().standardIcon(icon))
        self.b_play.setToolTip(tr("Pause (Space)") if playing else tr("Play (Space)"))

    def _update_enabled(self) -> None:
        loaded = self.audio is not None
        for widget in (self.b_start, self.b_back, self.b_play, self.b_stop, self.b_forward, self.b_end,
                       self.b_mark, self.b_repeat, self.panel.add_button):
            widget.setEnabled(loaded)
        for action in (self.a_close, self.a_play, self.a_stop, self.a_start, self.a_end, self.a_back,
                       self.a_forward, self.a_back_1, self.a_forward_1, self.a_mark, self.a_prev_mark,
                       self.a_next_mark, self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_repeat,
                       self.a_sel_start, self.a_sel_end, self.a_sel_clear):
            action.setEnabled(loaded)
        self.a_export.setEnabled(loaded and bool(self.bookmarks))
        self._update_play_button()

    def _set_skip(self, seconds: float) -> None:
        self.skip = float(seconds)
        self.settings.setValue("skip", seconds)
        self._update_skip_tips()

    def _update_skip_tips(self) -> None:
        n = f"{self.skip:g}"
        self.b_back.setToolTip(tr("Back {n} s (Left); hold to keep going", n=n))
        self.b_forward.setToolTip(tr("Forward {n} s (Right); hold to keep going", n=n))

    def _set_follow(self, on: bool) -> None:
        self.wave.follow = on
        self.settings.setValue("follow", on)

    # --- marcadores

    def _show_bookmarks(self, select: int | None = None) -> None:
        self.wave.set_bookmarks(self.bookmarks)
        self.panel.show_bookmarks(self.bookmarks, select)
        self.a_export.setEnabled(self.audio is not None and bool(self.bookmarks))

    def _save_bookmarks(self) -> None:
        if self.audio:
            self.store.set_bookmarks(self.audio.path, self.bookmarks)

    def add_bookmark(self) -> None:
        if self.audio:
            self.add_bookmark_at(self.player.position)

    def add_bookmark_at(self, seconds: float) -> int:
        """Add a bookmark at SECONDS (or none, if one is already there); its row."""
        if not self.audio:
            return -1
        for i, mark in enumerate(self.bookmarks):
            if abs(mark.time - seconds) < 0.05:
                self._show_bookmarks(i)
                return i
        mark = Bookmark(round(seconds, 3), "")
        self.bookmarks.append(mark)
        self.bookmarks.sort(key=lambda b: b.time)
        row = self.bookmarks.index(mark)
        self._save_bookmarks()
        self._show_bookmarks(row)
        self.statusBar().showMessage(tr("Bookmark at {time}", time=clock(seconds, tenths=True)), 3000)
        return row

    def remove_bookmark(self, row: int) -> None:
        if 0 <= row < len(self.bookmarks):
            del self.bookmarks[row]
            self._save_bookmarks()
            self._show_bookmarks()

    def rename_bookmark(self, row: int) -> None:
        if not 0 <= row < len(self.bookmarks):
            return
        mark = self.bookmarks[row]
        text, ok = QInputDialog.getText(self, tr("Bookmark at {time}", time=clock(mark.time, tenths=True)),
                                        tr("Label:"), text=mark.label)
        if ok:
            self._renamed(row, text.strip())
            self._show_bookmarks(row)

    def _renamed(self, row: int, text: str) -> None:
        if 0 <= row < len(self.bookmarks):
            self.bookmarks[row].label = text
            self._save_bookmarks()
            self.wave.set_bookmarks(self.bookmarks)

    def goto_bookmark(self, direction: int) -> None:
        """Go to the next (1) or previous (-1) bookmark from the position."""
        if not self.audio or not self.bookmarks:
            return
        here = self.player.position
        if direction > 0:
            later = [b for b in self.bookmarks if b.time > here + 0.05]
            target = later[0] if later else None
        else:
            # Mientras suena, el anterior es el de antes del que se acaba de pasar (medio segundo de gracia).
            grace = 0.5 if self.player.playing else 0.05
            earlier = [b for b in self.bookmarks if b.time < here - grace]
            target = earlier[-1] if earlier else None
        if target is not None:
            self.seek(target.time)
            self.panel.table.selectRow(self.bookmarks.index(target))

    def export_bookmarks(self) -> None:
        if not self.audio or not self.bookmarks:
            return
        suggestion = str(self.audio.path.with_suffix(".bookmarks.txt"))
        path, _ = QFileDialog.getSaveFileName(self, tr("Export the bookmarks"), suggestion,
                                              f"{tr('Text files')} (*.txt);;{tr('All files')} (*)")
        if path:
            try:
                Path(path).write_text(export_text(self.bookmarks, self.audio.path.name), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, APP, str(error))

    # --- ayuda y configuración

    def _set_language(self, code: str) -> None:
        self.settings.setValue("interface", code)
        QMessageBox.information(self, APP, tr("The language changes when py-slowdown starts again."))

    def show_shortcuts(self) -> None:
        rows = shortcut_rows()
        html = "<table cellspacing='4'>" + "".join(
            f"<tr><td>{what}</td><td>&nbsp;&nbsp;<b>{keys}</b></td></tr>" for what, keys in rows) + "</table>"
        QMessageBox.information(self, tr("Keyboard shortcuts"), html)

    def about(self) -> None:
        QMessageBox.about(self, tr("About py-slowdown"), tr(
            "<p><b>py-slowdown {version}</b></p>"
            "<p>Plays audio slower or faster without changing its pitch, with the "
            "Rubber Band Library (R3 engine).</p>"
            "<p>© 2026 Nicolas Vaughan &lt;nicolasvaughan@proton.me&gt;<br>"
            "GNU General Public License, version 3 or later.</p>", version=__version__))

    # --- eventos de la ventana

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())
                break

    def closeEvent(self, event) -> None:
        self.close_file()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        super().closeEvent(event)
