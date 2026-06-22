from __future__ import annotations

import pyqtgraph as pg

from battery_cycle_analyzer.core.data_model import Section


class SectionOverlay:
    """Owns visual highlight overlays for selected sections."""

    def __init__(self, plot_item: pg.PlotItem) -> None:
        self.plot_item = plot_item
        self._region: pg.LinearRegionItem | None = None

    def highlight(self, section: Section | None) -> None:
        self.clear()
        if section is None:
            return
        view_min, view_max = self.plot_item.vb.viewRange()[0]
        start = section.start_time if section.start_time is not None else view_min
        end = section.end_time if section.end_time is not None else view_max
        if start == end:
            return
        self._region = pg.LinearRegionItem(
            values=(start, end),
            movable=False,
            brush=pg.mkBrush(37, 99, 235, 45),
            pen=pg.mkPen(37, 99, 235, 120),
        )
        self._region.setZValue(-10)
        self.plot_item.addItem(self._region)

    def clear(self) -> None:
        if self._region is not None:
            self.plot_item.removeItem(self._region)
            self._region = None
