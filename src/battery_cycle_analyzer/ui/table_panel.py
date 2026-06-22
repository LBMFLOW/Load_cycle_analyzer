from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QMenu, QTableView, QToolButton, QVBoxLayout, QWidget


class DataFrameTableModel(QAbstractTableModel):
    """Qt model over a pandas DataFrame for scalable table display."""

    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._frame = frame if frame is not None else pd.DataFrame()
        self._current_row: int | None = None
        self._highlighted_rows: set[int] = set()

    def set_frame(self, frame: pd.DataFrame) -> None:
        self.beginResetModel()
        self._frame = frame
        self._current_row = None
        self._highlighted_rows.clear()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.BackgroundRole and index.row() == self._current_row:
            return QColor("#fff2b8")
        if role == Qt.ItemDataRole.BackgroundRole and index.row() in self._highlighted_rows:
            return QColor("#dbeafe")
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self._frame.iat[index.row(), index.column()]
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._frame.columns[section])
        return str(section + 1)

    def set_current_row(self, row: int | None) -> None:
        previous = self._current_row
        self._current_row = row
        for changed in (previous, row):
            if (
                changed is not None
                and 0 <= changed < len(self._frame)
                and self.columnCount() > 0
            ):
                self.dataChanged.emit(
                    self.index(changed, 0),
                    self.index(changed, self.columnCount() - 1),
                    [Qt.ItemDataRole.BackgroundRole],
                )

    def set_highlighted_rows(self, rows: list[int]) -> None:
        previous = self._highlighted_rows
        self._highlighted_rows = set(rows)
        affected = previous | self._highlighted_rows
        if self.columnCount() == 0:
            return
        for row in affected:
            if 0 <= row < len(self._frame):
                self.dataChanged.emit(
                    self.index(row, 0),
                    self.index(row, self.columnCount() - 1),
                    [Qt.ItemDataRole.BackgroundRole],
                )


class DataFrameFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.query = ""

    def set_query(self, query: str) -> None:
        self.query = query.strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self.query:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        for column in range(model.columnCount()):
            index = model.index(source_row, column, source_parent)
            value = model.data(index, Qt.ItemDataRole.DisplayRole)
            if value is not None and self.query in str(value).casefold():
                return True
        return False


class TablePanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.model = DataFrameTableModel()
        self.proxy = DataFrameFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search table values")
        self.search_edit.setToolTip("Filter visible table rows by text.")
        self.search_edit.textChanged.connect(self.proxy.set_query)
        self.columns_button = QToolButton()
        self.columns_button.setText("Columns")
        self.columns_button.setToolTip("Choose which columns are visible in the table.")
        self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.columns_menu = QMenu(self.columns_button)
        self.columns_button.setMenu(self.columns_menu)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(False)
        controls = QHBoxLayout()
        controls.addWidget(self.search_edit, 1)
        controls.addWidget(self.columns_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(controls)
        layout.addWidget(self.view)

    def set_frame(self, frame: pd.DataFrame) -> None:
        self.model.set_frame(frame)
        self.proxy.invalidate()
        self._rebuild_columns_menu()

    def select_row(self, row: int) -> None:
        if row < 0 or row >= self.model.rowCount():
            return
        self.model.set_current_row(row)
        source_index = self.model.index(row, 0)
        proxy_index = self.proxy.mapFromSource(source_index)
        if proxy_index.isValid():
            self.view.setCurrentIndex(proxy_index)
            self.view.scrollTo(proxy_index, QTableView.ScrollHint.PositionAtCenter)

    def highlight_rows(self, rows: list[int]) -> None:
        self.model.set_highlighted_rows(rows)
        if rows:
            source_index = self.model.index(rows[len(rows) // 2], 0)
            proxy_index = self.proxy.mapFromSource(source_index)
            if proxy_index.isValid():
                self.view.scrollTo(proxy_index, QTableView.ScrollHint.PositionAtCenter)

    def _rebuild_columns_menu(self) -> None:
        self.columns_menu.clear()
        for column, name in enumerate(self.model._frame.columns):
            action = self.columns_menu.addAction(str(name))
            action.setCheckable(True)
            action.setChecked(not self.view.isColumnHidden(column))
            action.toggled.connect(
                lambda checked, column_index=column: self.view.setColumnHidden(
                    column_index,
                    not checked,
                )
            )
