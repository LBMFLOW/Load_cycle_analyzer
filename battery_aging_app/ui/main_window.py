from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from battery_aging_app.analysis.integration import integrate_visible_curves
from battery_aging_app.analysis.metrics import add_standard_metrics, section_statistics
from battery_aging_app.analysis.sections import (
    new_divider,
    row_indexes_for_section,
)
from battery_aging_app.exports.csv_export import (
    export_processed_dataset,
    export_section_csv,
)
from battery_aging_app.exports.report import write_html_report
from battery_aging_app.importers.csv_import import batch_read_battery_csv, read_battery_csv
from battery_aging_app.models import AnalysisSettings, Divider, ImportedDataset, Section
from battery_aging_app.plotting.sync import trace_values
from battery_aging_app.session import ProjectSession
from battery_aging_app.ui.dialogs import IntegrationResultsDialog
from battery_aging_app.ui.import_dialog import ImportDialog
from battery_aging_app.ui.plot_widget import BatteryPlotWidget
from battery_aging_app.ui.table_model import DataFrameTableModel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Battery Aging Load-Cycle Analyzer")
        self.dataset: ImportedDataset | None = None
        self.loaded_datasets: list[ImportedDataset] = []
        self.dividers: list[Divider] = []
        self.selected_section: Section | None = None
        self.project_path: Path | None = None

        self.plot = BatteryPlotWidget()
        self.table_model = DataFrameTableModel()
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)

        self.curve_list = QListWidget()
        self.curve_list.itemChanged.connect(self._curve_visibility_changed)
        self.interpolation_combo = QComboBox()
        self.interpolation_combo.addItem("Nearest sample", "nearest")
        self.interpolation_combo.addItem("Linear interpolation", "linear")
        self.interpolation_combo.currentIndexChanged.connect(
            lambda _index: self._cursor_changed(float(self.plot.cursor.value()))
        )
        self.readout = QPlainTextEdit()
        self.readout.setReadOnly(True)
        self.readout.setMaximumBlockCount(200)
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)

        self._build_layout()
        self._build_menus()
        self._connect_plot_signals()
        self._set_empty_state()

    def _build_layout(self) -> None:
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Visible Curves"))
        right_layout.addWidget(self.curve_list, 2)
        right_layout.addWidget(QLabel("Trace Lookup"))
        right_layout.addWidget(self.interpolation_combo)
        right_layout.addWidget(QLabel("Cursor Readout"))
        right_layout.addWidget(self.readout, 1)
        integrate_button = QPushButton("Integrate Selected Section")
        integrate_button.clicked.connect(self.integrate_selected_section)
        right_layout.addWidget(integrate_button)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self.plot)
        top_splitter.addWidget(right_panel)
        top_splitter.setStretchFactor(0, 5)
        top_splitter.setStretchFactor(1, 1)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(self.table)
        bottom_splitter.addWidget(self.results)
        bottom_splitter.setStretchFactor(0, 4)
        bottom_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)

        self.setCentralWidget(main_splitter)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Open CSV...", self.open_csv)
        file_menu.addAction("Batch Import CSV...", self.batch_import)
        file_menu.addSeparator()
        file_menu.addAction("Save Project...", self.save_project)
        file_menu.addAction("Load Project...", self.load_project)
        file_menu.addSeparator()
        file_menu.addAction("Export Selected Section CSV...", self.export_selected_section)
        file_menu.addAction("Export Processed Dataset...", self.export_processed_dataset)
        file_menu.addAction("Export Analysis Report HTML...", self.export_report)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        analysis_menu = self.menuBar().addMenu("&Analysis")
        analysis_menu.addAction("Add Standard Derived Metrics", self.add_metrics)
        analysis_menu.addAction("Integrate Selected Section", self.integrate_selected_section)
        analysis_menu.addAction("Integrate Whole Dataset", self.integrate_whole_dataset)

        divider_menu = self.menuBar().addMenu("&Dividers")
        divider_menu.addAction("Add Divider At Cursor", self.add_divider_at_cursor)
        divider_menu.addAction("Clear Dividers", self.clear_dividers)

    def _connect_plot_signals(self) -> None:
        self.plot.cursorTimeChanged.connect(self._cursor_changed)
        self.plot.addDividerRequested.connect(self.add_divider_at_time)
        self.plot.sectionSelected.connect(self._section_selected)
        self.plot.sectionContextRequested.connect(self._section_context_menu)
        self.plot.dividerMoved.connect(self._divider_moved)
        self.plot.dividerRenameRequested.connect(self.rename_divider)
        self.plot.dividerRemoveRequested.connect(self.remove_divider)
        self.plot.dividerNoteRequested.connect(self.note_divider)

    def open_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Battery CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        self._import_one(Path(path))

    def batch_import(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Batch Import Battery CSVs", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not paths:
            return
        first = Path(paths[0])
        dialog = ImportDialog(first, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            datasets = batch_read_battery_csv(paths, dialog.mapping())
        except Exception as exc:
            QMessageBox.critical(self, "Batch Import Failed", str(exc))
            return
        self.loaded_datasets = datasets
        self._load_dataset(datasets[0])
        self.statusBar().showMessage(f"Imported {len(datasets)} CSV files.", 5000)

    def save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "battery_project.json", "Project JSON (*.json)"
        )
        if not path:
            return
        session = self._session_from_state()
        session.save(path)
        self.project_path = Path(path)
        self.statusBar().showMessage(f"Saved project {path}", 5000)

    def load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "Project JSON (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            session = ProjectSession.load(path)
            if not session.loaded_file_paths:
                raise ValueError("Project contains no loaded file paths.")
            first_path = session.loaded_file_paths[0]
            mapping = session.mappings.get(first_path)
            if mapping is None:
                raise ValueError("Project does not include a mapping for the first file.")
            dataset = read_battery_csv(first_path, mapping)
        except Exception as exc:
            QMessageBox.critical(self, "Project Load Failed", str(exc))
            return
        self.project_path = Path(path)
        self.dividers = session.dividers
        self._load_dataset(dataset)
        self._set_checked_curves(session.visible_curves)
        self.interpolation_combo.setCurrentIndex(
            max(
                0,
                self.interpolation_combo.findData(
                    session.analysis_settings.interpolation_mode
                ),
            )
        )
        self.plot.set_dividers(self.dividers)
        self.statusBar().showMessage(f"Loaded project {path}", 5000)

    def export_selected_section(self) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        section = self.selected_section
        if section is None:
            QMessageBox.information(
                self, "No Section Selected", "Click a plot section before exporting."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Section CSV", "section.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        export_section_csv(dataset, section, path, curves=self._visible_curves())
        self.statusBar().showMessage(f"Exported section to {path}", 5000)

    def export_processed_dataset(self) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Processed Dataset", "processed_dataset.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        export_processed_dataset(dataset.frame, path)
        self.statusBar().showMessage(f"Exported processed dataset to {path}", 5000)

    def export_report(self) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HTML Report", "analysis_report.html", "HTML Files (*.html)"
        )
        if not path:
            return
        section = self.selected_section
        results, _warnings = integrate_visible_curves(
            dataset, visible_curves=self._visible_curves(), section=section
        )
        write_html_report(dataset, path, selected_section=section, integration_results=results)
        self.statusBar().showMessage(f"Exported report to {path}", 5000)

    def add_metrics(self) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        dataset.frame = add_standard_metrics(
            dataset.frame,
            time_column=dataset.time_column,
            discharge_column=dataset.discharge_column,
            charge_column=dataset.charge_column,
        )
        self.table_model.set_frame(dataset.frame, dataset.metadata.units)
        self.plot.set_dataset(dataset)
        self._populate_curve_list()

    def add_divider_at_cursor(self) -> None:
        self.add_divider_at_time(float(self.plot.cursor.value()))

    def add_divider_at_time(self, time_value: float) -> None:
        divider = new_divider(time_value, f"Divider {len(self.dividers) + 1}")
        self.dividers.append(divider)
        self.plot.set_dividers(self.dividers)
        self.statusBar().showMessage(f"Added divider at {time_value:.8g}.", 3000)

    def clear_dividers(self) -> None:
        self.dividers.clear()
        self.selected_section = None
        self.plot.set_dividers(self.dividers)
        self.plot.highlight_section(None)
        self.table_model.set_highlighted_rows([])

    def rename_divider(self, divider_id: str) -> None:
        divider = self._find_divider(divider_id)
        if divider is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename Divider", "Name", text=divider.name
        )
        if accepted and name.strip():
            divider.name = name.strip()
            self.plot.set_dividers(self.dividers)

    def note_divider(self, divider_id: str) -> None:
        divider = self._find_divider(divider_id)
        if divider is None:
            return
        note, accepted = QInputDialog.getMultiLineText(
            self, "Divider Note", divider.name, divider.note
        )
        if accepted:
            divider.note = note

    def remove_divider(self, divider_id: str) -> None:
        self.dividers = [divider for divider in self.dividers if divider.id != divider_id]
        self.plot.set_dividers(self.dividers)

    def integrate_selected_section(self) -> None:
        if self.selected_section is None:
            choice = QMessageBox.question(
                self,
                "No Section Selected",
                "No section is selected. Integrate the whole loaded dataset?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        self._show_integration(self.selected_section)

    def integrate_whole_dataset(self) -> None:
        self._show_integration(None)

    def _show_integration(self, section: Section | None) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        results, warnings = integrate_visible_curves(
            dataset, visible_curves=self._visible_curves(), section=section
        )
        self._write_results_panel(results, warnings)
        IntegrationResultsDialog(results, warnings, self).exec()

    def _import_one(self, path: Path) -> None:
        dialog = ImportDialog(path, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            dataset = read_battery_csv(path, dialog.mapping())
        except Exception as exc:
            QMessageBox.critical(self, "CSV Import Failed", str(exc))
            return
        self.loaded_datasets = [dataset]
        self.dividers.clear()
        self._load_dataset(dataset)

    def _load_dataset(self, dataset: ImportedDataset) -> None:
        self.dataset = dataset
        self.table_model.set_frame(dataset.frame, dataset.metadata.units)
        self.plot.set_dataset(dataset)
        self.plot.set_dividers(self.dividers)
        self._populate_curve_list()
        self._show_import_warnings(dataset)
        self.statusBar().showMessage(
            f"Loaded {Path(dataset.metadata.source_file).name}: {len(dataset.frame)} rows",
            5000,
        )

    def _populate_curve_list(self) -> None:
        dataset = self.dataset
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        if dataset is not None:
            for column in dataset.plottable_columns:
                item = QListWidgetItem(column)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.curve_list.addItem(item)
        self.curve_list.blockSignals(False)
        self._curve_visibility_changed()

    def _set_checked_curves(self, curves: list[str]) -> None:
        wanted = set(curves)
        self.curve_list.blockSignals(True)
        for index in range(self.curve_list.count()):
            item = self.curve_list.item(index)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.text() in wanted
                else Qt.CheckState.Unchecked
            )
        self.curve_list.blockSignals(False)
        self._curve_visibility_changed()

    def _curve_visibility_changed(self) -> None:
        curves = self._visible_curves()
        self.plot.set_visible_curves(curves)

    def _visible_curves(self) -> list[str]:
        curves: list[str] = []
        for index in range(self.curve_list.count()):
            item = self.curve_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                curves.append(item.text())
        return curves

    def _cursor_changed(self, time_value: float) -> None:
        dataset = self.dataset
        if dataset is None:
            return
        readout = trace_values(
            dataset.frame,
            time_column=dataset.time_column,
            value_columns=self._visible_curves(),
            cursor_time=time_value,
            mode=self.interpolation_combo.currentData() or "nearest",
        )
        lines = [f"Row: {readout.row_index + 1}"]
        for column, value in readout.values.items():
            unit = dataset.metadata.units.get(column, "")
            suffix = f" {unit}" if unit else ""
            lines.append(f"{column}: {value:.8g}{suffix}")
        self.readout.setPlainText("\n".join(lines))
        self.table_model.set_cursor_row(readout.row_index)
        index = self.table_model.index(readout.row_index, 0)
        self.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
        self.table.setCurrentIndex(index)

    def _section_selected(self, section: Section) -> None:
        dataset = self.dataset
        if dataset is None:
            return
        self.selected_section = section
        rows = row_indexes_for_section(
            dataset.frame[dataset.time_column].to_numpy(dtype=float), section
        )
        self.table_model.set_highlighted_rows(rows.tolist())
        if rows.size:
            self.table.scrollTo(
                self.table_model.index(int(rows[len(rows) // 2]), 0),
                QTableView.ScrollHint.PositionAtCenter,
            )
        results, warnings = integrate_visible_curves(
            dataset, visible_curves=self._visible_curves(), section=section
        )
        self._write_results_panel(results, warnings)

    def _section_context_menu(self, section: Section, global_pos) -> None:
        menu = QMenu(self)
        save_action = menu.addAction("Save data section")
        integrate_action = menu.addAction("Integrate data")
        rename_action = menu.addAction("Rename section")
        stats_action = menu.addAction("Show section statistics")
        delete_border_action = menu.addAction("Delete bordering dividers")
        action = menu.exec(global_pos)
        self.selected_section = section
        self.plot.highlight_section(section)
        if action == save_action:
            self.export_selected_section()
        elif action == integrate_action:
            self._show_integration(section)
        elif action == rename_action:
            name, accepted = QInputDialog.getText(
                self, "Rename Section", "Name", text=section.name
            )
            if accepted and name.strip():
                section.name = name.strip()
        elif action == stats_action:
            self._show_section_statistics(section)
        elif action == delete_border_action:
            border_ids = {
                item
                for item in [section.left_divider_id, section.right_divider_id]
                if item is not None
            }
            self.dividers = [
                divider for divider in self.dividers if divider.id not in border_ids
            ]
            self.plot.set_dividers(self.dividers)

    def _show_section_statistics(self, section: Section) -> None:
        dataset = self._require_dataset()
        if dataset is None:
            return
        mask_rows = row_indexes_for_section(
            dataset.frame[dataset.time_column].to_numpy(dtype=float), section
        )
        if not len(mask_rows):
            QMessageBox.information(self, "Section Statistics", "The section is empty.")
            return
        lines = [section.name]
        time = dataset.frame[dataset.time_column].iloc[mask_rows]
        for curve in self._visible_curves():
            stats = section_statistics(dataset.frame[curve].iloc[mask_rows], time)
            lines.append("")
            lines.append(curve)
            lines.extend(f"{key}: {value:.8g}" for key, value in stats.items())
        QMessageBox.information(self, "Section Statistics", "\n".join(lines))

    def _write_results_panel(self, results, warnings) -> None:
        lines: list[str] = []
        for result in results:
            lines.append(
                f"{result.curve_name}: {result.integral_value:.10g} "
                f"{result.integral_unit} ({result.point_count} points)"
            )
        if warnings:
            lines.append("")
            lines.append("Warnings")
            lines.extend(f"- {warning.message}" for warning in warnings)
        self.results.setPlainText("\n".join(lines) if lines else "No results.")

    def _show_import_warnings(self, dataset: ImportedDataset) -> None:
        if not dataset.warnings:
            return
        serious = [warning for warning in dataset.warnings if warning.severity != "info"]
        if not serious:
            return
        preview = "\n".join(f"- {warning.message}" for warning in serious[:8])
        if len(serious) > 8:
            preview += f"\n- {len(serious) - 8} additional warnings."
        QMessageBox.warning(self, "Data-Cleaning Warnings", preview)

    def _divider_moved(self, divider_id: str, time_value: float) -> None:
        divider = self._find_divider(divider_id)
        if divider is not None:
            divider.time = time_value

    def _find_divider(self, divider_id: str) -> Divider | None:
        return next((divider for divider in self.dividers if divider.id == divider_id), None)

    def _session_from_state(self) -> ProjectSession:
        session = ProjectSession()
        if self.dataset is not None:
            path = self.dataset.metadata.source_file
            session.loaded_file_paths = [path]
            session.mappings[path] = self.dataset.mapping
            session.units = dict(self.dataset.metadata.units)
        session.dividers = self.dividers
        session.selected_section_id = (
            self.selected_section.id if self.selected_section is not None else None
        )
        session.visible_curves = self._visible_curves()
        session.analysis_settings = AnalysisSettings(
            interpolation_mode=self.interpolation_combo.currentData() or "nearest"
        )
        return session

    def _require_dataset(self) -> ImportedDataset | None:
        if self.dataset is None:
            QMessageBox.information(self, "No Dataset", "Load a CSV file first.")
            return None
        return self.dataset

    def _set_empty_state(self) -> None:
        self.readout.setPlainText("Load a CSV file to begin.")
        self.results.setPlainText("")
