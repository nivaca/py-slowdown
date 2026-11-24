"""La cuenta previa: unos golpes a un tempo antes de que empiece a sonar la grabación.

CountIn guarda lo que el usuario eligió (si se cuenta, cuántos golpes, a qué
tempo, y si el tempo sigue la velocidad) en la configuración, y dice cuántos
golpes y a qué tempo hay que dar ahora. CountInDialog es el diálogo donde se
eligen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from .engine import MAX_BEATS, MAX_BPM, MIN_BPM
from .interface import tr


@dataclass
class CountIn:
    on: bool = False
    beats: int = 4
    bpm: int = 100
    follow: bool = True  # el tempo sigue la velocidad: 120 BPM a 0,5× se cuentan a 60

    @classmethod
    def load(cls, settings: QSettings) -> CountIn:
        def number(key, default, low, high):
            try:
                return min(high, max(low, int(settings.value(key, default))))
            except (TypeError, ValueError):
                return default

        return cls(on=settings.value("countin/on", False, type=bool),
                   beats=number("countin/beats", 4, 1, MAX_BEATS),
                   bpm=number("countin/bpm", 100, MIN_BPM, MAX_BPM),
                   follow=settings.value("countin/follow", True, type=bool))

    def save(self, settings: QSettings) -> None:
        settings.setValue("countin/on", self.on)
        settings.setValue("countin/beats", self.beats)
        settings.setValue("countin/bpm", self.bpm)
        settings.setValue("countin/follow", self.follow)

    def tempo(self, speed: float) -> float:
        """The tempo of the clicks at SPEED."""
        return min(MAX_BPM, max(MIN_BPM, self.bpm * speed if self.follow else self.bpm))


class CountInDialog(QDialog):
    """Count in before playing: how many clicks, and at what tempo."""

    def __init__(self, count: CountIn, speed: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Count-in"))
        self.on = QCheckBox(tr("&Count in before playing"), self)
        self.on.setChecked(count.on)
        self.beats = QSpinBox(self)
        self.beats.setRange(1, MAX_BEATS)
        self.beats.setValue(count.beats)
        self.bpm = QSpinBox(self)
        self.bpm.setRange(MIN_BPM, MAX_BPM)
        self.bpm.setSuffix(" BPM")
        self.bpm.setValue(count.bpm)
        self.follow = QCheckBox(tr("&Follow the speed"), self)
        self.follow.setChecked(count.follow)
        self.follow.setToolTip(tr("The tempo of the clicks changes with the speed: 120 BPM at 0.5× are counted at 60"))
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self._speed = speed
        form = QFormLayout()
        form.addRow(tr("Cou&nts:"), self.beats)
        form.addRow(tr("&Tempo:"), self.bpm)
        form.addRow("", self.follow)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.on)
        layout.addLayout(form)
        layout.addWidget(self.note)
        layout.addWidget(buttons)
        for widget in (self.bpm, self.beats):
            widget.valueChanged.connect(self._explain)
        self.follow.toggled.connect(self._explain)
        self.on.toggled.connect(self._explain)
        self._explain()

    def value(self) -> CountIn:
        return CountIn(self.on.isChecked(), self.beats.value(), self.bpm.value(), self.follow.isChecked())

    def _explain(self) -> None:
        # Lo que se oirá a la velocidad de ahora, en palabras.
        count = self.value()
        for widget in (self.beats, self.bpm, self.follow):
            widget.setEnabled(count.on)
        if not count.on:
            self.note.setText(tr("Playing starts at once."))
            return
        self.note.setText(tr("At the speed now ({speed}×): {beats} clicks at {bpm} BPM, then the recording.",
                             speed=number(self._speed), beats=count.beats, bpm=number(count.tempo(self._speed))))


def number(value: float) -> str:
    """VALUE as the language of the interface writes it (0,75 in Spanish), without needless decimals."""
    from PySide6.QtCore import QLocale

    return QLocale().toString(float(round(value, 2)), "g", 6)
