"""El diálogo de Archivo > Exportar el audio, y la exportación con su barra de progreso.

ExportDialog elige qué se guarda (el archivo entero o la selección), en qué
formato, y si con la manera de oír; muestra a qué velocidad y altura. run_export
lo guarda en un hilo aparte (la reproducción sigue) con un diálogo de progreso
que lo puede cancelar.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from . import export
from .countin import number
from .export import FORMATS, Settings
from .interface import tr
from .timefmt import clock

FORMAT_NAMES = {"wav": "WAV", "flac": "FLAC", "mp3": "MP3", "opus": "Opus"}


def describe(speed: float, pitch: float, formants: bool) -> str:
    """How the export will sound, in words."""
    what = tr("At {speed}×", speed=number(speed))
    if pitch:
        what += ", " + (tr("{n} semitones higher", n=number(pitch)) if pitch > 0
                        else tr("{n} semitones lower", n=number(-pitch)))
        if formants:
            what += " " + tr("(formants kept)")
    else:
        what += ", " + tr("at the pitch of the recording")
    return what + "."


class ExportDialog(QDialog):
    def __init__(self, parent, selection: tuple[float, float] | None, speed: float, pitch: float,
                 formants: bool, hearing_text: str | None, format_: str):
        super().__init__(parent)
        self.setWindowTitle(tr("Export the audio"))
        self.whole = QRadioButton(tr("The &whole file"), self)
        self.part = QRadioButton(self)
        if selection:
            self.part.setText(tr("The &selection ({start} – {end})", start=clock(selection[0], tenths=True),
                                 end=clock(selection[1], tenths=True)))
        else:
            self.part.setText(tr("The &selection (there is none)"))
            self.part.setEnabled(False)
        group = QButtonGroup(self)
        group.addButton(self.whole)
        group.addButton(self.part)
        (self.part if selection else self.whole).setChecked(True)
        self.format = QComboBox(self)
        for key in export.available():
            self.format.addItem(FORMAT_NAMES[key], key)
        index = self.format.findData(format_)
        self.format.setCurrentIndex(max(0, index))
        self.hearing = QCheckBox(self)
        if hearing_text:
            self.hearing.setText(tr("As it is heard ({what})", what=hearing_text))
            self.hearing.setChecked(True)
        else:
            self.hearing.setText(tr("As it is heard (Hear: everything)"))
            self.hearing.setEnabled(False)

        what = QWidget(self)
        rows = QVBoxLayout(what)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.addWidget(self.whole)
        rows.addWidget(self.part)
        form = QFormLayout()
        form.addRow(tr("Export:"), what)
        form.addRow(tr("&Format:"), self.format)
        form.addRow("", self.hearing)
        self.sound = QLabel(describe(speed, pitch, formants), self)
        self.sound.setWordWrap(True)
        form.addRow(tr("Sound:"), self.sound)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("&Export…"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def chosen_format(self) -> str:
        return self.format.currentData()


def suggested_name(path: Path, speed: float, pitch: float, format_: str) -> str:
    """The name offered for the file: the recording's, with its speed and pitch."""
    parts = [f"{number(speed)}×"] if speed != 1.0 else []
    if pitch:
        parts.append(("+" if pitch > 0 else "−") + tr("{n} st", n=number(abs(pitch))))
    tail = f" ({', '.join(parts)})" if parts else tr(" (export)")
    return f"{path.stem}{tail}{FORMATS[format_][0]}"


def run_export(parent, audio, path: Path, format_: str, settings: Settings) -> bool | None:
    """Export with a progress dialog: True when done, False if cancelled, None after an error (it is shown)."""
    cancel = threading.Event()
    state = {"share": 0.0, "done": None, "error": None}

    def work():
        try:
            state["done"] = export.export(audio, path, format_, settings, cancel,
                                          lambda share: state.__setitem__("share", share))
        except Exception as error:  # noqa: BLE001 (se muestra)
            state["error"] = error
            state["done"] = False

    progress = QProgressDialog(tr("Exporting {name}…", name=path.name), tr("Cancel"), 0, 1000, parent)
    progress.setWindowTitle(tr("Export the audio"))
    progress.setMinimumDuration(300)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    thread = threading.Thread(target=work, name="export", daemon=True)
    timer = QTimer(progress)

    def poll():
        progress.setValue(int(state["share"] * 1000))
        if state["done"] is not None:
            timer.stop()
            progress.close()

    timer.timeout.connect(poll)
    progress.canceled.connect(cancel.set)
    thread.start()
    timer.start(50)
    progress.exec()
    if state["done"] is None:
        cancel.set()  # (se cerró el diálogo sin terminar: Cancelar)
    thread.join()
    if state["error"] is not None:
        QMessageBox.warning(parent, tr("Export the audio"),
                            tr("Cannot export {name}:\n{error}", name=path.name, error=state["error"]))
        return None
    return bool(state["done"])
