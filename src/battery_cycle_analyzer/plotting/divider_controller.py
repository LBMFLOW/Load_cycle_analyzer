from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal

from battery_cycle_analyzer.core.data_model import Divider


class DividerController(QObject):
    """Owns movable divider graphics and propagates divider edits."""

    divider_moved = pyqtSignal(str, float)
    divider_context_requested = pyqtSignal(str, QPoint)
    divider_selected = pyqtSignal(str)

    def __init__(self, plot_item: pg.PlotItem) -> None:
        super().__init__()
        self.plot_item = plot_item
        self._lines: dict[str, pg.InfiniteLine] = {}

    def set_dividers(self, dividers: list[Divider]) -> None:
        self.clear()
        for divider in dividers:
            line = pg.InfiniteLine(
                pos=divider.time_value,
                angle=90,
                movable=True,
                label=divider.name,
            )
            line.sigPositionChangeFinished.connect(
                lambda changed, divider_id=divider.id: self.divider_moved.emit(
                    divider_id, float(changed.value())
                )
            )
            original_click = line.mouseClickEvent

            def divider_click(event, *, divider_id=divider.id, original=original_click):
                if event.button() == Qt.MouseButton.RightButton:
                    self.divider_context_requested.emit(
                        divider_id, event.screenPos().toPoint()
                    )
                    event.accept()
                else:
                    if event.button() == Qt.MouseButton.LeftButton:
                        self.divider_selected.emit(divider_id)
                    original(event)

            line.mouseClickEvent = divider_click
            self._lines[divider.id] = line
            self.plot_item.addItem(line)

    def clear(self) -> None:
        for line in self._lines.values():
            self.plot_item.removeItem(line)
        self._lines.clear()
