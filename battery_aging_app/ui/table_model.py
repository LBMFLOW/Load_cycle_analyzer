from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor


class DataFrameTableModel(QAbstractTableModel):
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._frame = frame if frame is not None else pd.DataFrame()
        self._units: dict[str, str] = {}
        self._highlighted_rows: set[int] = set()
        self._cursor_row: int | None = None

    def set_frame(self, frame: pd.DataFrame, units: dict[str, str] | None = None) -> None:
        self.beginResetModel()
        self._frame = frame
        self._units = units or {}
        self._highlighted_rows.clear()
        self._cursor_row = None
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._frame.iat[row, column]
            if pd.isna(value):
                return ""
            if isinstance(value, (float, np.floating)):
                return f"{float(value):.8g}"
            return str(value)
        if role == Qt.ItemDataRole.BackgroundRole:
            if row == self._cursor_row:
                return QColor("#ffe8a3")
            if row in self._highlighted_rows:
                return QColor("#dcecff")
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            name = str(self._frame.columns[section])
            unit = self._units.get(name, "")
            return f"{name}\n[{unit}]" if unit else name
        return str(section + 1)

    def set_cursor_row(self, row: int | None) -> None:
        old = self._cursor_row
        self._cursor_row = row
        for item in (old, row):
            if item is not None and 0 <= item < len(self._frame):
                self.dataChanged.emit(
                    self.index(item, 0),
                    self.index(item, max(0, self.columnCount() - 1)),
                    [Qt.ItemDataRole.BackgroundRole],
                )

    def set_highlighted_rows(self, rows: Iterable[int]) -> None:
        previous = self._highlighted_rows
        self._highlighted_rows = {int(row) for row in rows}
        affected = previous | self._highlighted_rows
        if not affected or self.columnCount() == 0:
            return
        for row in affected:
            if 0 <= row < len(self._frame):
                self.dataChanged.emit(
                    self.index(row, 0),
                    self.index(row, self.columnCount() - 1),
                    [Qt.ItemDataRole.BackgroundRole],
                )
