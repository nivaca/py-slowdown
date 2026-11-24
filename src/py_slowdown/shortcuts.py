"""Los atajos de teclado, cambiados a gusto (Configuración > Atajos de teclado).

Cada acción de la ventana tiene un nombre (el de su atributo, a_play...) y sus
teclas de siempre. Las que el usuario cambia se guardan en la configuración,
shortcuts/NOMBRE, como texto portable de Qt; las demás no se guardan, de modo que
una versión nueva puede cambiar las de siempre. Así sirven también los pedales
de pie, que suelen mandar teclas.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .interface import tr

PORTABLE = QKeySequence.SequenceFormat.PortableText
NATIVE = QKeySequence.SequenceFormat.NativeText


def plain(text: str) -> str:
    """The text of a menu entry without its & and its …"""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip("…").strip()


def keys_of(action: QAction) -> list[str]:
    return [k.toString(PORTABLE) for k in action.shortcuts() if not k.isEmpty()]


def load(actions: dict[str, QAction], settings: QSettings) -> None:
    """Give each action the keys the user chose for it, if any."""
    for name, action in actions.items():
        value = settings.value(f"shortcuts/{name}")
        if value is None:
            continue
        keys = [value] if isinstance(value, str) else list(value)
        action.setShortcuts([QKeySequence(k, PORTABLE) for k in keys if k])


def save(actions: dict[str, QAction], defaults: dict[str, list[str]], settings: QSettings) -> None:
    """Keep the keys that are not those of always (and forget those that are again)."""
    for name, action in actions.items():
        keys = keys_of(action)
        if keys == defaults.get(name, []):
            settings.remove(f"shortcuts/{name}")
        else:
            # (una lista vacía se guarda como "": la acción sin atajo)
            settings.setValue(f"shortcuts/{name}", keys if keys else "")


def clashes(chosen: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """(keys, one action, another) for each combination of keys given to two actions."""
    seen: dict[str, str] = {}
    out = []
    for name, keys in chosen.items():
        for key in keys:
            if key in seen and seen[key] != name:
                out.append((key, seen[key], name))
            seen.setdefault(key, name)
    return out


class ShortcutsDialog(QDialog):
    """A table of the actions and their keys: a click on the keys, then the new ones."""

    def __init__(self, actions: dict[str, QAction], defaults: dict[str, list[str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Keyboard shortcuts"))
        self.actions = actions
        self.defaults = defaults
        self.names = list(actions)
        self.table = QTableWidget(len(self.names), 2, self)
        self.table.setHorizontalHeaderLabels([tr("Action"), tr("Keys")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.edits: dict[str, QKeySequenceEdit] = {}
        self.others: dict[str, list[str]] = {}  # las teclas de más (Más lento: ↓ y −), que se quedan si no se cambia
        self._first: dict[str, str] = {}  # la primera tecla de cada acción al abrir el diálogo
        for row, name in enumerate(self.names):
            action = actions[name]
            item = QTableWidgetItem(plain(action.text()))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            self.table.setCellWidget(row, 1, self._edit(name, keys_of(action)))
        reset = QPushButton(tr("&Restore the defaults"), self)
        reset.clicked.connect(self.restore_defaults)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.addButton(reset, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        hint = QLabel(tr("Click the keys of an action and press the new ones; the button inside clears them. A foot "
                         "pedal that sends keys works the same way."), self)
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
        self.resize(560, 620)

    def _edit(self, name: str, keys: list[str]) -> QKeySequenceEdit:
        edit = QKeySequenceEdit(QKeySequence(keys[0], PORTABLE) if keys else QKeySequence(), self)
        if hasattr(edit, "setMaximumSequenceLength"):
            edit.setMaximumSequenceLength(1)  # (una combinación, no una serie de ellas)
        edit.setClearButtonEnabled(True)
        if len(keys) > 1:
            edit.setToolTip(tr("Also: {keys}", keys=", ".join(QKeySequence(k, PORTABLE).toString(NATIVE)
                                                               for k in keys[1:])))
        self.edits[name] = edit
        self.others[name] = keys[1:]
        self._first[name] = keys[0] if keys else ""
        return edit

    def restore_defaults(self) -> None:
        for row, name in enumerate(self.names):
            self.table.setCellWidget(row, 1, self._edit(name, self.defaults.get(name, [])))

    def chosen(self) -> dict[str, list[str]]:
        """{action: its keys}, as the table has them."""
        out = {}
        for name in self.names:
            first = self.edits[name].keySequence().toString(PORTABLE)
            if first == self._first[name]:
                out[name] = ([first] if first else []) + self.others[name]
            else:
                out[name] = [first] if first else []  # (cambiadas: solo las nuevas)
        return out

    def accept(self) -> None:
        chosen = self.chosen()
        found = clashes(chosen)
        if found:
            key, one, other = found[0]
            QMessageBox.warning(self, tr("Keyboard shortcuts"), tr(
                "{keys} is given to two actions: {one} and {other}. Give it to only one.",
                keys=QKeySequence(key, PORTABLE).toString(NATIVE), one=plain(self.actions[one].text()),
                other=plain(self.actions[other].text())))
            return
        for name, keys in chosen.items():
            self.actions[name].setShortcuts([QKeySequence(k, PORTABLE) for k in keys])
        super().accept()
