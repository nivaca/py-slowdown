"""La forma de onda: el audio dibujado, la posición y los marcadores.

Waveform dibuja el mínimo y el máximo de cada columna de píxeles: con los picos
que Audio calculó (Peaks) cuando la vista es amplia, y con las muestras mismas
cuando se acerca más que un grupo de picos por píxel. La parte ya tocada va en
otro color; encima, una regla de tiempos, la línea de la posición y los
marcadores con su nombre, y la selección que se repite. Un clic lleva la
posición allí; arrastrar la sigue; Mayús+arrastrar hace una selección;
Ctrl+rueda acerca o aleja la vista alrededor del puntero, y la rueda sola la
corre. Durante la cuenta previa, el pulso se ve en grande. WaveformView le pone una barra de desplazamiento debajo.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import QMenu, QScrollBar, QSizePolicy, QVBoxLayout, QWidget

from .audio import BUCKET, Audio
from .bookmarks import Bookmark
from .interface import tr
from .timefmt import clock

RULER = 22  # height of the ruler, in pixels
LANE = 16  # alto de la franja de los bucles, al pie de la forma de onda
# Los colores de los bucles, uno tras otro (de la paleta de Okabe e Ito, que se distinguen también sin ver bien
# los colores)
LOOP_COLORS = ("#e69f00", "#56b4e9", "#009e73", "#cc79a7", "#d55e00", "#0072b2", "#f0e442")
FLAG = 16  # alto de la banda de los marcadores
MIN_FPP = 1.0  # a lo sumo un cuadro por píxel
GRAB = 5  # píxeles a cada lado de un marcador que cuentan como suyos

# Pasos de la regla, en segundos: se usa el primero que deje unos 90 píxeles entre marcas.
# Mientras se lee un archivo, la onda se redibuja a lo sumo cada tanto (segundos): cada vez se rehacen sus imágenes.
READ_REDRAW = 0.2

STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)


def columns(audio: Audio, start: float, fpp: float, width: int) -> tuple[np.ndarray, np.ndarray]:
    """(lo, hi) of each of WIDTH pixel columns from frame START at FPP frames per pixel.

    Columns past the decoded audio are NaN.
    """
    lo = np.full(width, np.nan, np.float32)
    hi = np.full(width, np.nan, np.float32)
    edges = start + np.arange(width + 1) * fpp
    if fpp >= BUCKET:
        peaks = audio.peaks
        count = peaks.count
        idx = np.floor(edges / BUCKET).astype(np.int64)
        valid = np.flatnonzero((idx[:-1] < count) & (idx[:-1] >= 0))
        if valid.size:
            first = idx[valid]
            lo[valid] = np.minimum.reduceat(peaks.lo[:count], first)
            hi[valid] = np.maximum.reduceat(peaks.hi[:count], first)
            # reduceat lleva cada tramo hasta el comienzo del siguiente; el último, hasta el final del arreglo
            stop = min(count, int(idx[valid[-1] + 1]))
            if stop > first[-1]:
                lo[valid[-1]] = peaks.lo[first[-1]:stop].min()
                hi[valid[-1]] = peaks.hi[first[-1]:stop].max()
        return lo, hi
    f0 = max(0, int(edges[0]))
    data = audio.frames(f0, math.ceil(edges[-1]) + 1)
    if not len(data):
        return lo, hi
    mins, maxs = data.min(axis=1), data.max(axis=1)
    idx = np.floor(edges[:-1]).astype(np.int64) - f0
    valid = np.flatnonzero((idx >= 0) & (idx < len(data)))
    if valid.size:
        lo[valid] = np.minimum.reduceat(mins, idx[valid])
        hi[valid] = np.maximum.reduceat(maxs, idx[valid])
    return lo, hi


class Waveform(QWidget):
    seekRequested = Signal(float)  # seconds
    addBookmarkRequested = Signal(float)
    removeBookmarkRequested = Signal(int)
    renameBookmarkRequested = Signal(int)
    selectionChanged = Signal(object)  # (start, end) in seconds, or None
    firstBeatRequested = Signal(object)  # seconds: the recording's first beat, for the count-in
    viewChanged = Signal()
    loopClicked = Signal(int)  # the saved loop (its row) whose band is clicked
    recentRequested = Signal(str)  # a recording of the start screen, clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio: Audio | None = None
        self.bookmarks: list[Bookmark] = []
        self.position = 0.0  # seconds
        self.start = 0.0  # primer cuadro visible
        self.fpp = 0.0  # frames per pixel; 0: the whole file fits
        self.follow = True
        self.selection: tuple[float, float] | None = None  # seconds
        self.repeating = False  # whether the selection is repeated (it is drawn stronger)
        self.count: int | None = None  # the beat of a count-in, drawn big
        self.loops: list = []  # los bucles guardados (bookmarks.Loop), dibujados al pie
        self.recent: list[tuple[str, object]] = []  # sin archivo: las grabaciones recientes (ruta, resumen o None)
        self._hover_row: int | None = None
        self.flash: str | None = None  # un valor que acaba de cambiar (la velocidad, la altura), grande un momento
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._flash_step)
        self._flash_alpha = 0
        self.first_beat: float | None = None  # the beat on which the recording comes in after the count
        self.pause_mark: float | None = None  # where the last pause was, to continue from it (Shift+Space)
        self._dragging = False
        self._selecting: float | None = None  # where a Shift+drag began
        self._cache_key = None
        self._cache: tuple[np.ndarray, np.ndarray] | None = None
        self._reading = None  # lo que se dibujó de la lectura: (columna de lo leído, largo, terminado)
        self._read_drawn = 0.0  # cuándo (time.monotonic) se pidió el último dibujo por la lectura
        self._loudest = (0, 0.0)  # (picos revisados, el mayor de ellos): se revisan solo los nuevos
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # --- la vista

    def set_audio(self, audio: Audio | None) -> None:
        self.audio = audio
        self.position = 0.0
        self.start = 0.0
        self.fpp = 0.0
        self._cache_key = None
        self._reading = None
        self._loudest = (0, 0.0)
        self.viewChanged.emit()
        self.update()

    def follow_reading(self) -> None:
        """Redraw while the file is read: what was just read, and the whole file at its real length at the end."""
        # Sin esto la onda se quedaba como se dibujó al abrir el archivo, a medio leer o a la escala del largo
        # anunciado, hasta que otra cosa la redibujara (un clic, la ventana cambiada de tamaño).
        audio = self.audio
        if audio is None:
            return
        length = audio.length
        if self._reading is not None and self._reading[1] != length:
            # El largo cambió (el real, al terminar, o uno mayor que el anunciado): la vista entera lo sigue.
            if self.fpp and self.fpp >= self.fit_fpp():
                self.fpp = 0.0
            self.set_start(self.start)
            self.viewChanged.emit()
        # Solo cuando lo leído avanza una columna dentro de la vista, y no más de una vez cada READ_REDRAW
        # segundos (en una pantalla 4K cada dibujo rehace imágenes por unos 10 ms); al terminar, enseguida.
        reading = (self._read_column(self.width()), length, audio.done)
        now = time.monotonic()
        if reading != self._reading and (audio.done or now - self._read_drawn >= READ_REDRAW):
            self._reading = reading
            self._read_drawn = now
            self.update()

    def _read_column(self, w: int) -> int:
        """The column where what is read ends, -1 before the view and W + 1 past it."""
        return min(max(int((self.audio.decoded - self.start) / self.current_fpp()), -1), w + 1)

    def _loudest_peak(self) -> float:
        # El mayor pico leído hasta ahora, revisando solo los que llegaron desde la última vez.
        peaks = self.audio.peaks
        seen, loudest = self._loudest
        if peaks.count > seen:
            loudest = max(loudest, float(np.abs(peaks.lo[seen:peaks.count]).max()),
                          float(np.abs(peaks.hi[seen:peaks.count]).max()))
            self._loudest = (peaks.count, loudest)
        return loudest

    def fit_fpp(self) -> float:
        if not self.audio:
            return 1.0
        return max(MIN_FPP, self.audio.length / max(1, self.width()))

    def current_fpp(self) -> float:
        return self.fpp or self.fit_fpp()

    def visible_frames(self) -> float:
        return self.current_fpp() * self.width()

    def max_start(self) -> float:
        if not self.audio:
            return 0.0
        return max(0.0, self.audio.length - self.visible_frames())

    def set_start(self, frame: float) -> None:
        frame = min(max(0.0, frame), self.max_start())
        if frame != self.start:
            self.start = frame
            self.viewChanged.emit()
            self.update()

    def zoom(self, factor: float, anchor_x: float | None = None) -> None:
        """Show FACTOR times more detail, keeping the frame under ANCHOR_X in place."""
        if not self.audio:
            return
        if anchor_x is None:
            # Without a pointer: around the position if it is in view, else around the middle.
            px = self.x_of(self.position)
            anchor_x = px if 0 <= px <= self.width() else self.width() / 2
        old = self.current_fpp()
        anchor = self.start + anchor_x * old
        fpp = min(max(MIN_FPP, old / factor), self.fit_fpp())
        self.fpp = 0.0 if fpp >= self.fit_fpp() else fpp
        self.start = 0.0
        self.set_start(anchor - anchor_x * self.current_fpp())
        self.viewChanged.emit()
        self.update()

    def fit(self) -> None:
        self.fpp = 0.0
        self.start = 0.0
        self.viewChanged.emit()
        self.update()

    def x_of(self, seconds: float) -> float:
        if not self.audio:
            return 0.0
        return (seconds * self.audio.rate - self.start) / self.current_fpp()

    def seconds_at(self, x: float) -> float:
        if not self.audio:
            return 0.0
        frame = self.start + x * self.current_fpp()
        return min(max(0.0, frame), self.audio.length) / self.audio.rate

    def set_position(self, seconds: float, playing: bool = False) -> None:
        old = self.x_of(self.position)
        self.position = seconds
        x = self.x_of(seconds)
        if playing and self.follow and self.fpp and not self._dragging and not (0 <= x < self.width() - 2):
            # When the position leaves the view while playing, the view turns to the next page.
            self.set_start(seconds * self.audio.rate - self.width() * 0.05 * self.current_fpp())
            return
        if int(old) != int(x):
            self.update()

    def set_bookmarks(self, bookmarks: list[Bookmark]) -> None:
        self.bookmarks = list(bookmarks)
        self.update()

    def bookmark_at(self, x: float) -> int | None:
        best, where = GRAB + 1, None
        for i, mark in enumerate(self.bookmarks):
            distance = abs(self.x_of(mark.time) - x)
            if distance < best:
                best, where = distance, i
        return where

    # --- el dibujo

    def _colors(self) -> dict[str, QColor]:
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Base)
        dark = base.lightness() < 128
        accent = palette.color(QPalette.ColorRole.Highlight)
        wave = QColor(accent)
        played = QColor(accent).lighter(150) if dark else QColor(accent).darker(160)
        return {
            "base": base,
            "ruler": palette.color(QPalette.ColorRole.Window),
            "text": palette.color(QPalette.ColorRole.Text),
            "faint": palette.color(QPalette.ColorRole.PlaceholderText),
            "wave": wave,
            "played": played,
            "cursor": QColor("#ff5a3c") if dark else QColor("#d62d0f"),
            "mark": QColor("#f2b134") if dark else QColor("#b8730a"),
            "select": QColor("#4cc38a") if dark else QColor("#1f8a5b"),
        }

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        colors = self._colors()
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), colors["base"])
        painter.fillRect(QRectF(0, 0, w, RULER), colors["ruler"])
        if not self.audio:
            self._paint_start(painter, colors, w, h)
            painter.end()
            return
        top = RULER + FLAG
        self._paint_ruler(painter, colors, w)
        self._paint_wave(painter, colors, w, top, h - top)
        self._paint_selection(painter, colors, h)  # (encima de la onda, transparente: la tiñe)
        self._paint_first_beat(painter, colors, h)
        self._paint_pause_mark(painter, colors, h)
        self._paint_marks(painter, colors, h)
        self._paint_loops(painter, colors, w, h)
        x = self.x_of(self.position)
        painter.setPen(QPen(colors["cursor"], 2))
        painter.drawLine(QPointF(x, RULER), QPointF(x, h))
        if self.flash and self.count is None:
            self._paint_flash(painter, colors, w, h)
        if self.count is not None:
            # El pulso de la cuenta previa, grande, en el centro.
            font = painter.font()
            font.setPixelSize(max(24, int((h - RULER) * 0.45)))
            font.setBold(True)
            painter.setFont(font)
            shade = QColor(colors["cursor"])
            shade.setAlpha(170)
            painter.setPen(shade)
            painter.drawText(QRectF(0, RULER, w, h - RULER), Qt.AlignmentFlag.AlignCenter, str(self.count))
        painter.end()

    def set_pause_mark(self, seconds: float | None) -> None:
        if seconds != self.pause_mark:
            self.pause_mark = seconds
            self.update()

    def _paint_pause_mark(self, painter: QPainter, colors, h: int) -> None:
        # Donde fue la última pausa (para seguir desde allí): una línea de puntos del color de la posición, y el
        # signo de pausa, dos barritas, abajo (arriba están la regla y los nombres de los marcadores).
        if self.pause_mark is None:
            return
        x = self.x_of(self.pause_mark)
        color = colors["cursor"]
        painter.setPen(QPen(color, 2, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(x, RULER), QPointF(x, h))
        painter.fillRect(QRectF(x - 9, h - 18, 18, 16), colors["base"])
        for left in (x - 6, x + 2):
            painter.fillRect(QRectF(left, h - 16, 4, 12), color)

    def set_first_beat(self, seconds: float | None) -> None:
        if seconds != self.first_beat:
            self.first_beat = seconds
            self.update()

    def _paint_first_beat(self, painter: QPainter, colors, h: int) -> None:
        # El pulso en que entra la grabación tras la cuenta (sin sonar): una línea de trazos y un «1» en la regla.
        if self.first_beat is None:
            return
        x = self.x_of(self.first_beat)
        color = colors["select"]
        painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, RULER), QPointF(x, h))
        box = QRectF(x - 8, RULER - 16, 16, 15)
        painter.fillRect(box, color)
        painter.setPen(colors["base"])
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "1")

    # --- la pantalla de inicio, sin archivo

    ROW = 46  # alto de cada grabación reciente

    def set_recent(self, recent) -> None:
        """The recordings opened last, as (path, its waveform in heights from 0 to 1, or None), for the start
        screen."""
        self.recent = list(recent)
        self._hover_row = None
        self.update()

    def _rows(self) -> tuple[float, float, int]:
        # (izquierda, arriba, cuántas filas caben) de la lista de las recientes, centrada.
        width = min(560, self.width() - 40)
        left = (self.width() - width) / 2
        top = RULER + 70
        fits = max(0, int((self.height() - top - 10) // self.ROW))
        return left, top, min(fits, len(self.recent))

    def recent_at(self, x: float, y: float) -> int | None:
        """The row of the start screen at X, Y."""
        if self.audio or not self.recent:
            return None
        left, top, count = self._rows()
        row = int((y - top) // self.ROW)
        width = min(560, self.width() - 40)
        return row if 0 <= row < count and left <= x <= left + width and y >= top else None

    def _paint_start(self, painter: QPainter, colors, w: int, h: int) -> None:
        painter.setPen(colors["faint"])
        hint = tr("Open an audio file (Ctrl+O), or drop one here")
        if not self.recent:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, hint)
            return
        painter.drawText(QRectF(0, RULER + 14, w, 24), Qt.AlignmentFlag.AlignCenter, hint)
        left, top, count = self._rows()
        width = min(560, w - 40)
        font = painter.font()
        bold = QFont(font)
        bold.setBold(True)
        painter.setPen(colors["text"])
        painter.drawText(QRectF(left, top - 26, width, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         tr("Recent recordings"))
        for row, (path, thumb) in enumerate(self.recent[:count]):
            y = top + row * self.ROW
            box = QRectF(left, y + 2, width, self.ROW - 4)
            there = Path(path).is_file()
            if row == self._hover_row and there:
                shade = QColor(colors["wave"])
                shade.setAlpha(40)
                painter.fillRect(box, shade)
            # La onda, pequeña, a la izquierda; el nombre y la carpeta, al lado.
            wave_box = QRectF(box.left() + 6, box.top() + 6, 120, box.height() - 12)
            ink = QColor(colors["wave"] if there else colors["faint"])
            painter.setPen(QPen(ink, 1))
            if thumb is not None and len(thumb):
                middle = wave_box.center().y()
                half = wave_box.height() / 2
                step = wave_box.width() / len(thumb)
                for i, height in enumerate(thumb):
                    x = wave_box.left() + i * step
                    painter.drawLine(QPointF(x, middle - height * half), QPointF(x, middle + height * half + 0.5))
            else:
                painter.drawLine(QPointF(wave_box.left(), wave_box.center().y()),
                                 QPointF(wave_box.right(), wave_box.center().y()))
            text_box = QRectF(wave_box.right() + 12, box.top() + 3, box.right() - wave_box.right() - 16, 20)
            painter.setFont(bold)
            painter.setPen(colors["text"] if there else colors["faint"])
            metrics = QFontMetrics(bold)
            painter.drawText(text_box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(Path(path).name, Qt.TextElideMode.ElideRight, int(text_box.width())))
            painter.setFont(font)
            painter.setPen(colors["faint"])
            folder = str(Path(path).parent) if there else tr("{folder} (not found)", folder=str(Path(path).parent))
            painter.drawText(text_box.translated(0, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             QFontMetrics(font).elidedText(folder, Qt.TextElideMode.ElideMiddle,
                                                           int(text_box.width())))

    def set_loops(self, loops) -> None:
        self.loops = list(loops)
        self.update()

    def loop_at(self, x: float, y: float) -> int | None:
        """The saved loop whose band (at the foot of the waveform) is at X, Y: the last drawn, if they overlap."""
        if not self.loops or y < self.height() - LANE:
            return None
        seconds = self.seconds_at(x)
        found = None
        for i, loop in enumerate(self.loops):
            if loop.start <= seconds <= loop.end:
                found = i
        return found

    def _paint_loops(self, painter: QPainter, colors, w: int, h: int) -> None:
        # Cada bucle, una banda de su color al pie, con su nombre; encima de la onda, algo transparente.
        metrics = QFontMetrics(painter.font())
        for i, loop in enumerate(self.loops):
            x0, x1 = self.x_of(loop.start), self.x_of(loop.end)
            if x1 < 0 or x0 > w:
                continue
            color = QColor(LOOP_COLORS[i % len(LOOP_COLORS)])
            band = QRectF(x0, h - LANE, max(2.0, x1 - x0), LANE - 1)
            fill = QColor(color)
            fill.setAlpha(170)
            painter.fillRect(band, fill)
            painter.setPen(QPen(color, 1))
            painter.drawLine(QPointF(x0, h - LANE), QPointF(x0, h))
            label = loop.label or f"{clock(loop.start, tenths=True)} – {clock(loop.end, tenths=True)}"
            room = band.width() - 8
            if room > 12:
                painter.setPen(QColor("#000000"))
                painter.drawText(band.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter,
                                 metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(room)))

    def show_value(self, text: str) -> None:
        """Show TEXT large in the middle of the waveform for a moment (about a second), fading at the end: the
        value just changed from the keyboard."""
        self.flash = text
        self._flash_alpha = 255
        self._flash_timer.start(900)
        self.update()

    def _flash_step(self) -> None:
        # Se apaga en unos 200 ms, de 40 en 40.
        self._flash_alpha -= 50
        if self._flash_alpha <= 0:
            self.flash = None
        else:
            self._flash_timer.start(40)
        self.update()

    def _paint_flash(self, painter: QPainter, colors, w: int, h: int) -> None:
        font = painter.font()
        font.setPixelSize(max(20, int((h - RULER) * 0.22)))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        box = QRectF(0, 0, metrics.horizontalAdvance(self.flash) + 36, metrics.height() + 14)
        box.moveCenter(QPointF(w / 2, RULER + (h - RULER) / 2))
        # Un recuadro del color de fondo, algo transparente, para que se lea sobre la onda.
        back = QColor(colors["base"])
        back.setAlpha(int(self._flash_alpha * 0.8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(back)
        painter.drawRoundedRect(box, 8, 8)
        ink = QColor(colors["text"])
        ink.setAlpha(self._flash_alpha)
        painter.setPen(ink)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self.flash)

    def set_count(self, beat: int | None) -> None:
        if beat != self.count:
            self.count = beat
            self.update()

    def set_selection(self, selection: tuple[float, float] | None, repeating: bool | None = None) -> None:
        self.selection = selection
        if repeating is not None:
            self.repeating = repeating
        self.update()

    def _paint_selection(self, painter: QPainter, colors, h: int) -> None:
        if not self.selection:
            return
        x0, x1 = (self.x_of(t) for t in self.selection)
        band = QColor(colors["select"])
        band.setAlpha(90 if self.repeating else 45)
        painter.fillRect(QRectF(x0, RULER, x1 - x0, h - RULER), band)
        edge = QColor(colors["select"])
        painter.setPen(QPen(edge, 2 if self.repeating else 1))
        for x in (x0, x1):
            painter.drawLine(QPointF(x, RULER), QPointF(x, h))
        painter.fillRect(QRectF(x0, 0, x1 - x0, 4), edge)  # (también en la regla)

    def _paint_ruler(self, painter: QPainter, colors, w: int) -> None:
        rate = self.audio.rate
        seconds_per_px = self.current_fpp() / rate
        step = next((s for s in STEPS if s / seconds_per_px >= 90), STEPS[-1])
        first = math.floor(self.start / rate / step) * step
        painter.setPen(colors["faint"])
        painter.drawLine(0, RULER - 1, w, RULER - 1)
        metrics = QFontMetrics(painter.font())
        t = first
        end = (self.start + w * self.current_fpp()) / rate
        while t <= end + step:
            x = self.x_of(t)
            painter.setPen(colors["faint"])
            painter.drawLine(QPointF(x, RULER - 6), QPointF(x, RULER - 1))
            for k in range(1, 5):  # marcas menores
                xm = self.x_of(t + k * step / 5)
                painter.drawLine(QPointF(xm, RULER - 3), QPointF(xm, RULER - 1))
            painter.setPen(colors["text"])
            label = clock(t, tenths=step < 1) if step >= 0.1 else f"{t:.2f}"
            painter.drawText(QPointF(x + 3, metrics.ascent() + 2), label)
            t += step

    def _paint_wave(self, painter: QPainter, colors, w: int, top: int, height: int) -> None:
        audio = self.audio
        fpp = self.current_fpp()
        mid = top + height / 2
        painter.setPen(colors["faint"])
        painter.drawLine(QPointF(0, mid), QPointF(w, mid))
        # La onda se dibuja una vez, con NumPy, en dos imágenes (la parte tocada y la otra), y en cada
        # movimiento de la posición solo se copian: rellenar con Qt un polígono de miles de picos tardaba
        # más de 100 ms, con el GIL tomado, y el sonido se cortaba cada vez que la línea avanzaba un píxel.
        # Lo leído cuenta solo por la columna donde termina dentro de la vista y por el mayor pico (la escala):
        # mientras se lee, mover la posición en una parte ya leída no rehace las imágenes.
        key = (self.start, fpp, w, height, self._read_column(w), self._loudest_peak(), audio.done,
               colors["wave"].rgba(), colors["played"].rgba())
        if key != self._cache_key:
            self._cache = self._wave_images(colors, w, height)
            self._cache_key = key
        if self._cache is not None:
            played, rest = self._cache
            cursor = min(max(0, round(self.x_of(self.position))), w)
            if cursor > 0:
                painter.drawImage(QPointF(0, top), played, QRectF(0, 0, cursor, height))
            if cursor < w:
                painter.drawImage(QPointF(cursor, top), rest, QRectF(cursor, 0, w - cursor, height))
        if not audio.done:
            # What is still to be read: a faint band.
            x = (audio.decoded - self.start) / fpp
            if x < w:
                shade = QColor(colors["faint"])
                shade.setAlpha(40)
                painter.fillRect(QRectF(max(0, x), top, w - max(0, x), height), shade)

    def _wave_images(self, colors, w: int, height: int):
        """(played, not yet played): the waveform drawn in each colour, as images of W × HEIGHT."""
        audio = self.audio
        lo, hi = columns(audio, self.start, self.current_fpp(), w)
        ok = ~np.isnan(lo)
        if height < 4 or not ok.any():
            return None
        # A escala del pico del archivo (lo leído hasta ahora): una grabación baja no se ve plana.
        loudest = max(self._loudest_peak(), 0.05)
        mid = height / 2
        half = (height / 2 - 2) / min(1.0, loudest)
        limit = height / 2 - 2
        y_hi = np.where(ok, mid - np.clip(np.nan_to_num(hi) * half, -limit, limit), height)
        y_lo = np.where(ok, mid - np.clip(np.nan_to_num(lo) * half, -limit, limit), -1)
        # Una columna muy baja se ve al menos como una línea de un píxel.
        y_lo = np.maximum(y_lo, y_hi + 1)
        # Un solo mapa de bytes (1 donde hay onda) con dos tablas de dos colores: Qt (en C++) hace cada imagen
        # en color. Pintar con NumPy las dos imágenes de 32 bits tardaba el doble.
        rows = np.arange(height, dtype=np.int16)[:, None]
        top = np.floor(y_hi).astype(np.int16)[None, :]
        bottom = np.ceil(y_lo).astype(np.int16)[None, :]
        mask = np.ascontiguousarray(((rows >= top) & (rows <= bottom)).view(np.uint8))
        indexed = QImage(mask.data, w, height, w, QImage.Format.Format_Indexed8)
        images = []
        for color in (colors["played"], colors["wave"]):
            indexed.setColorTable([0, color.rgba() | 0xFF000000])
            # (convertToFormat hace una imagen nueva, de Qt: el arreglo de NumPy puede irse)
            images.append(indexed.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        return images[0], images[1]


    def _paint_marks(self, painter: QPainter, colors, h: int) -> None:
        metrics = QFontMetrics(painter.font())
        for i, mark in enumerate(self.bookmarks):
            x = self.x_of(mark.time)
            if x < -200 or x > self.width() + 2:
                continue
            # El primer pulso, del color de la selección y con línea entera; los otros, del de los marcadores.
            color = colors["select"] if mark.first_beat else colors["mark"]
            style = Qt.PenStyle.SolidLine if mark.first_beat else Qt.PenStyle.DashLine
            painter.setPen(QPen(color, 1, style))
            painter.drawLine(QPointF(x, RULER), QPointF(x, h))
            if mark.first_beat:
                label = f"1 · {mark.label}" if mark.label else "1"
            else:
                label = mark.label or str(i + 1)
            text_w = min(metrics.horizontalAdvance(label) + 8, 220)
            box = QRectF(x, RULER + 1, text_w, FLAG - 2)
            painter.fillRect(box, color)
            painter.setPen(colors["base"])
            painter.drawText(box.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(label, Qt.TextElideMode.ElideRight, text_w - 6))

    # --- el ratón

    def mousePressEvent(self, event) -> None:
        if not self.audio:
            row = self.recent_at(event.position().x(), event.position().y())
            if event.button() == Qt.MouseButton.LeftButton and row is not None:
                path = self.recent[row][0]
                if Path(path).is_file():
                    self.recentRequested.emit(path)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Mayús+arrastrar: una selección (la que se puede repetir).
            self._selecting = self.seconds_at(x)
            return
        mark = self.bookmark_at(x) if event.position().y() < RULER + FLAG else None
        if mark is not None:
            self.seekRequested.emit(self.bookmarks[mark].time)
            return
        loop = self.loop_at(x, event.position().y())
        if loop is not None:
            self.loopClicked.emit(loop)  # (lo elige, lo repite y va a su comienzo)
            return
        self._dragging = True
        self.seekRequested.emit(self.seconds_at(x))

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        if not self.audio:
            # La pantalla de inicio: la fila bajo el puntero, sombreada, y el puntero, una mano.
            row = self.recent_at(x, event.position().y())
            if row != self._hover_row:
                self._hover_row = row
                self.setCursor(Qt.CursorShape.PointingHandCursor if row is not None else Qt.CursorShape.ArrowCursor)
                self.update()
            return
        if self._selecting is not None:
            here = self.seconds_at(x)
            self.set_selection((min(self._selecting, here), max(self._selecting, here)))
            return
        if self._dragging:
            self.seekRequested.emit(self.seconds_at(x))
            return
        if self.audio:
            mark = self.bookmark_at(x)
            tip = clock(self.seconds_at(x), tenths=True)
            if mark is not None:
                b = self.bookmarks[mark]
                tip = f"{clock(b.time, tenths=True)}  {b.label}".rstrip()
            loop = self.loop_at(x, event.position().y())
            if loop is not None:
                one = self.loops[loop]
                tip = (f"{one.label}  " if one.label else "") + tr(
                    "{start} – {end}: a click repeats it", start=clock(one.start, tenths=True),
                    end=clock(one.end, tenths=True))
            self.setToolTip(tip)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        if self._selecting is not None:
            here = self.seconds_at(event.position().x())
            start, end = sorted((self._selecting, here))
            self._selecting = None
            # (un clic con Mayús, sin arrastrar, quita la selección)
            self.selectionChanged.emit((start, end) if end - start > 0.05 else None)

    def mouseDoubleClickEvent(self, event) -> None:
        mark = self.bookmark_at(event.position().x())
        if mark is not None:
            self.renameBookmarkRequested.emit(mark)

    def contextMenuEvent(self, event) -> None:
        if not self.audio:
            return
        x = event.pos().x()
        menu = QMenu(self)
        here = self.seconds_at(x)
        menu.addAction(tr("Add a bookmark here"), lambda: self.addBookmarkRequested.emit(here))
        mark = self.bookmark_at(x)
        if mark is not None:
            menu.addAction(tr("Rename the bookmark…"), lambda: self.renameBookmarkRequested.emit(mark))
            menu.addAction(tr("Remove the bookmark"), lambda: self.removeBookmarkRequested.emit(mark))
        later = [b.time for b in self.bookmarks if b.time > here + 0.05]
        if later:
            menu.addAction(tr("Select from here to the next bookmark"),
                           lambda: self.selectionChanged.emit((here, later[0])))
        if self.selection:
            menu.addAction(tr("Clear the selection"), lambda: self.selectionChanged.emit(None))
        menu.addSeparator()
        menu.addAction(tr("Count-in: the first beat is here"), lambda: self.firstBeatRequested.emit(here))
        menu.exec(event.globalPos())

    def wheelEvent(self, event) -> None:
        if not self.audio:
            return
        delta = event.angleDelta()
        steps = (delta.y() or delta.x()) / 120
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.25 ** steps, event.position().x())
        else:
            # La rueda corre la vista un octavo de su ancho por paso.
            self.set_start(self.start - steps * self.visible_frames() / 8)
        event.accept()

    def resizeEvent(self, event) -> None:
        if self.fpp and self.fpp >= self.fit_fpp():
            self.fpp = 0.0
        self.set_start(self.start)
        self.viewChanged.emit()
        super().resizeEvent(event)


class Overview(QWidget):
    """The whole file, in a thin strip above the waveform while it is zoomed in: the part in view shaded, the
    position a line; a click or a drag there moves the view (not the position) to that point."""

    HEIGHT = 30

    def __init__(self, wave: Waveform, parent=None):
        super().__init__(parent)
        self.wave = wave
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("The whole file: a click or a drag shows that part"))
        self._key = None
        self._image: QImage | None = None

    def _shape(self, colors) -> QImage | None:
        # La onda entera, dibujada una vez por tamaño y lectura (como la de la forma de onda, en una imagen).
        audio = self.wave.audio
        w, h = self.width(), self.height()
        key = (w, h, audio.decoded, audio.peaks.count, colors["wave"].rgba())
        if key == self._key:
            return self._image
        self._key = key
        length = max(1, audio.length)
        lo, hi = columns(audio, 0.0, length / max(1, w), w)
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setPen(colors["wave"])
        loudest = max(float(np.nanmax(np.abs(np.concatenate([lo, hi])))) if np.isfinite(lo).any() else 0.0, 0.05)
        middle = h / 2
        for x in range(w):
            if np.isnan(lo[x]):
                continue
            top = middle - hi[x] / loudest * (middle - 2)
            bottom = middle - lo[x] / loudest * (middle - 2)
            painter.drawLine(QPointF(x, top), QPointF(x, max(bottom, top + 1)))
        painter.end()
        self._image = image
        return image

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        colors = self.wave._colors()
        painter.fillRect(self.rect(), colors["ruler"])
        audio = self.wave.audio
        if audio is None:
            painter.end()
            return
        image = self._shape(colors)
        if image is not None:
            painter.drawImage(0, 0, image)
        length = max(1, audio.length)
        scale = self.width() / length
        x0 = self.wave.start * scale
        x1 = (self.wave.start + self.wave.visible_frames()) * scale
        shade = QColor(colors["select"])
        shade.setAlpha(60)
        painter.fillRect(QRectF(x0, 0, max(2.0, x1 - x0), self.height()), shade)
        painter.setPen(QPen(colors["select"], 1))
        painter.drawRect(QRectF(x0, 0.5, max(2.0, x1 - x0), self.height() - 1))
        x = self.wave.position * audio.rate * scale
        painter.setPen(QPen(colors["cursor"], 2))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.setPen(colors["faint"])
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.end()

    def _show_at(self, x: float) -> None:
        audio = self.wave.audio
        if audio is None:
            return
        frame = x / max(1, self.width()) * audio.length
        self.wave.set_start(frame - self.wave.visible_frames() / 2)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_at(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._show_at(event.position().x())


class WaveformView(QWidget):
    """The waveform with a scroll bar under it, and, while it is zoomed in, the whole file in a strip above it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wave = Waveform(self)
        self.overview = Overview(self.wave, self)
        self.overview.hide()
        self.bar = QScrollBar(Qt.Orientation.Horizontal, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.overview)
        layout.addWidget(self.wave)
        layout.addWidget(self.bar)
        self._sync = False
        self.wave.viewChanged.connect(self._update_bar)
        self.bar.valueChanged.connect(self._scrolled)
        self._update_bar()

    def _update_bar(self) -> None:
        # La barra cuenta en píxeles de la vista actual.
        wave = self.wave
        fpp = wave.current_fpp()
        self._sync = True
        total = int(wave.max_start() / fpp) if wave.audio else 0
        self.bar.setRange(0, total)
        self.bar.setPageStep(max(1, wave.width()))
        self.bar.setSingleStep(max(1, wave.width() // 10))
        self.bar.setValue(int(wave.start / fpp))
        self.bar.setVisible(total > 0)
        # (la franja del archivo entero, solo mientras se ve una parte)
        self.overview.setVisible(bool(wave.audio) and bool(wave.fpp))
        self.overview.update()
        self._sync = False

    def _scrolled(self, value: int) -> None:
        if not self._sync:
            self.wave.set_start(value * self.wave.current_fpp())
