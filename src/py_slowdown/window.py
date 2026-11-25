"""La ventana principal de py-slowdown.

Arriba, la forma de onda; debajo, los mandos de la reproducción (al principio,
atrás, tocar o pausar, detener, adelante, al final), el tiempo y el volumen;
luego la velocidad y la altura (en semitonos y cents); a la derecha, el panel de los
marcadores y los bucles. Los menús repiten todo eso con sus atajos de teclado,
que se pueden cambiar.

La ventana tiene un solo archivo abierto a la vez. Al cerrarlo (o al abrir
otro, o al salir) guarda el punto donde iba, y al volver a abrirlo sigue de allí.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDial,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
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
from .countin import MAX_OFFSET, CountIn, CountInDialog, TapTempo, grid_offset, number, recording_tempo
from .exportdialog import ExportDialog, run_export, suggested_name
from .engine import MAX_BEATS, MAX_BPM, MAX_PITCH, MAX_SPEED, MIN_BPM, MIN_LOOP, MIN_SPEED, Output, Player, max_earlier
from .hearing import CHANNELS, FILTERS
from .interface import tr
from .panel import BookmarkPanel, LoopPanel
from .timefmt import clock
from .waveform import WaveformView

APP = "py-slowdown"
SPEED_STEP = 0.05
KNOB_GAP = 4  # píxeles entre las perillas de la altura y su botón 0
SEMITONE_TICK, CENT_TICK = 3, 5  # una marca cada tantos semitonos, o cents, alrededor de su perilla
MAX_CENTS = 50  # cents, centésimas de semitono, arriba o abajo: más allá, el semitono siguiente
SPEED_PRESETS = (50, 60, 70, 75, 80, 90, 100, 110, 125, 150)
COUNT_CHOICES = (1, 2, 3, 4, 5, 6, 7, 8, 12, 16)  # golpes de la cuenta previa, en su menú (el diálogo, de 1 a 16)
NORMAL_VOLUME = 100  # por ciento: el sonido de la grabación, lo más que da la perilla
BOOST = 1.5  # el refuerzo multiplica el sonido, sin que la perilla cambie de número
OLD_MAX_VOLUME = 150  # por ciento: lo más que guardaban las versiones 1.3 (sin refuerzo, la perilla llegaba allí)
SPEED_TICKS = (25, 50, 75, 100, 150, 200, 250, 300)  # por ciento, alrededor de la perilla de la velocidad
VOLUME_TICKS = (0, 25, 50, 75, 100)
WARNING = QColor(200, 30, 30)  # lo que pasa de lo normal (el volumen por encima de 100 %)


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


def split_pitch(pitch: float, cents_now: int = 0) -> tuple[int, int]:
    """PITCH (semitones, with decimals) as whole semitones and cents (-50 to 50): with CENTS_NOW, if those cents
    still fit (a semitone up keeps the cents of a tuning); else with the nearest semitone."""
    whole = pitch - cents_now / 100
    if abs(whole - round(whole)) < 0.005 and abs(round(whole)) <= MAX_PITCH:
        return int(round(whole)), cents_now
    semitones = math.floor(pitch + 0.5)
    return semitones, int(round((pitch - semitones) * 100))


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
        (tr("Play, or pause and go back to where it started"), tr("Space")),
        (tr("Continue from the last pause"), tr("Shift+Space")),
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
        (tr("The first beat is here (count-in)"), tr("Shift+C")),
        (tr("Open a file"), "Ctrl+O"),
        (tr("Close the file (the program stays open)"), "Ctrl+W"),
        (tr("Quit"), "Alt+F4   Ctrl+Q"),
        (tr("Save the .slx"), "Ctrl+S"),
        (tr("Export the audio"), "Ctrl+E"),
        (tr("Change the shortcuts"), tr("Settings > Keyboard shortcuts")),
    ]


class Knob(QDial):
    """A knob drawn as on an amplifier: a short pointer at the edge of its face, its value written in the middle
    (FORMAT gives the text), ticks around it (at TICKS, the one at TOP longer). TOP is the value straight up: the
    values below it share the left half of the dial and those above it the right half, so a range need not be
    even around it (the speed: 25% to 100% on the left, 100% to 300% on the right). Dragged around (the pointer
    follows the mouse), or STEP for each notch of the mouse wheel (not three, as Qt's); a double click goes back to
    HOME. Values above WARN (if any) are drawn in red."""

    SIZE = 52
    LOWEST, HIGHEST = 240.0, -60.0  # grados de la marca más baja (abajo a la izquierda) y la más alta

    def __init__(self, format_, ticks=(), top: int | None = None, home: int = 0, step: int = 1,
                 warn: int | None = None, parent=None):
        super().__init__(parent)
        self.format = format_
        self.ticks = tuple(ticks)
        self.top = top
        self.home = home
        self.step = step
        self.warn = warn
        self.setWrapping(False)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def text(self) -> str:
        """The value as it is written in the knob."""
        return self.format(self.value())

    def _top(self) -> float:
        # (sin TOP, el valor del medio: la escala pareja de siempre)
        return self.top if self.top is not None else (self.minimum() + self.maximum()) / 2

    def degrees(self, value: float) -> float:
        """The angle of VALUE, in degrees counterclockwise from the right: LOWEST at the minimum, 90 (straight
        up) at TOP, HIGHEST at the maximum."""
        low, high, top = self.minimum(), self.maximum(), self._top()
        if value <= top:
            share = (value - low) / (top - low) if top > low else 1.0
            return self.LOWEST - share * (self.LOWEST - 90.0)
        share = (value - top) / (high - top) if high > top else 0.0
        return 90.0 - share * (90.0 - self.HIGHEST)

    def angle(self, value: int) -> float:
        """The angle of VALUE in radians (see degrees)."""
        return math.radians(self.degrees(value))

    def value_at(self, x: float, y: float) -> int:
        """The value whose pointer is towards the point (X, Y) of the knob; below the knob, the nearest end."""
        degrees = math.degrees(math.atan2(self.height() / 2 - y, x - self.width() / 2))
        if degrees < -90.0:
            degrees += 360.0  # (abajo a la izquierda: de 180 a 270)
        degrees = min(self.LOWEST, max(self.HIGHEST, degrees))
        low, high, top = self.minimum(), self.maximum(), self._top()
        if degrees >= 90.0:
            value = low + (self.LOWEST - degrees) / (self.LOWEST - 90.0) * (top - low)
        else:
            value = top + (90.0 - degrees) / (90.0 - self.HIGHEST) * (high - top)
        return int(round(value))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self.value_at(event.position().x(), event.position().y()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self.value_at(event.position().x(), event.position().y()))
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        # (un panel táctil manda trozos de muesca: se juntan hasta una entera, 120)
        self._turned = getattr(self, "_turned", 0) + event.angleDelta().y()
        notches = int(self._turned / 120)
        if notches:
            self._turned -= notches * 120
            self.setValue(self.value() + notches * self.step)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.setValue(self.home)
        event.accept()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        palette = self.palette()
        center = QPointF(self.width() / 2, self.height() / 2)
        outer = min(self.width(), self.height()) / 2 - 1
        face = outer - 6

        def point(angle: float, radius: float) -> QPointF:
            return QPointF(center.x() + radius * math.cos(angle), center.y() - radius * math.sin(angle))

        # Las marcas alrededor, más larga la de arriba: del color del texto, algo transparente (el «Mid» del tema
        # es, en muchos temas oscuros, casi el del fondo, y no se veían).
        ink = QColor(palette.color(group, QPalette.ColorRole.WindowText))
        ink.setAlpha(150)
        painter.setPen(QPen(ink, 1))
        top = self._top()
        for value in self.ticks:
            if self.minimum() <= value <= self.maximum():
                inner = face + (1 if value == top else 3)
                painter.drawLine(point(self.angle(value), inner), point(self.angle(value), outer))
        # La cara de la perilla.
        rim = QColor(ink)
        rim.setAlpha(90)
        painter.setPen(QPen(rim, 1))
        painter.setBrush(palette.color(group, QPalette.ColorRole.Button))
        painter.drawEllipse(center, face, face)
        # El indicador: una raya corta en el borde de la cara, lejos del texto del centro; en rojo, más allá de WARN.
        loud = self.warn is not None and self.value() > self.warn and self.isEnabled()
        pointer = WARNING if loud else palette.color(group, QPalette.ColorRole.Highlight)
        angle = self.angle(self.value())
        painter.setPen(QPen(pointer, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(point(angle, face * 0.84), point(angle, face - 1))
        # El valor, en el centro.
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(loud)
        painter.setFont(font)
        painter.setPen(WARNING if loud else palette.color(group, QPalette.ColorRole.ButtonText))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()


def signed(unit: str):
    """The text of a knob around 0: +2 st, −15 ¢, 0 st."""
    def text(value: int) -> str:
        sign = "+" if value > 0 else ("−" if value < 0 else "")
        return f"{sign}{abs(value)}{unit}"
    return text


class PitchDial(Knob):
    """A knob for the pitch, from -N to +N, 0 at the top, a tick every TICK steps; a double click takes it back
    to 0."""

    def __init__(self, unit: str, tick: int = 1, parent=None):
        super().__init__(signed(unit), top=0, home=0, step=1, parent=parent)
        self.unit = unit
        self.tick = tick

    def setRange(self, low: int, high: int) -> None:
        super().setRange(low, high)
        self.ticks = tuple(v for v in range(low, high + 1) if v % self.tick == 0 or v in (low, high))


class SaveDialog(QDialog):
    """Whether to save the changes of a recording before closing it: Save (with an arrow: always for this
    recording, always for all, never for this one), Discard, or Cancel. ANSWER says which: "save", "discard",
    "cancel", "always_file", "always_all" or "never_file"."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP)
        self.answer = "cancel"
        text = QLabel(tr("{name} has changes (bookmarks, loops or how it is played). Save them?", name=name), self)
        text.setWordWrap(True)
        icon = QLabel(self)
        icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion).pixmap(32, 32))
        # Guardar es un botón partido: el botón guarda; la flecha de al lado, lo que se hará en adelante.
        self.save = QToolButton(self)
        self.save.setText(tr("&Save"))
        self.save.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.save.setMinimumHeight(QPushButton().sizeHint().height())
        self.save.clicked.connect(lambda: self._done("save"))
        menu = QMenu(self.save)
        self.a_always_file = menu.addAction(tr("Always save, for this &recording"), lambda: self._done("always_file"))
        self.a_always_all = menu.addAction(tr("Always save, for &all recordings"), lambda: self._done("always_all"))
        self.a_never_file = menu.addAction(tr("&Never save this recording's changes"),
                                           lambda: self._done("never_file"))
        self.save.setMenu(menu)
        discard = QPushButton(tr("&Discard"), self)
        discard.clicked.connect(lambda: self._done("discard"))
        cancel = QPushButton(tr("Cancel"), self)
        cancel.clicked.connect(self.reject)
        for button in (discard, cancel):
            button.setAutoDefault(False)
        top = QHBoxLayout()
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(text, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.save, discard, cancel):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(buttons)
        self.save.setFocus()

    def _done(self, answer: str) -> None:
        self.answer = answer
        self.accept()

    def keyPressEvent(self, event) -> None:
        # Intro guarda, como el botón por omisión de cualquier diálogo; Esc cancela (el de QDialog).
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._done("save")
            return
        super().keyPressEvent(event)


class Window(QMainWindow):
    def __init__(self, player: Player | None = None, store: Store | None = None,
                 settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings(APP, APP)
        self.player = player or Player()
        self.store = store or Store()
        self.audio: Audio | None = None
        self._saved = ""  # what was saved of the file open (_snapshot), to tell its changes
        self.bookmarks: list[Bookmark] = []
        self.loops: list[Loop] = []
        self._resume = 0.0  # where to go once the file is decoded that far
        # Al pausar, la posición vuelve adonde empezó a tocar (para oír el pasaje otra vez); Continuar sigue
        # desde donde se pausó.
        self._return_to: float | None = None  # where playing started
        self._paused_at: float | None = None  # where the last pause was
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
        self.boost.setChecked(self.settings.value("volume_boost", False, type=bool))
        self.volume.setValue(int(self.settings.value("volume", NORMAL_VOLUME, type=int)))
        self._update_enabled()
        self._check_rubberband()
        self._update_formants()
        self.wave.setFocus()

    def _check_rubberband(self) -> None:
        """Without the Rubber Band Library, the files play only at 1× (and the window says why)."""
        try:
            rubberband.library()
        except rubberband.RubberBandError:
            self.stretching = False
            why = tr("The Rubber Band Library is not installed, so the speed stays at 1×.")
            for widget in (self.speed_knob, self.b_normal, self.b_speeds, self.semitone_dial,
                           self.cent_dial, self.b_pitch):
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
        # Un botón encendido (repetir, formantes) se ve lleno del color de selección del tema, no apenas hundido.
        self.transport.setStyleSheet(
            "QToolButton:checked { background-color: palette(highlight); color: palette(highlighted-text);"
            " border: 1px solid palette(highlight); border-radius: 3px; }"
            "QToolButton:checked:disabled { background-color: palette(mid); color: palette(window);"
            " border: 1px solid palette(mid); }")
        rows = QVBoxLayout(self.transport)
        rows.setContentsMargins(0, 4, 0, 0)
        rows.setSpacing(2)
        row = QHBoxLayout()
        rows.addLayout(row)
        row.addStretch()  # (y otro al final: la fila, centrada bajo la forma de onda)
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
        self.b_repeat.setToolTip(tr("Repeat the selection, or the whole file if there is none, without a pause (L); "
                                    "Shift+drag on the waveform selects"))
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
        row.addStretch()  # (y otro al final: la fila, centrada)

        row.addWidget(QLabel(tr("Speed"), self))
        # La velocidad, en por ciento, con 100 % arriba: de 25 a 100 a la izquierda, de 100 a 300 a la derecha.
        self.speed_knob = Knob(lambda value: f"{value}%", SPEED_TICKS, top=100, home=100,
                               step=round(SPEED_STEP * 100), parent=self)
        self.speed_knob.setRange(round(MIN_SPEED * 100), round(MAX_SPEED * 100))
        self.speed_knob.setPageStep(25)
        self.speed_knob.setValue(100)
        self.speed_knob.setToolTip(tr("The speed: slower or faster (Down, Up; the mouse wheel by 5%), the pitch "
                                      "stays the same; a double click goes back to 100%"))
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
        row.addWidget(self.speed_knob)
        row.addWidget(self.b_normal)
        row.addWidget(self.b_speeds)
        row.addSpacing(8)

        # La altura: semitonos y cents (centésimas de semitono), cada uno con su rueda y su valor.
        row.addWidget(QLabel(tr("Pitch"), self))
        semitones_tip = tr("The pitch, in semitones, up or down (Ctrl+↑, Ctrl+↓); the speed does not change")
        cents_tip = tr("Cents, hundredths of a semitone, up or down: to tune the recording to an instrument")
        self.semitone_dial = self._pitch_dial(int(MAX_PITCH), tr(" st"), semitones_tip)
        self.cent_dial = self._pitch_dial(MAX_CENTS, " ¢", cents_tip)
        self.b_pitch = QToolButton(self)
        self.b_pitch.setText("ø")  # (la altura original)
        self.b_pitch.setToolTip(tr("Original pitch (Shift+N)"))
        self.b_pitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.b_pitch.setEnabled(False)
        # Las perillas, cada una con su valor dentro, y el 0, a la misma distancia unas de otras.
        knobs = QHBoxLayout()
        knobs.setSpacing(KNOB_GAP)
        for widget in (self.semitone_dial, self.cent_dial, self.b_pitch):
            knobs.addWidget(widget)
        row.addLayout(knobs)
        self._show_pitch(0.0)
        row.addSpacing(12)

        # El volumen: hasta 100 % (el sonido de la grabación), o hasta 150 % con el refuerzo, en rojo.
        speaker = QLabel(self)
        speaker.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume).pixmap(20, 20))
        speaker.setToolTip(tr("Volume"))
        row.addWidget(speaker)
        self.volume = Knob(lambda value: f"{value}%", VOLUME_TICKS, top=None, home=NORMAL_VOLUME, step=5,
                           parent=self)
        self.volume.setRange(0, NORMAL_VOLUME)
        self.volume.setPageStep(10)
        self.volume.setValue(NORMAL_VOLUME)
        row.addWidget(self.volume)
        self.boost = QCheckBox(tr("Boost"), self)
        self.boost.setToolTip(tr("Volume boost: the sound times 1.5, louder than the recording (it may distort); "
                                 "the knob keeps its number"))
        self.boost.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self.boost)
        self._show_volume(NORMAL_VOLUME)

        row.addStretch()
        self._update_skip_tips()

    def _pitch_dial(self, limit: int, unit: str, tip: str) -> PitchDial:
        # Una perilla, de -LIMIT a LIMIT (el 0 arriba), para los semitonos o los cents de la altura, con su valor
        # escrito dentro.
        dial = PitchDial(unit, SEMITONE_TICK if limit <= 12 else CENT_TICK, self)
        dial.setRange(-limit, limit)
        dial.setPageStep(max(1, limit // 4))
        dial.setToolTip(tip)
        return dial

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
        # (teclas fijas, no las «estándar» de Qt, que cambian con el escritorio: Ctrl+W cierra el archivo y el
        # programa sigue; Alt+F4, o Ctrl+Q, cierra el programa)
        self.a_close = a(tr("&Close"), self.close_file, ["Ctrl+W", "Ctrl+F4"])
        self.a_save_slx = a(tr("&Save the .slx"), self.save_sidecar, [QKeySequence.StandardKey.Save])
        self.a_export_audio = a(tr("E&xport the audio…"), self.export_audio, ["Ctrl+E"])
        self.a_quit = a(tr("&Quit"), self.close, ["Ctrl+Q", "Alt+F4"])
        self.a_play = a(tr("&Play/Pause"), self.toggle, ["Space"])
        self.a_continue = a(tr("&Continue from the pause"), self.continue_playing, ["Shift+Space"])
        self.a_stop = a(tr("&Stop"), self.stop, ["S"])
        self.a_start = a(tr("Go to the s&tart"), self.go_start, ["Home"])
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
        self.a_formants.setStatusTip(tr("Keep the formants: when the pitch moves, voices and instruments keep their "
                                        "natural timbre"))
        self.a_repeat = a(tr("&Repeat (the selection, or the whole file)"), self._set_repeat, ["L"], checkable=True)
        self.a_sel_start = a(tr("Select&ion starts here"), lambda: self.mark_selection(start=True), ["I"])
        self.a_sel_end = a(tr("Selection ends &here"), lambda: self.mark_selection(start=False), ["O"])
        self.a_sel_clear = a(tr("Clear the selecti&on"), lambda: self.set_selection(None), ["Esc"])
        self.a_save_loop = a(tr("Sa&ve the selection as a loop"), self.save_loop, ["Shift+L"])
        self.a_count = a(tr("&Count in before playing"), self._set_count_on, ["C"], checkable=True)
        self.a_count.setChecked(self.count.on)
        self.a_count_settings = a(tr("Co&unt-in settings…"), self.count_settings)
        self.a_tap = a(tr("Tap the tempo"), self.tap_tempo, ["T"])
        self.a_first_beat = a(tr("The &first beat is here"), lambda: self.set_first_beat(None), ["Shift+C"])
        self.a_no_first_beat = a(tr("&Remove the first beat"), self.remove_first_beat)
        self.a_ask_save = a(tr("As&k to save before closing a file"), self._set_ask_save, checkable=True)
        self.a_ask_save.setChecked(self.settings.value("ask_save", True, type=bool))
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
        file.addAction(self.a_save_slx)
        file.addAction(self.a_export_audio)
        file.addAction(self.a_close)
        file.addSeparator()
        file.addAction(self.a_quit)

        play = bar.addMenu(tr("&Playback"))
        for action in (self.a_play, self.a_continue, self.a_stop, None, self.a_start, self.a_back, self.a_back_1,
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
        self.clicks_menu = QMenu(tr("C&licks"), self)
        self.clicks_menu.aboutToShow.connect(self._fill_clicks_menu)
        for action in (self.a_count, self.a_tap, self.clicks_menu, None, self.a_first_beat, self.a_no_first_beat,
                       None, self.a_count_settings):
            if action is None:
                count.addSeparator()
            elif isinstance(action, QMenu):
                count.addMenu(action)
            else:
                count.addAction(action)

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
        settings.addAction(self.a_ask_save)
        # Lo que la grabación abierta tiene por su cuenta (desde la flecha de Guardar, o aquí).
        self.file_saving_menu = settings.addMenu(tr("Changes of &this recording"))
        group = QActionGroup(self)
        self.a_file_saving: dict[str, QAction] = {}
        for value, name in (("", tr("&As for all recordings")), ("always", tr("A&lways saved")),
                            ("never", tr("&Never saved"))):
            action = self.file_saving_menu.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, v=value: self._set_file_saving(v))
            group.addAction(action)
            self.a_file_saving[value] = action
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
        self.b_start.clicked.connect(self.go_start)
        self.b_end.clicked.connect(self.go_end)
        self.b_back.clicked.connect(lambda: self.jump(-self.skip))
        self.b_forward.clicked.connect(lambda: self.jump(self.skip))
        self.b_mark.clicked.connect(self.add_bookmark)
        self.b_normal.clicked.connect(lambda: self.set_speed(1.0))
        self.b_pitch.clicked.connect(lambda: self.set_pitch(0.0))
        for dial in (self.semitone_dial, self.cent_dial):
            dial.valueChanged.connect(self._pitch_moved)
        self.speed_knob.valueChanged.connect(lambda v: self.set_speed(v / 100))
        self.volume.valueChanged.connect(self._set_volume)
        self.boost.toggled.connect(self._set_boost)
        self.wave.seekRequested.connect(self.seek)
        self.wave.addBookmarkRequested.connect(self.add_bookmark_at)
        self.wave.removeBookmarkRequested.connect(self.remove_bookmark)
        self.wave.renameBookmarkRequested.connect(self.rename_bookmark)
        self.wave.selectionChanged.connect(self.set_selection)
        self.wave.firstBeatRequested.connect(self.set_first_beat)
        self.b_repeat.toggled.connect(self.a_repeat.setChecked)
        self.a_repeat.toggled.connect(self.b_repeat.setChecked)
        self.b_tap.clicked.connect(self.tap_tempo)
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
        own = f"*{sidecar.EXTENSION}"
        start = self.settings.value("folder", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open an audio file"), start,
            f"{tr('Audio and video files')} ({patterns} {own});;{tr('Settings of a recording')} ({own});;"
            f"{tr('All files')} (*)")
        if path:
            self.open_file(path)

    def open_file(self, path: str | Path) -> bool:
        """Open the audio or video file at PATH; or, if PATH is a .slx, the recording it is of, as it says."""
        path = Path(path)
        given = None
        if path.suffix.lower() == sidecar.EXTENSION:
            audio_path = sidecar.owner(path)
            given = sidecar.read(path) if audio_path is not None else None
            if given is None:
                QMessageBox.warning(self, APP, tr("Cannot find the recording of {name}.", name=path.name))
                return False
            path = audio_path
        if not self.close_file():
            return False  # (cancelado: queda el archivo de antes)
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
        kept = given or self._read_sidecar(path)
        self.bookmarks = kept.bookmarks if kept else self.store.bookmarks(path)
        self._show_bookmarks()
        self.loops = kept.loops if kept else self.store.loops(path)
        self.loop_panel.show_loops(self.loops)
        # Cada archivo empieza con lo de siempre, y luego con lo que se guardó de él (no con lo del anterior).
        self._reset_file_settings()
        self._apply_file_settings(kept.settings if kept else self.store.settings(path))
        # Sigue donde se dejó, cuando el archivo esté decodificado hasta allí (_tick).
        self._resume = kept.position if kept else self.store.position(path)
        self._saved = self._snapshot()  # (lo de ahora es lo guardado: los cambios se cuentan desde aquí)
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

    def _set_ask_save(self, on: bool) -> None:
        self.settings.setValue("ask_save", on)
        if not on and self.audio is not None and self._changed():
            self._save_all()  # (sin preguntar, todo se guarda como se hace: también lo pendiente)
        self._show_title()

    def _snapshot(self) -> str:
        # Lo que se guarda de un archivo, salvo la posición (moverla no es un cambio que haya que preguntar).
        marks = [(round(b.time, 3), b.label, b.first_beat) for b in self.bookmarks]
        loops = [(round(x.start, 3), round(x.end, 3), x.label) for x in self.loops]
        return json.dumps([self._file_settings(), marks, loops], sort_keys=True, default=str)

    def _changed(self) -> bool:
        """Whether the file open has changes not saved yet (only while Ask to save is on: else all is saved as
        it is done)."""
        return self.audio is not None and self._saving() == "ask" and self._snapshot() != self._saved

    def _saving(self) -> str:
        """How the changes of the file open are saved: "ask" (on closing it), "always" (as they are made) or
        "never"; the file's own choice first, else Settings > Ask to save before closing a file."""
        own = self.store.saving(self.audio.path) if self.audio is not None else ""
        return own or ("ask" if self.a_ask_save.isChecked() else "always")

    def _show_title(self) -> None:
        if self.audio is None:
            self.setWindowTitle(APP)
            return
        mark = "• " if self._changed() else ""  # (cambios sin guardar)
        never = " " + tr("(changes not saved)") if self._saving() == "never" else ""
        title = f"{mark}{self.audio.path.name}{never} — {APP}"
        if self.windowTitle() != title:
            self.setWindowTitle(title)

    def _save_all(self, asked: bool = False) -> None:
        """Save what there is of the file open: in bookmarks.json and in its .slx (ASKED: also with Not
        saved, beside the recording)."""
        if self.audio is None:
            return
        path = self.audio.path
        self.store.set_bookmarks(path, self.bookmarks)
        self.store.set_loops(path, self.loops)
        self.store.set_settings(path, self._file_settings())
        self.store.set_position(path, self._position_to_keep())
        self._write_sidecar(asked)
        self._saved = self._snapshot()
        self._show_title()

    def _ask_save(self, name: str) -> str:
        """Ask whether to save the changes of NAME: "save", "discard", "cancel", or, from the arrow of Save,
        "always_file" (always save this recording's), "always_all" (all recordings') or "never_file"."""
        dialog = SaveDialog(name, self)
        dialog.exec()
        return dialog.answer

    def _set_file_saving(self, saving: str) -> None:
        """How the changes of the recording open are saved, its own choice: "always", "never", or "" (as for all
        recordings, Settings > Ask to save before closing a file)."""
        if self.audio is None:
            return
        self.store.set_saving(self.audio.path, saving)
        if self._saving() == "always" and self._snapshot() != self._saved:
            self._save_all()  # (lo pendiente, ahora: en adelante se guarda al hacerlo)
        self._show_file_saving()
        self._show_title()

    def _show_file_saving(self) -> None:
        own = self.store.saving(self.audio.path) if self.audio is not None else ""
        self.a_file_saving[own].setChecked(True)
        self.file_saving_menu.setEnabled(self.audio is not None)

    def _set_reopen(self, on: bool) -> None:
        self.settings.setValue("reopen", on)

    def close_file(self) -> bool:
        """Close the file open, saving what there is of it; with Ask to save on and changes, after asking.
        False if the user cancelled (the file stays open)."""
        if self.audio is None:
            return True
        path = self.audio.path
        if self._changed():
            answer = self._ask_save(path.name)
            if answer == "cancel":
                return False
            if answer == "always_file":
                self.store.set_saving(path, "always")  # (esta grabación: en adelante, sin preguntar)
            elif answer == "always_all":
                self.a_ask_save.setChecked(False)  # (todas: Configuración > Preguntar antes de cerrar, apagado)
            elif answer == "never_file":
                self.store.set_saving(path, "never")
            if answer in ("save", "always_file", "always_all"):
                self._save_all()
            else:
                self.store.set_position(path, self._position_to_keep())  # (lo demás, como estaba)
        elif self._saving() == "never":
            self.store.set_position(path, self._position_to_keep())  # (sus cambios no se guardan)
        else:
            self._save_all()
        audio = self.audio
        self.player.unload()
        audio.close()
        self.audio = None
        self.bookmarks = []
        self.loops = []
        self.loop_panel.show_loops(self.loops)
        self._resume = 0.0
        self._return_to = self._paused_at = None
        self._pending_selection = None
        self.wave.set_audio(None)
        self.selection = None
        self.wave.set_selection(None)
        self._show_bookmarks()
        self.setWindowTitle(APP)
        self.statusBar().clearMessage()
        self._update_enabled()
        return True

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
        elif self.a_repeat.isChecked():
            kept["repeat"] = True  # (sin selección: el archivo entero)
        if self.volume.value() != 100:
            kept["volume"] = self.volume.value()
        if self.count.on or self.first_beat() is not None:
            # (el tempo y el desfase de la cuenta son de cada pieza; con un primer pulso, aunque esté apagada)
            kept["countin"] = {"bpm": self.count.bpm, "offset": self.count.offset, "on": self.count.on}
        return kept

    def _reset_file_settings(self) -> None:
        """What belongs to each piece back to the usual: speed 1×, the recording's pitch, the formants off, both
        channels without a filter, the count-in off, at 100 BPM, without offset, and the volume at 100%; the
        count-in's clicks, the user's, stay."""
        if self.stretching:
            self.set_speed(1.0)
            self.set_pitch(0.0)
            self.a_formants.setChecked(False)
        else:
            self.set_speed(self.player.speed)
        self.set_hearing("both", "none")
        self.a_repeat.setChecked(False)
        default = CountIn()
        self.count.bpm, self.count.offset = default.bpm, default.offset
        self.a_count.setChecked(False)  # (un archivo con la cuenta guardada encendida la recibe luego)
        self.volume.setValue(100)
        self.count.save(self.settings)
        self._update_count_tip()

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
            elif kept.get("repeat"):
                self.a_repeat.setChecked(True)  # (el archivo entero)
            if "volume" in kept:
                volume = int(min(OLD_MAX_VOLUME, max(0, int(kept["volume"]))))
                if volume > NORMAL_VOLUME:
                    # (de una versión 1.3, más fuerte que la grabación: con el refuerzo, lo que suena casi igual)
                    self.boost.setChecked(True)
                    volume = min(NORMAL_VOLUME, round(volume / math.sqrt(BOOST)))
                self.volume.setValue(volume)
            countin = kept.get("countin")
            if isinstance(countin, dict):
                self.count.bpm = int(min(MAX_BPM, max(MIN_BPM, int(countin.get("bpm", self.count.bpm)))))
                self.count.offset = min(MAX_OFFSET, max(-MAX_OFFSET, float(countin.get("offset", 0.0))))
                self.a_count.setChecked(bool(countin.get("on", True)))
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

    def _write_sidecar(self, asked: bool = False) -> Path | None:
        """Write the .slx of the file open, where the settings say; ASKED (File > Save the .slx), also when they
        say Not saved, then beside the recording. Its path, or None."""
        on, folder = self._sidecar_place()
        if (not on and not asked) or self.audio is None:
            return None
        state = sidecar.FileState(self._position_to_keep(), self._file_settings(), list(self.bookmarks),
                                  list(self.loops))
        try:
            return sidecar.save(self.audio.path, state, folder)
        except OSError as error:
            # (una carpeta de solo lectura, un disco lleno: bookmarks.json lo guarda de todos modos)
            self.statusBar().showMessage(tr("Cannot write the settings file of {name}: {error}",
                                            name=self.audio.path.name, error=error.strerror or error), 8000)
            return None

    def save_sidecar(self) -> None:
        """File > Save the .slx: save all now (bookmarks.json and the .slx), without closing the file."""
        if self.audio is None:
            return
        self._save_all(asked=True)
        path = sidecar.find(self.audio.path, self._sidecar_place()[1])
        if path is not None:
            self.statusBar().showMessage(tr("Saved {path}", path=str(path)), 5000)

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
        """Play from the position; or pause, and go back to where playing started, to hear the passage again
        (Continue from the pause goes on from where it was paused)."""
        if not self.audio:
            return
        if self.player.playing:
            self._pause()
        else:
            self._play()
            self._return_to = self.player.position  # (después de play: al final, vuelve a empezar desde 0)
        self._update_play_button()

    def continue_playing(self) -> None:
        """Play from where the last pause was, as a pause without going back would have left it; pausing
        then goes back to where playing first started, as before."""
        if not self.audio or self.player.playing:
            return
        if self._paused_at is None:
            self.toggle()
            return
        start = self._return_to
        self.player.seek(min(self._paused_at, self.audio.duration))
        self._play()
        self._return_to = start if start is not None else self.player.position
        self._update_play_button()

    def _play(self) -> None:
        if self.count.on:
            self.player.play(self.count.beats, self.count.tempo(self.player.speed), self.count_offset())
        else:
            self.player.play()

    def _pause(self) -> None:
        self.player.pause()
        self._paused_at = self.player.position
        back = self._return_point()
        if back is not None:
            self.player.seek(back)
            self.statusBar().showMessage(tr("Paused at {time}; back to {start} (Shift+Space continues from the "
                                            "pause)", time=clock(self._paused_at, tenths=True),
                                            start=clock(back, tenths=True)), 4000)
        self._tick()

    def _return_point(self) -> float | None:
        # Adonde vuelve la posición: donde empezó a tocar; con una selección que se repite, dentro de ella.
        back = self._return_to
        loop = self.player.loop
        if back is not None and loop and not loop[0] <= back < loop[1]:
            back = loop[0]
        return back

    # --- la cuenta previa y la selección repetida

    def _set_count_on(self, on: bool) -> None:
        self.count.on = on
        self.count.save(self.settings)
        if "a_count_settings" in vars(self):
            # (al armar las acciones, la cuenta guardada encendida llega aquí antes que las demás; _connect lo dice)
            self._update_count_tip()

    def count_settings(self) -> None:
        beat = self.first_beat()
        dialog = CountInDialog(self.count, self.player.speed, self, beat.time if beat else None)
        if dialog.exec():
            self.count = dialog.value()
            self.count.save(self.settings)
            self.a_count.setChecked(self.count.on)
            self._update_count_tip()

    def _fill_clicks_menu(self) -> None:
        # Cuántos golpes da la cuenta previa; el de ahora, marcado (también si se eligió otro en el diálogo).
        menu = self.clicks_menu
        menu.clear()
        group = QActionGroup(menu)
        for beats in sorted(set(COUNT_CHOICES) | {self.count.beats}):
            action = menu.addAction(str(beats))
            action.setCheckable(True)
            action.setChecked(beats == self.count.beats)
            action.triggered.connect(lambda _=False, n=beats: self.set_count_beats(n))
            group.addAction(action)

    def set_count_beats(self, beats: int) -> None:
        """How many clicks the count-in gives (1 to 16; 4 at first)."""
        self.count.beats = min(MAX_BEATS, max(1, int(beats)))
        self.count.save(self.settings)
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

    def first_beat(self) -> Bookmark | None:
        """The bookmark of the recording's first beat, if the file has one."""
        return next((mark for mark in self.bookmarks if mark.first_beat), None)

    def count_offset(self) -> float:
        """How far (seconds of the recording) the recording comes in after the beat that follows the count,
        playing from the position: with a first beat, on the nearest beat of its grid (grid_offset); without
        one, the offset of the count-in's settings."""
        beat = self.first_beat()
        if beat is None or self.audio is None:
            return self.count.offset
        earliest = max_earlier(self.audio.rate, self.count.tempo(self.player.speed))
        return grid_offset(self.player.position, beat.time, self.count.bpm, self.player.speed, earliest)

    def set_first_beat(self, seconds: float | None) -> None:
        """The recording's first beat at SECONDS (None: at the position), a bookmark of its own that is kept
        with the others: the count-in then brings the recording in on the beats from there, at its tempo,
        wherever it is played from. There is one: the one there was moves. The count-in is turned on."""
        if not self.audio:
            return
        here = self.player.position if seconds is None else seconds
        here = round(min(max(0.0, here), self.audio.duration), 3)
        old = self.first_beat()
        near = next((m for m in self.bookmarks if not m.first_beat and abs(m.time - here) < 0.05), None)
        if near is not None:
            # (un marcador que ya está allí se vuelve el primer pulso, con su nombre)
            if old is not None:
                self.bookmarks.remove(old)
            near.first_beat = True
            near.label = near.label or (old.label if old else tr("First beat"))
            mark = near
        elif old is not None:
            old.time = here
            mark = old
        else:
            mark = Bookmark(here, tr("First beat"), first_beat=True)
            self.bookmarks.append(mark)
        self.bookmarks.sort(key=lambda b: b.time)
        self._save_bookmarks()
        self._show_bookmarks(self.bookmarks.index(mark))
        self.a_count.setChecked(True)
        self.count.save(self.settings)
        self._update_count_tip()
        self.statusBar().showMessage(tr("Count-in: the first beat at {time}; the recording comes in on its beats, "
                                        "at {bpm} BPM.", time=clock(here, tenths=True), bpm=self.count.bpm), 8000)

    def remove_first_beat(self) -> None:
        """Remove the bookmark of the first beat: the count-in goes back to the offset of its settings."""
        mark = self.first_beat()
        if mark is not None:
            self.remove_bookmark(self.bookmarks.index(mark))

    def _update_count_tip(self) -> None:
        # Lo que la cuenta hace ahora: la barra de estado lo dice al pasar sobre sus acciones, en el menú.
        count = self.count
        if count.follow:
            what = tr("{beats} clicks at {bpm} BPM, following the speed", beats=count.beats, bpm=count.bpm)
        else:
            what = tr("{beats} clicks at {bpm} BPM", beats=count.beats, bpm=count.bpm)
        beat = self.first_beat()
        if beat is not None:
            what += tr("; on the beats of the first beat ({time})", time=clock(beat.time, tenths=True))
        elif count.offset:
            signed = ("+" if count.offset > 0 else "−") + number(abs(count.offset))
            what += tr("; the recording {offset} s off the beat", offset=signed)
        # Ir al principio va al primer pulso con la cuenta encendida: el botón y el menú lo dicen.
        if self.count.on and beat is not None:
            start = tr("Go to the first beat, {time} (Home): the count-in is on",
                       time=clock(beat.time, tenths=True))
        else:
            start = tr("Go to the start (Home)")
        self.b_start.setToolTip(start)
        self.a_start.setStatusTip(start)
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
            self.statusBar().showMessage(tr("Repeating the whole file (to repeat only a part, select it: Shift+drag "
                                            "on the waveform, or I and O)"), 6000)

    def _apply_loop(self) -> None:
        if self.audio:
            loop = None
            if self.a_repeat.isChecked():
                # Sin selección, el archivo entero, una vez leído (antes, su final no se sabe: _tick lo pone luego).
                whole = (0.0, self.audio.duration) if self.audio.done else None
                loop = self.selection or whole
            if loop != self.player.loop:
                self.player.set_loop(loop)

    def stop(self) -> None:
        self.player.stop()
        self._return_to = self._paused_at = None
        self._update_play_button()

    def seek(self, seconds: float) -> None:
        if self.audio:
            self.player.seek(seconds)
            self._resume = 0.0
            if self.player.playing:
                self._return_to = self.player.position  # (llevada a otro lugar mientras suena: desde allí)
            self._tick()

    def jump(self, seconds: float) -> None:
        if self.audio:
            self.seek(max(0.0, self.player.position + seconds))

    def start_point(self) -> float:
        """Where Go to the start goes: with the count-in on, the first beat, if the file has one (so that the
        count-in brings the recording in on it); else the beginning of the file."""
        beat = self.first_beat()
        return beat.time if self.count.on and beat is not None else 0.0

    def go_start(self) -> None:
        if self.audio:
            self.seek(self.start_point())

    def go_end(self) -> None:
        if self.audio:
            self.seek(self.audio.duration)

    def set_speed(self, speed: float) -> None:
        speed = min(MAX_SPEED, max(MIN_SPEED, round(float(speed), 2)))
        self.player.speed = speed
        # The knob is brought in line without calling this again.
        self.speed_knob.blockSignals(True)
        self.speed_knob.setValue(round(speed * 100))
        self.speed_knob.blockSignals(False)
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
        self._show_pitch(self.player.pitch)
        self.b_pitch.setEnabled(self.player.pitch != 0.0)
        self._update_formants()

    def _pitch_moved(self, _value: int = 0) -> None:
        # Una barra o una casilla de la altura: los semitonos más los cents.
        self.set_pitch(self.semitone_dial.value() + self.cent_dial.value() / 100)

    def _show_pitch(self, pitch: float) -> None:
        """The pitch in the bars and boxes, as semitones and cents: as they are, if they already say it (so that
        the semitones do not jump while the cents move); else with the cents they have, if they fit; else with
        the nearest semitone."""
        semitones, cents = split_pitch(pitch, self.cent_dial.value())
        if abs(self.semitone_dial.value() + self.cent_dial.value() / 100 - pitch) < 0.005:
            semitones, cents = self.semitone_dial.value(), self.cent_dial.value()
        for dial, value in ((self.semitone_dial, semitones), (self.cent_dial, cents)):
            dial.blockSignals(True)
            dial.setValue(value)
            dial.blockSignals(False)
            dial.update()  # (su valor, escrito dentro: valueChanged estaba bloqueada)

    def set_quality(self, quality: str) -> None:
        """Stretch the sound with QUALITY: "high" (R3), "light" (R3 with a short window, half the processor) or
        "r2" (the older engine, with crisp attacks). It changes while it plays; exports always use "high"."""
        self.player.quality = quality
        self.a_qualities[quality].setChecked(True)
        self.settings.setValue("quality", quality)

    def _update_formants(self) -> None:
        # Los formantes solo cuentan cuando la altura se movió: si no, la acción está en gris (y guarda su estado).
        moved = self.stretching and self.player.pitch != 0.0
        self.a_formants.setEnabled(moved)

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

    def _gain(self, value: int) -> float:
        # A square curve (the steps of the knob sound more even to the ear), times 1.5 with Boost.
        return (value / 100) ** 2 * (BOOST if self.boost.isChecked() else 1.0)

    def _set_volume(self, value: int) -> None:
        self.player.volume = self._gain(value)
        self.settings.setValue("volume", value)
        self._show_volume(value)

    def _show_volume(self, value: int) -> None:
        """The volume knob's tooltip; where Boost makes the sound louder than the recording's, the knob draws its
        value (the same number) and pointer in red."""
        tip = tr("Volume: {percent}%", percent=value)
        if self.boost.isChecked():
            tip += " " + tr("(boosted: the sound times 1.5)")
        if self._gain(value) > 1.0:
            tip += " " + tr("(louder than the recording: it may distort)")
        # (en rojo desde el primer valor que, con el refuerzo, pasa del sonido de la grabación: 82 %)
        self.volume.warn = math.ceil(100 / math.sqrt(BOOST)) - 1 if self.boost.isChecked() else None
        self.volume.setToolTip(tip + "; " + tr("a double click goes back to 100%"))
        self.volume.update()

    def _set_boost(self, on: bool) -> None:
        """Volume boost: the sound times 1.5, the knob's number as it is."""
        self.settings.setValue("volume_boost", on)
        self._set_volume(self.volume.value())

    def _tick(self) -> None:
        audio = self.audio
        if audio is None:
            return
        self._show_title()
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
            if self._return_point() is not None:
                # (al acabar el archivo, también vuelve adonde empezó a tocar)
                self.player.seek(self._return_point())
                self._paused_at = None
            self._update_play_button()
        position = self.player.position
        self.wave.follow_reading()
        self.wave.set_position(position, self.player.playing)
        counting = self.player.counting()
        self.wave.set_count(counting[0] if counting and counting[0] else None)
        # Con la cuenta previa, y sin sonar, dónde espera el primer pulso de la grabación.
        offset = self.count_offset() if self.count.on and not self.player.playing else 0.0
        beat = position - offset if offset else None
        self.wave.set_first_beat(beat if beat is None or beat >= 0 else None)
        # La última pausa, mientras no suena: desde allí sigue Mayús+Espacio.
        paused = self._paused_at if not self.player.playing else None
        self.wave.set_pause_mark(paused if paused is not None and abs(paused - position) > 0.01 else None)
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
            self._apply_loop()  # (repetir el archivo entero: ahora se sabe dónde termina)
        elif not audio.done and audio.estimated and audio.length:
            share = min(99, int(100 * audio.decoded / audio.length))
            self.statusBar().showMessage(tr("Reading {name}… {percent}%", name=audio.path.name, percent=share))

    def _describe(self, audio: Audio) -> str:
        channels = tr("mono") if audio.channels == 1 else tr("stereo")
        return f"{audio.path.name} · {audio.codec} · {audio.rate} Hz · {channels} · {clock(audio.duration)}"

    def _update_play_button(self) -> None:
        playing = self.player.playing
        self.b_play.setProperty("playing", playing)
        self.a_continue.setEnabled(self.audio is not None and not playing and self._paused_at is not None)
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.b_play.setIcon(self.style().standardIcon(icon))
        self.b_play.setToolTip(tr("Pause and go back to where it started (Space); Shift+Space continues from the "
                                  "pause") if playing else tr("Play (Space)"))

    def _update_enabled(self) -> None:
        loaded = self.audio is not None
        self._show_file_saving()
        for widget in (self.b_start, self.b_back, self.b_play, self.b_stop, self.b_forward, self.b_end,
                       self.b_mark, self.b_repeat, self.panel.add_button):
            widget.setEnabled(loaded)
        for action in (self.a_close, self.a_save_slx, self.a_export_audio, self.a_play, self.a_stop, self.a_start, self.a_end, self.a_back,
                       self.a_forward, self.a_back_1, self.a_forward_1, self.a_mark, self.a_prev_mark,
                       self.a_next_mark, self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_repeat,
                       self.a_sel_start, self.a_sel_end, self.a_sel_clear):
            action.setEnabled(loaded)
        self.a_export.setEnabled(loaded and bool(self.bookmarks))
        self.a_first_beat.setEnabled(loaded)
        self.a_no_first_beat.setEnabled(loaded and self.first_beat() is not None)
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
        self.a_no_first_beat.setEnabled(self.audio is not None and self.first_beat() is not None)
        self._update_count_tip()

    def _save_bookmarks(self) -> None:
        # En bookmarks.json y, enseguida, en el .slx de la grabación (no solo al cerrarla); con Preguntar antes
        # de cerrar, solo cuando se guarde.
        if self.audio and self._saving() == "always":
            self.store.set_bookmarks(self.audio.path, self.bookmarks)
            self._write_sidecar()
        self._show_title()

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
        if self.audio and self._saving() == "always":
            self.store.set_loops(self.audio.path, self.loops)
            self._write_sidecar()
        self._show_title()

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
        if not self.close_file():
            event.ignore()  # (cancelado: el programa sigue)
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        super().closeEvent(event)
