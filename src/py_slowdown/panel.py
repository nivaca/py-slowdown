"""Los paneles de los marcadores y de los bucles: listas de tiempos y nombres.

En los marcadores, un doble clic en el tiempo lleva allí la posición; el nombre
se edita en la misma lista. Los botones añaden un marcador en la posición actual,
quitan el elegido o copian la lista como texto. Los bucles son selecciones
guardadas con un nombre: un doble clic en sus tiempos la vuelve a elegir y la
repite.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .bookmarks import Bookmark, Loop
from .interface import tr
from .timefmt import clock


class BookmarkPanel(QWidget):
    activated = Signal(int)  # a row whose time is double-clicked
    addRequested = Signal()
    removeRequested = Signal(int)
    renamed = Signal(int, str)
    exportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels([tr("Time"), tr("Label")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.itemChanged.connect(self._changed)
        self.table.currentCellChanged.connect(lambda *_: self._update_buttons())

        self.add_button = QPushButton(tr("Add"), self)
        self.add_button.setToolTip(tr("Add a bookmark at the current position (B)"))
        self.remove_button = QPushButton(tr("Remove"), self)
        self.export_button = QPushButton(tr("Export…"), self)
        self.export_button.setToolTip(tr("Save the bookmarks as a text file"))
        for button in (self.add_button, self.remove_button, self.export_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_button.clicked.connect(self.addRequested)
        self.remove_button.clicked.connect(self._remove)
        self.export_button.clicked.connect(self.exportRequested)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        buttons.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self._filling = False
        self._update_buttons()

    def show_bookmarks(self, bookmarks: list[Bookmark], select: int | None = None) -> None:
        self._filling = True
        self.table.setRowCount(len(bookmarks))
        for row, mark in enumerate(bookmarks):
            when = QTableWidgetItem(clock(mark.time, tenths=True))
            when.setFlags(when.flags() & ~Qt.ItemFlag.ItemIsEditable)
            when.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            when.setToolTip(tr("Double-click to go there"))
            self.table.setItem(row, 0, when)
            self.table.setItem(row, 1, QTableWidgetItem(mark.label))
        self._filling = False
        if select is not None and 0 <= select < len(bookmarks):
            self.table.selectRow(select)
        self._update_buttons()

    def edit_label(self, row: int) -> None:
        item = self.table.item(row, 1)
        if item is not None:
            self.table.setCurrentItem(item)
            self.table.editItem(item)

    def _double_clicked(self, row: int, column: int) -> None:
        if column == 0:
            self.activated.emit(row)

    def _changed(self, item: QTableWidgetItem) -> None:
        if not self._filling and item.column() == 1:
            self.renamed.emit(item.row(), item.text().strip())

    def _remove(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.removeRequested.emit(row)

    def _update_buttons(self) -> None:
        rows = self.table.rowCount()
        self.remove_button.setEnabled(self.table.currentRow() >= 0 and rows > 0)
        self.export_button.setEnabled(rows > 0)


class LoopPanel(QWidget):
    activated = Signal(int)  # a row whose start or end is double-clicked
    saveRequested = Signal()
    removeRequested = Signal(int)
    renamed = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels([tr("Start"), tr("End"), tr("Label")])
        self.table.verticalHeader().setVisible(False)
        for column in (0, 1):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.itemChanged.connect(self._changed)
        self.table.currentCellChanged.connect(lambda *_: self._update_buttons())

        self.save_button = QPushButton(tr("Save the selection"), self)
        self.save_button.setToolTip(tr("Keep the selection as a loop, with a name (Shift+L)"))
        self.remove_button = QPushButton(tr("Remove"), self)
        for button in (self.save_button, self.remove_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.save_button.clicked.connect(self.saveRequested)
        self.remove_button.clicked.connect(self._remove)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self._filling = False
        self._update_buttons()

    def show_loops(self, loops: list[Loop], select: int | None = None) -> None:
        self._filling = True
        self.table.setRowCount(len(loops))
        for row, loop in enumerate(loops):
            for column, seconds in ((0, loop.start), (1, loop.end)):
                when = QTableWidgetItem(clock(seconds, tenths=True))
                when.setFlags(when.flags() & ~Qt.ItemFlag.ItemIsEditable)
                when.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                when.setToolTip(tr("Double-click to repeat it"))
                self.table.setItem(row, column, when)
            self.table.setItem(row, 2, QTableWidgetItem(loop.label))
        self._filling = False
        if select is not None and 0 <= select < len(loops):
            self.table.selectRow(select)
        self._update_buttons()

    def edit_label(self, row: int) -> None:
        item = self.table.item(row, 2)
        if item is not None:
            self.table.setCurrentItem(item)
            self.table.editItem(item)

    def _double_clicked(self, row: int, column: int) -> None:
        if column in (0, 1):
            self.activated.emit(row)

    def _changed(self, item: QTableWidgetItem) -> None:
        if not self._filling and item.column() == 2:
            self.renamed.emit(item.row(), item.text().strip())

    def _remove(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.removeRequested.emit(row)

    def _update_buttons(self) -> None:
        self.remove_button.setEnabled(self.table.currentRow() >= 0 and self.table.rowCount() > 0)
