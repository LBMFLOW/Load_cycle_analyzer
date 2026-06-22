from __future__ import annotations

import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from battery_cycle_analyzer.core.data_model import CurveSpec, InterpolationMode, LoadedDataset
from battery_cycle_analyzer.plotting.plot_controller import PlotController


class PlotPanel(QWidget):
    cursor_moved = pyqtSignal(float, int)
    add_divider_requested = pyqtSignal(float)
    clear_dividers_requested = pyqtSignal()
    export_plot_requested = pyqtSignal()
    integrate_selected_section_requested = pyqtSignal()
    save_selected_section_requested = pyqtSignal()
    copy_cursor_requested = pyqtSignal()
    divider_moved = pyqtSignal(str, float)
    divider_context_requested = pyqtSignal(str, object)
    divider_selected = pyqtSignal(str)
    section_selected = pyqtSignal(object)
    section_context_requested = pyqtSignal(object, object)
    plot_context_requested = pyqtSignal(float, object)

    def __init__(self) -> None:
        super().__init__()
        self._dataset: LoadedDataset | None = None
        self._syncing_cursor_controls = False
        self.toolbar = QToolBar()
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._build_toolbar()
        self.plot_widget = pg.PlotWidget(background="w")
        self.controller = PlotController(self.plot_widget)
        self.controller.cursor_changed.connect(self._cursor_changed)
        self.controller.add_divider_requested.connect(self.add_divider_requested.emit)
        self.controller.trace_context_requested.connect(self._trace_context_menu)
        self.controller.divider_moved.connect(self.divider_moved.emit)
        self.controller.divider_context_requested.connect(
            self.divider_context_requested.emit
        )
        self.controller.divider_selected.connect(self.divider_selected.emit)
        self.controller.section_selected.connect(self.section_selected.emit)
        self.controller.section_context_requested.connect(
            self.section_context_requested.emit
        )
        self.controller.plot_context_requested.connect(self.plot_context_requested.emit)

        self.cursor_slider = QSlider(Qt.Orientation.Horizontal)
        self.cursor_slider.setRange(0, 0)
        self.cursor_slider.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cursor_slider.customContextMenuRequested.connect(self._slider_context_menu)
        self.cursor_slider.valueChanged.connect(self._slider_changed)

        self.cursor_spin = QDoubleSpinBox()
        self.cursor_spin.setDecimals(8)
        self.cursor_spin.setRange(-1e18, 1e18)
        self.cursor_spin.setToolTip("Trace cursor position on the x-axis.")
        self.cursor_spin.valueChanged.connect(self._spin_changed)
        self.cursor_readout_label = QLabel("Cursor: no data")

        cursor_controls = QHBoxLayout()
        cursor_controls.addWidget(QLabel("Trace"))
        cursor_controls.addWidget(self.cursor_slider, 1)
        cursor_controls.addWidget(self.cursor_spin)
        cursor_controls.addWidget(self.cursor_readout_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.plot_widget, 1)
        layout.addLayout(cursor_controls)

    def _build_toolbar(self) -> None:
        reset_action = self.toolbar.addAction("Reset zoom")
        reset_action.setToolTip("Reset the plot view to include all visible data.")
        reset_action.triggered.connect(self.reset_view)
        export_action = self.toolbar.addAction("Export plot")
        export_action.setToolTip("Export the current plot as an image.")
        export_action.triggered.connect(self.export_plot_requested.emit)
        add_divider_action = self.toolbar.addAction("Add divider")
        add_divider_action.setToolTip("Add a divider at the trace cursor.")
        add_divider_action.triggered.connect(
            lambda: self.add_divider_requested.emit(float(self.cursor_spin.value()))
        )
        clear_action = self.toolbar.addAction("Clear dividers")
        clear_action.setToolTip("Remove all dividers from the plot.")
        clear_action.triggered.connect(self.clear_dividers_requested.emit)
        integrate_action = self.toolbar.addAction("Integrate section")
        integrate_action.setToolTip("Integrate visible curves over the selected section.")
        integrate_action.triggered.connect(self.integrate_selected_section_requested.emit)
        save_action = self.toolbar.addAction("Save section")
        save_action.setToolTip("Export the selected section to CSV.")
        save_action.triggered.connect(self.save_selected_section_requested.emit)

    def set_dataset(
        self,
        dataset: LoadedDataset | None,
        curves: list[CurveSpec],
        *,
        x_axis_column: str | None = None,
        normalize_x_axis: bool = False,
    ) -> None:
        self._dataset = dataset
        self.controller.set_dataset(
            dataset,
            curves,
            x_axis_column=x_axis_column,
            normalize_x_axis=normalize_x_axis,
        )
        self._configure_cursor_controls()

    def set_curves(self, curves: list[CurveSpec]) -> None:
        self.controller.set_curves(curves)

    def set_x_axis(self, column: str) -> None:
        self.controller.set_x_axis(column)
        self._configure_cursor_controls()

    def set_normalize_x_axis(self, normalize: bool) -> None:
        self.controller.set_normalize_x_axis(normalize)
        self._configure_cursor_controls()

    def set_interpolation_mode(self, mode: InterpolationMode) -> None:
        self.controller.cursor.set_mode(mode)

    def reset_view(self) -> None:
        self.controller.reset_view()

    def export_plot(self, path: str) -> None:
        if path.lower().endswith(".svg"):
            exporter = pg.exporters.SVGExporter(self.controller.plot_item)
        else:
            exporter = pg.exporters.ImageExporter(self.controller.plot_item)
            exporter.parameters()["width"] = 1800
        exporter.export(path)

    def cursor_readout(self):
        return self.controller.cursor_readout()

    def set_dividers(self, dividers) -> None:
        self.controller.set_dividers(dividers)

    def set_selected_section(self, section) -> None:
        self.controller.set_selected_section(section)

    def row_indexes_for_section(self, section) -> list[int]:
        return self.controller.row_indexes_for_section(section)

    def current_axis_values(self):
        return self.controller.current_axis_values()

    def cursor_value(self) -> float | None:
        return self.controller.cursor_value()

    def set_cursor_value(self, value: float) -> None:
        self.controller.set_cursor_value(value)

    def move_cursor_by_rows(self, delta: int) -> None:
        current = self.cursor_slider.value()
        target = max(self.cursor_slider.minimum(), min(self.cursor_slider.maximum(), current + delta))
        self.controller.set_cursor_to_row(target)

    def snap_cursor_to_nearest(self) -> None:
        value = self.cursor_value()
        if value is None:
            return
        row = self.controller.cursor.nearest_index(value)
        if row >= 0:
            self.controller.set_cursor_to_row(row)

    def visible_x_range(self) -> tuple[float, float]:
        return self.controller.visible_x_range()

    def plot_comparison_overlay(self, overlay_frame) -> None:
        self.controller.plot_comparison_overlay(overlay_frame)

    def _configure_cursor_controls(self) -> None:
        self._syncing_cursor_controls = True
        try:
            row_count = 0 if self._dataset is None else len(self._dataset.frame)
            self.cursor_slider.setRange(0, max(0, row_count - 1))
            if row_count:
                first_value = self.controller.axis_value_at_row(0)
                last_value = self.controller.axis_value_at_row(row_count - 1)
                if first_value is not None and last_value is not None:
                    self.cursor_spin.setRange(
                        min(first_value, last_value),
                        max(first_value, last_value),
                    )
                    self.cursor_spin.setValue(first_value)
                    self.cursor_slider.setValue(0)
        finally:
            self._syncing_cursor_controls = False

    def _slider_changed(self, row: int) -> None:
        if self._syncing_cursor_controls:
            return
        self.controller.set_cursor_to_row(row)

    def _spin_changed(self, value: float) -> None:
        if self._syncing_cursor_controls:
            return
        self.controller.set_cursor_value(value)

    def _cursor_changed(self, value: float, row: int) -> None:
        self._syncing_cursor_controls = True
        try:
            if row >= 0:
                self.cursor_slider.setValue(row)
            self.cursor_spin.setValue(value)
            self.cursor_readout_label.setText(
                f"Cursor: row {row + 1}, x={value:.8g}" if row >= 0 else "Cursor: no data"
            )
        finally:
            self._syncing_cursor_controls = False
        self.cursor_moved.emit(value, row)

    def _slider_context_menu(self, point) -> None:
        menu = QMenu(self)
        add_action = menu.addAction("Add divider")
        snap_action = menu.addAction("Snap cursor to nearest point")
        copy_action = menu.addAction("Copy current values")
        action = menu.exec(self.cursor_slider.mapToGlobal(point))
        if action == add_action:
            self.add_divider_requested.emit(float(self.cursor_spin.value()))
        elif action == snap_action:
            self.snap_cursor_to_nearest()
        elif action == copy_action:
            self.copy_cursor_requested.emit()

    def _trace_context_menu(self, value: float, global_pos) -> None:
        menu = QMenu(self)
        add_action = menu.addAction("Add divider")
        snap_action = menu.addAction("Snap cursor to nearest point")
        copy_action = menu.addAction("Copy current values")
        action = menu.exec(global_pos)
        if action == add_action:
            self.add_divider_requested.emit(float(value))
        elif action == snap_action:
            self.snap_cursor_to_nearest()
        elif action == copy_action:
            self.copy_cursor_requested.emit()
