"""La ventana principal de py-slowdown.

Arriba, la forma de onda; debajo, los mandos de la reproducción (al principio,
atrás, tocar o pausar, detener, adelante, al final), el tiempo, la velocidad,
la altura, la manera de oír y el volumen; a la derecha, el panel de los
marcadores y los bucles. Los menús repiten todo eso con sus atajos de teclado,
que se pueden cambiar.

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
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, interface, rubberband
from .audio import EXTENSIONS, Audio, AudioError
from .bookmarks import Bookmark, Loop, Store, export_text
from . import export, shortcuts, sidecar
from .countin import MAX_OFFSET, CountIn, CountInDialog, TapTempo, number, recording_tempo
from .exportdialog import ExportDialog, run_export, suggested_name
from .engine import MAX_BPM, MAX_PITCH, MAX_SPEED, MIN_BPM, MIN_LOOP, MIN_SPEED, Output, Player, max_earlier
from .hearing import CHANNELS, FILTERS
from .interface import tr
from .panel import BookmarkPanel, LoopPanel
from .timefmt import clock
from .waveform import WaveformView

APP = "py-slowdown"
SPEED_STEP = 0.05
SPEED_PRESETS = (50, 60, 70, 75, 80, 90, 100, 110, 125, 150)  # por ciento: las velocidades de siempre del botón


def parse_speeds(text: str) -> list[int] | None:
    """The speeds, in percent, of TEXT ("50, 75%, 100"), in order and each once; None if one is not a whole
    number from MIN_SPEED to MAX_SPEED (25 to 300)."""
    speeds = set()
    for part in text.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip().rstrip("%").strip()
        if not part:
            continue
        if not part.isdigit():
            return None
        value = int(part)
        if not round(MIN_SPEED * 100) <= value <= round(MAX_SPEED * 100):
            return None
        speeds.add(value)
    return sorted(speeds) or None
SKIPS = (1, 2, 5, 10, 15, 30, 60)
RECENT = 10


def hearing_names() -> tuple[dict[str, str], dict[str, str]]:
    """The names of the ways of hearing, in the menu: ({channels: name}, {filter: name})."""
    return ({"both": tr("&Both channels"), "left": tr("&Left channel only"), "right": tr("&Right channel only"),
             "mono": tr("&Mono (both channels in one)"),
             "no_centre": tr("Without the &centre (what is in the middle of the mix)")},
            {"none": tr("&No filter"), "bass": tr("Bass &only (below 250 Hz)"),
             "no_bass": tr("Without the b&ass (above 250 Hz)")})


def quality_names() -> dict[str, str]:
    """The choices of Settings > Playback quality."""
    return {"high": tr("&Highest (R3 engine)"),
            "light": tr("&Lighter (R3, half the processor, a little less detail in the low notes)"),
            "r2": tr("&Older engine (R2, crisp attacks, for drums and percussion)")}


def hearing_short(channels: str, filter_: str) -> str:
    """A few words for the button Hear: what is heard, if not everything."""
    words = {"left": tr("left"), "right": tr("right"), "mono": tr("mono"), "no_centre": tr("no centre"),
             "bass": tr("bass only"), "no_bass": tr("no bass")}
    parts = [words[x] for x in (channels, filter_) if x in words]
    return tr("Hear: {what}", what=", ".join(parts)) if parts else tr("Hear")
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
        (tr("Save the selection as a loop"), tr("Shift+L")),
        (tr("Count in before playing"), "C"),
        (tr("Tap the tempo (with the beat)"), "T"),
        (tr("Open a file"), "Ctrl+O"),
        (tr("Export the audio"), "Ctrl+E"),
        (tr("Change the shortcuts"), tr("Settings > Keyboard shortcuts")),
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
        self.loops: list[Loop] = []
        self._resume = 0.0  # where to go once the file is decoded that far
        self._pending_selection: tuple[tuple[float, float], bool] | None = None  # (selección, repetir), al leerla
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
        self.loop_panel = LoopPanel(self)
        self._build_transport()
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.transport)
        self.setCentralWidget(central)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.panel, tr("Bookmarks"))
        self.tabs.addTab(self.loop_panel, tr("Loops"))
        self.dock = QDockWidget(tr("Bookmarks and loops"), self)
        self.dock.setObjectName("bookmarks")
        self.dock.setWidget(self.tabs)
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
            for widget in (self.speed_slider, self.speed_box, self.b_normal, self.b_speeds, self.pitch_box,
                           self.b_pitch, self.b_formants):
                widget.setEnabled(False)
                widget.setToolTip(why)
            for action in (self.a_slower, self.a_faster, self.a_normal, self.a_higher, self.a_lower,
                           self.a_original_pitch, self.a_formants):
                action.setEnabled(False)
            self.quality_menu.setEnabled(False)
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
        self.b_tap = QToolButton(self)
        self.b_tap.setText(tr("Tap"))
        self.b_tap.setToolTip(tr("Tap with the beat of the music (T), a few times: the tempo of the count-in is "
                                 "measured"))
        self.b_tap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.b_repeat)
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
        self.b_speeds = QToolButton(self)
        self.b_speeds.setText(tr("Speeds"))
        self.b_speeds.setToolTip(tr("Speeds chosen beforehand (50%, 75%, 100%…), which can be changed"))
        self.b_speeds.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_speeds.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_menu = QMenu(tr("Spee&d presets"), self)
        self.speed_menu.aboutToShow.connect(self._fill_speed_menu)
        self.b_speeds.setMenu(self.speed_menu)
        row.addWidget(self.speed_slider)
        row.addWidget(self.speed_box)
        row.addWidget(self.b_normal)
        row.addWidget(self.b_speeds)
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
        self.b_formants = QToolButton(self)
        self.b_formants.setText(tr("Formants"))
        self.b_formants.setCheckable(True)
        self.b_formants.setToolTip(tr("Keep the formants: when the pitch moves, voices and instruments keep their "
                                      "natural timbre"))
        self.b_formants.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.pitch_box)
        row.addWidget(self.b_pitch)
        row.addWidget(self.b_formants)
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
        self.a_export_audio = a(tr("E&xport the audio…"), self.export_audio, ["Ctrl+E"])
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
        self.a_formants = a(tr("&Keep the formants"), self.set_formants, checkable=True)
        self.a_repeat = a(tr("&Repeat the selection"), self._set_repeat, ["L"], checkable=True)
        self.a_sel_start = a(tr("Select&ion starts here"), lambda: self.mark_selection(start=True), ["I"])
        self.a_sel_end = a(tr("Selection ends &here"), lambda: self.mark_selection(start=False), ["O"])
        self.a_sel_clear = a(tr("Clear the selecti&on"), lambda: self.set_selection(None), ["Esc"])
        self.a_save_loop = a(tr("Sa&ve the selection as a loop"), self.save_loop, ["Shift+L"])
        self.a_count = a(tr("&Count in before playing"), self._set_count_on, ["C"], checkable=True)
        self.a_count.setChecked(self.count.on)
        self.a_count_settings = a(tr("Co&unt-in settings…"), self.count_settings)
        self.a_tap = a(tr("Tap the tempo"), self.tap_tempo, ["T"])
        self.a_reopen = a(tr("&Reopen the last file when starting"), self._set_reopen, checkable=True)
        self.a_reopen.setChecked(self.settings.value("reopen", False, type=bool))
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
        self.a_edit_shortcuts = a(tr("Keyboard s&hortcuts…"), self.edit_shortcuts)
        # Las acciones con nombre (el del atributo), sus teclas de siempre, y las que el usuario eligió.
        self.shortcut_actions = {name: action for name, action in vars(self).items()
                                 if name.startswith("a_") and isinstance(action, QAction)}
        for name, action in self.shortcut_actions.items():
            action.setObjectName(name)
        self.default_shortcuts = {name: shortcuts.keys_of(action) for name, action in self.shortcut_actions.items()}
        shortcuts.load(self.shortcut_actions, self.settings)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file = bar.addMenu(tr("&File"))
        file.addAction(self.a_open)
        self.recent_menu = file.addMenu(tr("Open &recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        file.addAction(self.a_export_audio)
        file.addAction(self.a_close)
        file.addSeparator()
        file.addAction(self.a_quit)

        play = bar.addMenu(tr("&Playback"))
        for action in (self.a_play, self.a_stop, None, self.a_start, self.a_back, self.a_back_1,
                       self.a_forward_1, self.a_forward, self.a_end, None,
                       self.a_slower, self.a_faster, self.a_normal, self.speed_menu, None,
                       self.a_higher, self.a_lower, self.a_original_pitch, self.a_formants, None,
                       self.a_repeat, self.a_sel_start, self.a_sel_end, self.a_sel_clear, self.a_save_loop):
            if action is None:
                play.addSeparator()
            elif isinstance(action, QMenu):
                play.addMenu(action)
            else:
                play.addAction(action)

        # Oír y la cuenta previa, cada uno con su menú.
        self.hear_menu = bar.addMenu(tr("H&ear"))
        self.a_channels: dict[str, QAction] = {}
        self.a_filters: dict[str, QAction] = {}
        channel_names, filter_names = hearing_names()
        for names, actions, key in ((channel_names, self.a_channels, CHANNELS), (filter_names, self.a_filters, FILTERS)):
            group = QActionGroup(self)
            for value in key:
                action = self.hear_menu.addAction(names[value])
                action.setCheckable(True)
                action.triggered.connect(self._hearing_chosen)
                group.addAction(action)
                actions[value] = action
            if key is CHANNELS:
                self.hear_menu.addSeparator()
        channels = self.settings.value("hearing/channels", "both")
        filter_ = self.settings.value("hearing/filter", "none")
        self.set_hearing(channels if channels in CHANNELS else "both", filter_ if filter_ in FILTERS else "none")

        count = bar.addMenu(tr("&Count-in"))
        for action in (self.a_count, self.a_tap, None, self.a_count_settings):
            count.addSeparator() if action is None else count.addAction(action)

        marks = bar.addMenu(tr("&Bookmarks"))
        for action in (self.a_mark, self.a_prev_mark, self.a_next_mark, None, self.a_export):
            marks.addSeparator() if action is None else marks.addAction(action)

        view = bar.addMenu(tr("&View"))
        for action in (self.a_zoom_in, self.a_zoom_out, self.a_fit, None, self.a_follow):
            view.addSeparator() if action is None else view.addAction(action)
        view.addSeparator()
        view.addAction(self.dock.toggleViewAction())

        settings = bar.addMenu(tr("&Settings"))
        settings.addAction(self.a_edit_shortcuts)
        settings.addAction(self.a_reopen)
        settings.addSeparator()
        files = settings.addMenu(tr("Settings &files of each recording"))
        group = QActionGroup(self)
        self.a_sidecar: dict[str, QAction] = {}
        for mode, name in (("beside", tr("&Beside the audio file")), ("folder", tr("In a &folder…")),
                           ("off", tr("&Not saved"))):
            action = files.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, m=mode: self._sidecar_chosen(m))
            group.addAction(action)
            self.a_sidecar[mode] = action
        self._show_sidecar_choice()
        qualities = settings.addMenu(tr("Playback &quality"))
        group = QActionGroup(self)
        self.a_qualities: dict[str, QAction] = {}
        for key, name in quality_names().items():
            action = qualities.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, k=key: self.set_quality(k))
            group.addAction(action)
            self.a_qualities[key] = action
        self.quality_menu = qualities
        quality = self.settings.value("quality", "high")
        self.set_quality(quality if quality in self.a_qualities else "high")
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
        self.b_tap.clicked.connect(self.tap_tempo)
        self.b_formants.toggled.connect(self.a_formants.setChecked)
        self.a_formants.toggled.connect(self.b_formants.setChecked)
        self.a_formants.setChecked(self.settings.value("formants", False, type=bool))
        self._update_count_tip()
        self.panel.activated.connect(lambda row: self.seek(self.bookmarks[row].time))
        self.panel.addRequested.connect(self.add_bookmark)
        self.panel.removeRequested.connect(self.remove_bookmark)
        self.panel.renamed.connect(self._renamed)
        self.panel.exportRequested.connect(self.export_bookmarks)
        self.loop_panel.activated.connect(self.repeat_loop)
        self.loop_panel.saveRequested.connect(self.save_loop)
        self.loop_panel.removeRequested.connect(self.remove_loop)
        self.loop_panel.renamed.connect(self._loop_renamed)

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
        # Lo que se guardó de este archivo: su XML, si lo hay (va con el archivo, aunque se mueva); si no, lo de
        # bookmarks.json.
        kept = self._read_sidecar(path)
        self.bookmarks = kept.bookmarks if kept else self.store.bookmarks(path)
        self._show_bookmarks()
        self.loops = kept.loops if kept else self.store.loops(path)
        self.loop_panel.show_loops(self.loops)
        self.set_speed(self.player.speed)
        self.set_hearing(*self.player.hearing)
        self._apply_file_settings(kept.settings if kept else self.store.settings(path))
        # Sigue donde se dejó, cuando el archivo esté decodificado hasta allí (_tick).
        self._resume = kept.position if kept else self.store.position(path)
        self.setWindowTitle(f"{path.name} — {APP}")
        self.settings.setValue("folder", str(path.parent))
        self._remember(path)
        self._update_enabled()
        self.statusBar().showMessage(tr("Reading {name}…", name=path.name))
        return True

    def open_at_start(self, path: str | None = None) -> None:
        """The file to open when the program starts: PATH, or else the last one opened, if Settings > Reopen the
        last file when starting is on and it is still there (it goes on where it was left)."""
        if path:
            self.open_file(path)
            return
        if not self.a_reopen.isChecked():
            return
        recent = self.settings.value("recent", [], type=list)
        if recent and Path(recent[0]).is_file():
            self.open_file(recent[0])

    def _set_reopen(self, on: bool) -> None:
        self.settings.setValue("reopen", on)

    def close_file(self) -> None:
        if self.audio is None:
            return
        self.store.set_position(self.audio.path, self._position_to_keep())
        self.store.set_settings(self.audio.path, self._file_settings())
        self._write_sidecar()
        audio = self.audio
        self.player.unload()
        audio.close()
        self.audio = None
        self.bookmarks = []
        self.loops = []
        self.loop_panel.show_loops(self.loops)
        self._resume = 0.0
        self._pending_selection = None
        self.wave.set_audio(None)
        self.selection = None
        self.wave.set_selection(None)
        self._show_bookmarks()
        self.setWindowTitle(APP)
        self.statusBar().clearMessage()
        self._update_enabled()

    def _file_settings(self) -> dict:
        """How the file is played, to have it so again the next time: only what is not the usual."""
        player = self.player
        kept: dict = {}
        if player.speed != 1.0:
            kept["speed"] = player.speed
        if player.pitch:
            kept["pitch"] = player.pitch
        if player.formants:
            kept["formants"] = True
        if player.hearing != ("both", "none"):
            kept["hearing"] = list(player.hearing)
        selection = self.selection or (self._pending_selection[0] if self._pending_selection else None)
        if selection:
            kept["selection"] = [round(selection[0], 3), round(selection[1], 3)]
            repeat = self.a_repeat.isChecked() if self.selection else self._pending_selection[1]
            if repeat:
                kept["repeat"] = True
        if self.count.on:
            # (el tempo y el desfase de la cuenta son de cada pieza)
            kept["countin"] = {"bpm": self.count.bpm, "offset": self.count.offset}
        return kept

    def _apply_file_settings(self, kept: dict) -> None:
        """Play the file as it was played the last time (KEPT, from _file_settings); nothing kept, nothing
        changes."""
        if not kept:
            return
        try:
            if self.stretching:
                self.set_speed(float(kept.get("speed", 1.0)))
                self.set_pitch(float(kept.get("pitch", 0.0)))
                self.a_formants.setChecked(bool(kept.get("formants", False)))
            channels, filter_ = kept.get("hearing", ("both", "none"))
            self.set_hearing(channels if channels in CHANNELS else "both", filter_ if filter_ in FILTERS else "none")
            selection = kept.get("selection")
            if selection:
                start, end = sorted(float(x) for x in selection)
                # (se elige cuando el archivo esté leído hasta su final: _tick)
                self._pending_selection = ((start, end), bool(kept.get("repeat", False)))
            countin = kept.get("countin")
            if isinstance(countin, dict):
                self.count.bpm = int(min(MAX_BPM, max(MIN_BPM, int(countin.get("bpm", self.count.bpm)))))
                self.count.offset = min(MAX_OFFSET, max(-MAX_OFFSET, float(countin.get("offset", 0.0))))
                self.a_count.setChecked(True)
                self.count.save(self.settings)
                self._update_count_tip()
        except (TypeError, ValueError):
            pass  # (lo guardado no se entiende: queda lo que había)

    # --- el XML de cada archivo (sidecar.py)

    def _sidecar_place(self) -> tuple[bool, Path | None]:
        """(whether the XML files are written, the folder where: None beside each audio file)."""
        mode = self.settings.value("sidecar/mode", "beside")
        if mode == "off":
            return False, None
        folder = self.settings.value("sidecar/folder", "")
        if mode == "folder" and folder:
            return True, Path(folder)
        return True, None

    def _read_sidecar(self, path: Path) -> sidecar.FileState | None:
        on, folder = self._sidecar_place()
        return sidecar.load(path, folder) if on else None

    def _write_sidecar(self) -> None:
        on, folder = self._sidecar_place()
        if not on or self.audio is None:
            return
        state = sidecar.FileState(self._position_to_keep(), self._file_settings(), list(self.bookmarks),
                                  list(self.loops))
        try:
            sidecar.save(self.audio.path, state, folder)
        except OSError as error:
            # (una carpeta de solo lectura, un disco lleno: bookmarks.json lo guarda de todos modos)
            self.statusBar().showMessage(tr("Cannot write the settings file of {name}: {error}",
                                            name=self.audio.path.name, error=error.strerror or error), 8000)

    def _sidecar_chosen(self, mode: str) -> None:
        if mode == "folder":
            start = self.settings.value("sidecar/folder", "") or str(Path.home())
            folder = QFileDialog.getExistingDirectory(self, tr("The folder of the settings files"), start)
            if not folder:
                self._show_sidecar_choice()  # (cancelado: queda lo de antes)
                return
            self.settings.setValue("sidecar/folder", folder)
        self.settings.setValue("sidecar/mode", mode)
        self._show_sidecar_choice()

    def _show_sidecar_choice(self) -> None:
        on, folder = self._sidecar_place()
        mode = "off" if not on else ("folder" if folder else "beside")
        self.a_sidecar[mode].setChecked(True)
        if folder:
            self.a_sidecar["folder"].setText(tr("In a &folder ({folder})…", folder=str(folder)))
        else:
            self.a_sidecar["folder"].setText(tr("In a &folder…"))

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
        # Lo que la cuenta hace ahora: la barra de estado lo dice al pasar sobre sus acciones, en el menú.
        count = self.count
        if count.follow:
            what = tr("{beats} clicks at {bpm} BPM, following the speed", beats=count.beats, bpm=count.bpm)
        else:
            what = tr("{beats} clicks at {bpm} BPM", beats=count.beats, bpm=count.bpm)
        if count.offset:
            signed = ("+" if count.offset > 0 else "−") + number(abs(count.offset))
            what += tr("; the recording {offset} s off the beat", offset=signed)
        tip = tr("Count in before playing (C): {what}.", what=what)
        for action in (self.a_count, self.a_count_settings):
            action.setStatusTip(tip)

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
        self._update_loop_saving()
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

    def speed_presets(self) -> list[int]:
        """The speeds of the button Speeds, in percent."""
        return parse_speeds(str(self.settings.value("speed/presets", ""))) or list(SPEED_PRESETS)

    def _fill_speed_menu(self) -> None:
        # Las velocidades, con la de ahora marcada si está entre ellas; y cómo cambiarlas.
        menu = self.speed_menu
        menu.clear()
        now = round(self.player.speed * 100)
        for percent in self.speed_presets():
            action = menu.addAction(f"{percent}%")
            action.setCheckable(True)
            action.setChecked(percent == now)
            action.setEnabled(self.stretching or percent == 100)
            action.triggered.connect(lambda _=False, p=percent: self.set_speed(p / 100))
        menu.addSeparator()
        menu.addAction(tr("&Edit the speeds…"), self.edit_speed_presets)
        menu.addAction(tr("&Restore the usual speeds"), self.restore_speed_presets)

    def edit_speed_presets(self) -> None:
        current = ", ".join(str(p) for p in self.speed_presets())
        text, ok = QInputDialog.getText(self, tr("Speeds"), tr("The speeds, in percent, separated by commas "
                                                               "(from 25 to 300):"), text=current)
        if not ok:
            return
        speeds = parse_speeds(text)
        if speeds is None:
            QMessageBox.warning(self, tr("Speeds"), tr("Write whole numbers from 25 to 300, separated by commas: "
                                                       "50, 75, 100, 125."))
            return
        self.settings.setValue("speed/presets", ", ".join(str(p) for p in speeds))

    def restore_speed_presets(self) -> None:
        self.settings.remove("speed/presets")

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

    def set_quality(self, quality: str) -> None:
        """Stretch the sound with QUALITY: "high" (R3), "light" (R3 with a short window, half the processor) or
        "r2" (the older engine, with crisp attacks). It changes while it plays; exports always use "high"."""
        self.player.quality = quality
        self.a_qualities[quality].setChecked(True)
        self.settings.setValue("quality", quality)

    def set_formants(self, on: bool) -> None:
        """Keep the formants when the pitch moves: a voice or an instrument keeps its timbre, instead of
        sounding smaller (higher) or bigger (lower)."""
        self.player.formants = on
        self.settings.setValue("formants", on)

    def set_hearing(self, channels: str, filter_: str) -> None:
        """Hear CHANNELS (both, left, right, mono, no_centre) through FILTER (none, bass, no_bass)."""
        if self.audio is not None and self.audio.channels == 1:
            channels = "both"  # (un archivo mono no tiene lados)
        self.player.hearing = (channels, filter_)
        self.a_channels[channels].setChecked(True)
        self.a_filters[filter_].setChecked(True)
        self.settings.setValue("hearing/channels", channels)
        self.settings.setValue("hearing/filter", filter_)

    def _hearing_chosen(self) -> None:
        channels = next(k for k, a in self.a_channels.items() if a.isChecked())
        filter_ = next(k for k, a in self.a_filters.items() if a.isChecked())
        self.set_hearing(channels, filter_)

    def _update_hearing_choices(self) -> None:
        # Con un archivo mono, los canales no se eligen.
        stereo = self.audio is None or self.audio.channels == 2
        for value, action in self.a_channels.items():
            action.setEnabled(stereo or value == "both")

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
        if self._pending_selection and (audio.done or audio.decoded / audio.rate > self._pending_selection[0][1]):
            selection, repeat = self._pending_selection
            self._pending_selection = None
            self.set_selection(selection)
            self.a_repeat.setChecked(repeat and self.selection is not None)
        if self._resume and (audio.done or audio.decoded / audio.rate > self._resume + 1):
            self.player.seek(min(self._resume, audio.duration))
            self._resume = 0.0
        if self.player.ended:
            self.player.ended = False
            self._update_play_button()
        position = self.player.position
        self.wave.follow_reading()
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
        for action in (self.a_close, self.a_export_audio, self.a_play, self.a_stop, self.a_start, self.a_end, self.a_back,
                       self.a_forward, self.a_back_1, self.a_forward_1, self.a_mark, self.a_prev_mark,
                       self.a_next_mark, self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_repeat,
                       self.a_sel_start, self.a_sel_end, self.a_sel_clear):
            action.setEnabled(loaded)
        self.a_export.setEnabled(loaded and bool(self.bookmarks))
        self._update_loop_saving()
        self._update_hearing_choices()
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

    # --- bucles: selecciones guardadas con un nombre

    def _update_loop_saving(self) -> None:
        can = self.audio is not None and self.selection is not None
        self.a_save_loop.setEnabled(can)
        self.loop_panel.save_button.setEnabled(can)

    def _save_loops(self) -> None:
        if self.audio:
            self.store.set_loops(self.audio.path, self.loops)

    def save_loop(self) -> None:
        """Keep the selection as a loop; its name is written in the list (Loops), which is shown."""
        if not self.audio or not self.selection:
            return
        start, end = self.selection
        for row, loop in enumerate(self.loops):
            if abs(loop.start - start) < 0.05 and abs(loop.end - end) < 0.05:
                self.tabs.setCurrentWidget(self.loop_panel)
                self.loop_panel.show_loops(self.loops, row)
                return
        loop = Loop(round(start, 3), round(end, 3), "")
        self.loops.append(loop)
        self.loops.sort(key=lambda x: (x.start, x.end))
        row = self.loops.index(loop)
        self._save_loops()
        self.dock.show()
        self.tabs.setCurrentWidget(self.loop_panel)
        self.loop_panel.show_loops(self.loops, row)
        self.loop_panel.edit_label(row)
        self.statusBar().showMessage(tr("Loop {start} – {end}: write its name", start=clock(start, tenths=True),
                                        end=clock(end, tenths=True)), 4000)

    def repeat_loop(self, row: int) -> None:
        """Select the loop of ROW, repeat it, and go to its start."""
        if not self.audio or not 0 <= row < len(self.loops):
            return
        loop = self.loops[row]
        self.set_selection((loop.start, loop.end))
        self.a_repeat.setChecked(True)
        self.seek(loop.start)

    def remove_loop(self, row: int) -> None:
        if 0 <= row < len(self.loops):
            del self.loops[row]
            self._save_loops()
            self.loop_panel.show_loops(self.loops)

    def _loop_renamed(self, row: int, text: str) -> None:
        if 0 <= row < len(self.loops):
            self.loops[row].label = text
            self._save_loops()

    def export_audio(self) -> None:
        """Save the recording (or the selection) as it sounds: at the speed and pitch chosen, and, if asked, as
        it is heard (Hear)."""
        if not self.audio:
            return
        player = self.player
        channels, filter_ = player.hearing
        plain = (channels, filter_) == ("both", "none")
        dialog = ExportDialog(self, self.selection, player.speed, player.pitch, player.formants,
                              None if plain else hearing_short(channels, filter_),
                              self.settings.value("export/format", "wav"))
        if not dialog.exec():
            return
        format_ = dialog.chosen_format()
        self.settings.setValue("export/format", format_)
        folder = Path(self.settings.value("export/folder", str(self.audio.path.parent)))
        suggestion = folder / suggested_name(self.audio.path, player.speed, player.pitch, format_)
        suffix = export.FORMATS[format_][0]
        path, _ = QFileDialog.getSaveFileName(self, tr("Export the audio"), str(suggestion),
                                              f"{dialog.format.currentText()} (*{suffix})")
        if not path:
            return
        path = Path(path)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        self.settings.setValue("export/folder", str(path.parent))
        start, end = self.selection if dialog.part.isChecked() and self.selection else (0.0, None)
        settings = export.Settings(start=start, end=end, speed=player.speed, pitch=player.pitch,
                                   formants=player.formants,
                                   hearing=player.hearing if dialog.hearing.isChecked() else ("both", "none"))
        if run_export(self, self.audio, path, format_, settings):
            self.statusBar().showMessage(tr("Exported {name}", name=path.name), 6000)

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

    def edit_shortcuts(self) -> None:
        dialog = shortcuts.ShortcutsDialog(self.shortcut_actions, self.default_shortcuts, self)
        if dialog.exec():
            shortcuts.save(self.shortcut_actions, self.default_shortcuts, self.settings)

    def current_shortcut_rows(self) -> list[tuple[str, str]]:
        """(what, keys) of each action with keys, as they are now (they can be changed), and what the mouse
        does."""
        rows = []
        for action in self.shortcut_actions.values():
            keys = [k.toString(shortcuts.NATIVE) for k in action.shortcuts() if not k.isEmpty()]
            if keys:
                rows.append((shortcuts.plain(action.text()), "   ".join(keys)))
        rows += [(tr("Zoom around the pointer"), tr("Ctrl+wheel")), (tr("Select with the mouse"), tr("Shift+drag"))]
        return rows

    def show_shortcuts(self) -> None:
        rows = self.current_shortcut_rows()
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
