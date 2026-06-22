from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from battery_aging_app.analysis.sections import build_sections, section_for_time
from battery_aging_app.models import Divider, ImportedDataset, Section
from battery_aging_app.plotting.sync import nearest_index


class BatteryPlotWidget(QWidget):
    cursorTimeChanged = pyqtSignal(float)
    addDividerRequested = pyqtSignal(float)
    sectionSelected = pyqtSignal(object)
    sectionContextRequested = pyqtSignal(object, object)
    dividerMoved = pyqtSignal(str, float)
    dividerRenameRequested = pyqtSignal(str)
    dividerRemoveRequested = pyqtSignal(str)
    dividerNoteRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pg.setConfigOptions(antialias=False)
        self.dataset: ImportedDataset | None = None
        self.visible_curves: list[str] = []
        self.dividers: list[Divider] = []
        self._divider_lines: dict[str, pg.InfiniteLine] = {}
        self._curve_items: dict[str, pg.PlotDataItem] = {}
        self._sections: list[Section] = []
        self._selected_section: Section | None = None
        self._updating_cursor = False

        self.plot = pg.PlotWidget(background="#ffffff")
        self.plot.showGrid(x=True, y=True, alpha=0.28)
        self.plot.addLegend(offset=(10, 10))
        self.plot.setMenuEnabled(False)
        self.plot.scene().sigMouseClicked.connect(self._mouse_clicked)

        self.cursor = pg.InfiniteLine(
            angle=90,
            movable=True,
            pen=pg.mkPen("#1f2937", width=2),
            hoverPen=pg.mkPen("#111827", width=3),
            label="{value:0.6g}",
            labelOpts={"position": 0.95, "color": "#111827"},
        )
        self.cursor.sigPositionChanged.connect(self._cursor_line_moved)
        self.plot.addItem(self.cursor)

        self._selected_region: pg.LinearRegionItem | None = None

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.slider.customContextMenuRequested.connect(self._slider_context_menu)
        self.slider.valueChanged.connect(self._slider_moved)

        self.time_spin = QDoubleSpinBox()
        self.time_spin.setDecimals(8)
        self.time_spin.setRange(-1e18, 1e18)
        self.time_spin.valueChanged.connect(self.set_cursor_time)

        self.reset_button = QToolButton()
        self.reset_button.setText("Reset")
        self.reset_button.setToolTip("Reset plot view")
        self.reset_button.clicked.connect(self.reset_view)

        self.export_png_button = QPushButton("Export PNG")
        self.export_png_button.clicked.connect(lambda: self.export_plot_image())
        self.export_svg_button = QPushButton("Export SVG")
        self.export_svg_button.clicked.connect(lambda: self.export_plot_svg())

        controls = QHBoxLayout()
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.time_spin)
        controls.addWidget(self.reset_button)
        controls.addWidget(self.export_png_button)
        controls.addWidget(self.export_svg_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot, 1)
        layout.addLayout(controls)

    def set_dataset(self, dataset: ImportedDataset | None) -> None:
        self.dataset = dataset
        if dataset is None:
            self.visible_curves = []
            self.dividers = []
        else:
            self.visible_curves = [
                column
                for column in [
                    dataset.discharge_column,
                    dataset.charge_column,
                    *dataset.plottable_columns,
                ]
                if column is not None and column != dataset.time_column
            ]
            self.visible_curves = list(dict.fromkeys(self.visible_curves))
        self.replot()

    def set_visible_curves(self, curves: list[str]) -> None:
        self.visible_curves = curves
        self.replot()

    def set_dividers(self, dividers: list[Divider]) -> None:
        self.dividers = dividers
        self._rebuild_divider_lines()
        self._rebuild_sections()

    def selected_section(self) -> Section | None:
        return self._selected_section

    def sections(self) -> list[Section]:
        return list(self._sections)

    def replot(self) -> None:
        self.plot.clear()
        self._curve_items.clear()
        self.plot.addLegend(offset=(10, 10))
        self.plot.showGrid(x=True, y=True, alpha=0.28)
        self.plot.addItem(self.cursor)
        self._selected_region = None

        dataset = self.dataset
        if dataset is None or dataset.frame.empty:
            self.slider.setRange(0, 0)
            return

        frame = dataset.frame
        time_column = dataset.time_column
        x = frame[time_column].to_numpy(dtype=float)
        colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2"]
        for index, column in enumerate(self.visible_curves):
            if column not in frame:
                continue
            item = self.plot.plot(
                x,
                frame[column].to_numpy(dtype=float),
                pen=pg.mkPen(colors[index % len(colors)], width=1.6),
                name=column,
            )
            item.setClipToView(True)
            item.setDownsampling(auto=True, method="peak")
            self._curve_items[column] = item

        time_unit = dataset.metadata.units.get(time_column, "")
        self.plot.setLabel("bottom", time_column, units=time_unit or None)
        axis_label = "Energy / selected value"
        energy_units = [
            dataset.metadata.units.get(column, "")
            for column in self.visible_curves
            if dataset.metadata.units.get(column, "")
        ]
        if energy_units and len(set(energy_units)) == 1:
            self.plot.setLabel("left", axis_label, units=energy_units[0])
        else:
            self.plot.setLabel("left", axis_label)

        valid_time = x[~np.isnan(x)]
        if valid_time.size:
            self.time_spin.blockSignals(True)
            self.time_spin.setRange(float(np.nanmin(valid_time)), float(np.nanmax(valid_time)))
            self.time_spin.blockSignals(False)
            self.slider.setRange(0, len(frame) - 1)
            self.set_cursor_time(float(valid_time[0]))
        self._rebuild_divider_lines()
        self._rebuild_sections()
        self.reset_view()

    def set_cursor_time(self, time_value: float) -> None:
        if self._updating_cursor:
            return
        self._updating_cursor = True
        try:
            self.cursor.setValue(float(time_value))
            self.time_spin.blockSignals(True)
            self.time_spin.setValue(float(time_value))
            self.time_spin.blockSignals(False)
            if self.dataset is not None and not self.dataset.frame.empty:
                row = nearest_index(self.dataset.frame[self.dataset.time_column], time_value)
                self.slider.blockSignals(True)
                self.slider.setValue(row)
                self.slider.blockSignals(False)
            self.cursorTimeChanged.emit(float(time_value))
        finally:
            self._updating_cursor = False

    def reset_view(self) -> None:
        self.plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot.autoRange()

    def export_plot_image(self, path: str | Path | None = None) -> None:
        if path is None:
            from PyQt6.QtWidgets import QFileDialog

            selected, _ = QFileDialog.getSaveFileName(
                self, "Export Plot PNG", "plot.png", "PNG Images (*.png)"
            )
            if not selected:
                return
            path = selected
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.parameters()["width"] = 1800
        exporter.export(str(path))

    def export_plot_svg(self, path: str | Path | None = None) -> None:
        if path is None:
            from PyQt6.QtWidgets import QFileDialog

            selected, _ = QFileDialog.getSaveFileName(
                self, "Export Plot SVG", "plot.svg", "SVG Files (*.svg)"
            )
            if not selected:
                return
            path = selected
        exporter = pg.exporters.SVGExporter(self.plot.plotItem)
        exporter.export(str(path))

    def highlight_section(self, section: Section | None) -> None:
        if self._selected_region is not None:
            self.plot.removeItem(self._selected_region)
            self._selected_region = None
        self._selected_section = section
        if section is None:
            return
        view_min, view_max = self.plot.viewRange()[0]
        start = section.start_time if section.start_time is not None else view_min
        end = section.end_time if section.end_time is not None else view_max
        if start == end:
            return
        self._selected_region = pg.LinearRegionItem(
            values=(start, end),
            movable=False,
            brush=pg.mkBrush(37, 99, 235, 38),
            pen=pg.mkPen(37, 99, 235, 90),
        )
        self._selected_region.setZValue(-10)
        self.plot.addItem(self._selected_region)

    def _cursor_line_moved(self) -> None:
        if self._updating_cursor:
            return
        self.set_cursor_time(float(self.cursor.value()))

    def _slider_moved(self, row: int) -> None:
        dataset = self.dataset
        if dataset is None or dataset.frame.empty:
            return
        time_value = float(dataset.frame[dataset.time_column].iloc[row])
        self.set_cursor_time(time_value)

    def _slider_context_menu(self, point: QPoint) -> None:
        menu = QMenu(self)
        add_action = menu.addAction("Add divider")
        action = menu.exec(self.slider.mapToGlobal(point))
        if action == add_action:
            self.addDividerRequested.emit(float(self.cursor.value()))

    def _mouse_clicked(self, event) -> None:
        dataset = self.dataset
        if dataset is None:
            return
        if not self.plot.sceneBoundingRect().contains(event.scenePos()):
            return
        mouse_point = self.plot.plotItem.vb.mapSceneToView(event.scenePos())
        section = section_for_time(self._sections, float(mouse_point.x()))
        if event.button() == Qt.MouseButton.LeftButton:
            self.highlight_section(section)
            if section is not None:
                self.sectionSelected.emit(section)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            if section is not None:
                self.sectionContextRequested.emit(section, event.screenPos().toPoint())
            else:
                menu = QMenu(self)
                add_action = menu.addAction("Add divider")
                action = menu.exec(event.screenPos().toPoint())
                if action == add_action:
                    self.addDividerRequested.emit(float(self.cursor.value()))
            event.accept()

    def _rebuild_divider_lines(self) -> None:
        for line in self._divider_lines.values():
            try:
                self.plot.removeItem(line)
            except Exception:
                pass
        self._divider_lines.clear()
        for divider in self.dividers:
            line = pg.InfiniteLine(
                pos=divider.time,
                angle=90,
                movable=True,
                pen=pg.mkPen("#0f766e", width=2, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen("#0f766e", width=3),
                label=divider.name,
                labelOpts={"position": 0.08, "color": "#0f766e"},
            )
            line.sigPositionChangeFinished.connect(
                lambda changed_line, divider_id=divider.id: self._divider_finished(
                    divider_id, float(changed_line.value())
                )
            )
            original_click = line.mouseClickEvent

            def click_handler(event, *, divider_id=divider.id, original=original_click):
                if event.button() == Qt.MouseButton.RightButton:
                    self._divider_context_menu(divider_id, event.screenPos().toPoint())
                    event.accept()
                else:
                    original(event)

            line.mouseClickEvent = click_handler
            self._divider_lines[divider.id] = line
            self.plot.addItem(line)

    def _divider_finished(self, divider_id: str, time_value: float) -> None:
        for divider in self.dividers:
            if divider.id == divider_id:
                divider.time = time_value
                break
        self._rebuild_sections()
        self.dividerMoved.emit(divider_id, time_value)

    def _divider_context_menu(self, divider_id: str, global_pos: QPoint) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction("Rename divider")
        note_action = menu.addAction("Add note")
        remove_action = menu.addAction("Remove divider")
        action = menu.exec(global_pos)
        if action == rename_action:
            self.dividerRenameRequested.emit(divider_id)
        elif action == note_action:
            self.dividerNoteRequested.emit(divider_id)
        elif action == remove_action:
            self.dividerRemoveRequested.emit(divider_id)

    def _rebuild_sections(self) -> None:
        dataset = self.dataset
        if dataset is None or dataset.frame.empty:
            self._sections = []
            return
        time = dataset.frame[dataset.time_column].to_numpy(dtype=float)
        valid = time[~np.isnan(time)]
        self._sections = build_sections(
            self.dividers,
            time_min=float(valid.min()) if valid.size else None,
            time_max=float(valid.max()) if valid.size else None,
        )
