from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal

from battery_cycle_analyzer.core.data_model import CurveSpec, Divider, LoadedDataset, Section
from battery_cycle_analyzer.core.sections import SectionManager
from battery_cycle_analyzer.plotting.cursor_controller import CursorController
from battery_cycle_analyzer.plotting.cursor_math import axis_values
from battery_cycle_analyzer.plotting.divider_controller import DividerController
from battery_cycle_analyzer.plotting.section_overlay import SectionOverlay

MAX_DISPLAY_POINTS = 100_000


class PlotController(QObject):
    """Coordinates dataset curves, cursor, dividers, and section overlays."""

    cursor_changed = pyqtSignal(float, int)
    add_divider_requested = pyqtSignal(float)
    trace_context_requested = pyqtSignal(float, QPoint)
    divider_moved = pyqtSignal(str, float)
    divider_context_requested = pyqtSignal(str, QPoint)
    divider_selected = pyqtSignal(str)
    section_selected = pyqtSignal(object)
    section_context_requested = pyqtSignal(object, QPoint)
    plot_context_requested = pyqtSignal(float, QPoint)

    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        super().__init__()
        self.plot_widget = plot_widget
        self.plot_item = plot_widget.getPlotItem()
        self.cursor = CursorController(self.plot_item)
        self.cursor.cursor_changed.connect(self.cursor_changed.emit)
        self.cursor.add_divider_requested.connect(self.add_divider_requested.emit)
        self.cursor.trace_context_requested.connect(self.trace_context_requested.emit)
        self.dividers = DividerController(self.plot_item)
        self.dividers.divider_moved.connect(self.divider_moved.emit)
        self.dividers.divider_context_requested.connect(self.divider_context_requested.emit)
        self.dividers.divider_selected.connect(self.divider_selected.emit)
        self.sections = SectionOverlay(self.plot_item)
        self.section_manager = SectionManager()
        self.dataset: LoadedDataset | None = None
        self.curves: list[CurveSpec] = []
        self.divider_state: list[Divider] = []
        self.selected_section: Section | None = None
        self.x_axis_column: str | None = None
        self.normalize_x_axis = False

        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_item.addLegend()
        self.plot_widget.scene().sigMouseClicked.connect(self._plot_clicked)

    def set_dataset(
        self,
        dataset: LoadedDataset | None,
        curves: list[CurveSpec],
        *,
        x_axis_column: str | None = None,
        normalize_x_axis: bool = False,
    ) -> None:
        self.dataset = dataset
        self.curves = curves
        self.x_axis_column = x_axis_column or (dataset.time_column if dataset else None)
        self.normalize_x_axis = normalize_x_axis
        self.redraw()

    def set_x_axis(self, column: str) -> None:
        self.x_axis_column = column
        self.redraw()

    def set_normalize_x_axis(self, normalize: bool) -> None:
        self.normalize_x_axis = normalize
        self.redraw()

    def set_curves(self, curves: list[CurveSpec]) -> None:
        self.curves = curves
        self.redraw()

    def visible_curve_columns(self) -> list[str]:
        return [curve.column for curve in self.curves if curve.visible]

    def redraw(self) -> None:
        self.plot_item.clear()
        self.plot_item.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_item.addItem(self.cursor.line)

        if self.dataset is None or self.dataset.frame.empty or self.x_axis_column is None:
            self.cursor.set_dataset(None, None)
            return

        frame = self.dataset.frame
        if self.x_axis_column not in frame:
            self.cursor.set_dataset(None, None)
            return

        axis = axis_values(frame[self.x_axis_column], normalize=self.normalize_x_axis)
        self.cursor.set_dataset(
            frame,
            self.x_axis_column,
            normalize=self.normalize_x_axis,
        )
        for curve in self.curves:
            if not curve.visible or curve.column not in frame:
                continue
            x_display, y_display = self._display_arrays(
                axis.values,
                frame[curve.column].to_numpy(dtype=float),
            )
            item = self.plot_item.plot(
                x_display,
                y_display,
                name=curve.name,
                pen=pg.mkPen(curve.color or None, width=1.5),
            )
            item.setClipToView(True)
            item.setDownsampling(auto=True, method="peak")
        x_unit = axis.label_suffix or self.dataset.metadata.units.get(self.x_axis_column, "")
        self.plot_item.setLabel("bottom", self.x_axis_column, units=x_unit or None)
        y_units = {
            self.dataset.metadata.units.get(curve.column, "")
            for curve in self.curves
            if curve.visible and self.dataset.metadata.units.get(curve.column, "")
        }
        self.plot_item.setLabel(
            "left",
            "Value",
            units=next(iter(y_units)) if len(y_units) == 1 else None,
        )
        self.plot_widget.autoRange()
        self.dividers.set_dividers(self.divider_state)
        self.sections.highlight(self.selected_section)

        first_value = self.cursor.axis_value_at_row(0)
        if first_value is not None:
            self.cursor.set_time(first_value)

    def _display_arrays(self, x_values, y_values):
        size = len(x_values)
        if size <= MAX_DISPLAY_POINTS:
            return x_values, y_values
        stride = max(1, math.ceil(size / MAX_DISPLAY_POINTS))
        return x_values[::stride], y_values[::stride]

    def set_cursor_value(self, value: float) -> None:
        self.cursor.set_time(value)

    def cursor_value(self) -> float | None:
        return self.cursor.current_time()

    def set_cursor_to_row(self, row: int) -> None:
        value = self.cursor.axis_value_at_row(row)
        if value is not None:
            self.cursor.set_time(value)

    def axis_value_at_row(self, row: int) -> float | None:
        return self.cursor.axis_value_at_row(row)

    def cursor_readout(self):
        return self.cursor.readout(self.visible_curve_columns())

    def reset_view(self) -> None:
        self.plot_widget.enableAutoRange()
        self.plot_widget.autoRange()

    def set_dividers(self, dividers: list[Divider]) -> None:
        self.divider_state = self.section_manager.sorted_dividers(dividers)
        self.dividers.set_dividers(self.divider_state)
        self.sections.highlight(self.selected_section)

    def set_selected_section(self, section: Section | None) -> None:
        self.selected_section = section
        self.sections.highlight(section)

    def current_sections(self) -> list[Section]:
        axis = self.current_axis_values()
        if axis is None:
            return []
        return self.section_manager.sections_for_time_values(self.divider_state, axis)

    def row_indexes_for_section(self, section: Section) -> list[int]:
        axis = self.current_axis_values()
        if axis is None:
            return []
        return self.section_manager.row_indexes(axis, section).tolist()

    def current_axis_values(self):
        if (
            self.dataset is None
            or self.x_axis_column is None
            or self.x_axis_column not in self.dataset.frame
        ):
            return None
        return axis_values(
            self.dataset.frame[self.x_axis_column],
            normalize=self.normalize_x_axis,
        ).values

    def visible_x_range(self) -> tuple[float, float]:
        x_range = self.plot_item.vb.viewRange()[0]
        return float(x_range[0]), float(x_range[1])

    def plot_comparison_overlay(self, overlay_frame) -> None:
        self.plot_item.clear()
        self.plot_item.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2"]
        if overlay_frame is None or overlay_frame.empty:
            return
        for index, (name, group) in enumerate(overlay_frame.groupby("dataset")):
            self.plot_item.plot(
                group["cycle_index"].to_numpy(dtype=float),
                group["discharge_energy_retention_pct"].to_numpy(dtype=float),
                name=str(name),
                pen=pg.mkPen(colors[index % len(colors)], width=1.5),
            )
        self.plot_item.setLabel("bottom", "Cycle index", units="cycle")
        self.plot_item.setLabel("left", "Discharge energy retention", units="%")
        self.plot_widget.autoRange()

    def _plot_clicked(self, event) -> None:
        if self.dataset is None or self.x_axis_column is None:
            return
        if not self.plot_widget.sceneBoundingRect().contains(event.scenePos()):
            return
        point = self.plot_item.vb.mapSceneToView(event.scenePos())
        axis = self.current_axis_values()
        if axis is None:
            return
        section = self.section_manager.section_at_time(
            self.divider_state, axis, float(point.x())
        )
        if section is None:
            if event.button() == Qt.MouseButton.RightButton:
                self.plot_context_requested.emit(float(point.x()), event.screenPos().toPoint())
                event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_selected_section(section)
            self.section_selected.emit(section)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.section_context_requested.emit(section, event.screenPos().toPoint())
            event.accept()
