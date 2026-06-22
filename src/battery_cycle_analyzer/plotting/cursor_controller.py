from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import QObject, Qt, pyqtSignal

from battery_cycle_analyzer.core.data_model import InterpolationMode
from battery_cycle_analyzer.plotting.cursor_math import AxisData, axis_values, linear_interpolate, nearest_row_index


@dataclass(frozen=True, slots=True)
class CursorReadout:
    cursor_time: float
    row_index: int
    values: dict[str, object]


class CursorController(QObject):
    """Owns plot trace cursor state and lookup behavior."""

    cursor_changed = pyqtSignal(float, int)
    add_divider_requested = pyqtSignal(float)
    trace_context_requested = pyqtSignal(float, object)

    def __init__(self, plot_item: pg.PlotItem) -> None:
        super().__init__()
        self.plot_item = plot_item
        self.line = pg.InfiniteLine(angle=90, movable=True)
        self.line.sigPositionChanged.connect(self._line_moved)
        original_click = self.line.mouseClickEvent

        def cursor_click(event, original=original_click):
            if event.button() == Qt.MouseButton.RightButton:
                self.trace_context_requested.emit(
                    float(self.line.value()), event.screenPos().toPoint()
                )
                event.accept()
            else:
                original(event)

        self.line.mouseClickEvent = cursor_click
        self.plot_item.addItem(self.line)
        self._frame: pd.DataFrame | None = None
        self._x_axis_column: str | None = None
        self._axis: AxisData | None = None
        self._mode: InterpolationMode = "nearest"
        self._updating = False

    def set_dataset(
        self,
        frame: pd.DataFrame | None,
        x_axis_column: str | None,
        *,
        normalize: bool = False,
    ) -> None:
        self._frame = frame
        self._x_axis_column = x_axis_column
        self._axis = (
            axis_values(frame[x_axis_column], normalize=normalize)
            if frame is not None and x_axis_column is not None and x_axis_column in frame
            else None
        )

    def set_mode(self, mode: InterpolationMode) -> None:
        self._mode = mode

    def set_time(self, time_value: float) -> None:
        self._updating = True
        try:
            self.line.setValue(float(time_value))
        finally:
            self._updating = False
        self.cursor_changed.emit(float(time_value), self.nearest_index(time_value))

    def current_time(self) -> float | None:
        try:
            return float(self.line.value())
        except Exception:
            return None

    def readout(self, value_columns: list[str]) -> CursorReadout | None:
        if (
            self._frame is None
            or self._x_axis_column is None
            or self._axis is None
            or self._frame.empty
        ):
            return None
        cursor_time = float(self.line.value())
        row = self.nearest_index(cursor_time)
        if row < 0:
            return None
        values: dict[str, object] = {
            self._x_axis_column: self._axis.display_values.iloc[row],
        }
        for column in value_columns:
            if column not in self._frame:
                continue
            if self._mode == "linear":
                values[column] = linear_interpolate(
                    self._axis.values,
                    self._frame[column].to_numpy(dtype=float),
                    cursor_time,
                )
            else:
                values[column] = float(self._frame[column].iloc[row])
        return CursorReadout(cursor_time, row, values)

    def nearest_index(self, time_value: float) -> int:
        if self._axis is None:
            return -1
        return nearest_row_index(self._axis.values, time_value)

    def axis_value_at_row(self, row: int) -> float | None:
        if self._axis is None or row < 0 or row >= self._axis.values.size:
            return None
        value = self._axis.values[row]
        return None if pd.isna(value) else float(value)

    def _line_moved(self) -> None:
        if self._updating:
            return
        time_value = float(self.line.value())
        self.cursor_changed.emit(time_value, self.nearest_index(time_value))
