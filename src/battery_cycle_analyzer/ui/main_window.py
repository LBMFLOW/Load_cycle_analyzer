from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QApplication,
)

from battery_cycle_analyzer.core.analysis import AnalysisOptions, AnalysisService
from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.comparison import (
    ComparisonDataset,
    ComparisonResult,
    ComparisonService,
)
from battery_cycle_analyzer.core.csv_loader import CsvLoader
from battery_cycle_analyzer.core.data_model import CurveSpec, Divider, LoadedDataset, Section
from battery_cycle_analyzer.core.derived_metrics import DerivedMetricsService
from battery_cycle_analyzer.core.export import ExportService, SectionExportError
from battery_cycle_analyzer.core.filtering import DataFilterService
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.core.report import AgingReportOptions, AgingReportService
from battery_cycle_analyzer.core.project_state import (
    DatasetProjectState,
    FileSignature,
    ProjectSessionState,
    ProjectStateStore,
)
from battery_cycle_analyzer.core.sections import SectionManager
from battery_cycle_analyzer.ui.advanced_analysis_panel import AdvancedAnalysisPanel
from battery_cycle_analyzer.ui.dialogs import (
    IntegrationRangeDialog,
    IntegrationResultsDialog,
    SectionExportOptionsDialog,
    show_exception,
)
from battery_cycle_analyzer.ui.import_wizard import ImportWizard
from battery_cycle_analyzer.ui.plot_panel import PlotPanel
from battery_cycle_analyzer.ui.results_panel import ResultsPanel
from battery_cycle_analyzer.ui.table_panel import TablePanel
from battery_cycle_analyzer.ui.workers import ProgressTask


class MainWindow(QMainWindow):
    """Main application shell with menus, controls, plot, table, and results."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Battery Cycle Analyzer")
        self.dataset: LoadedDataset | None = None
        self._raw_frame: pd.DataFrame | None = None
        self.comparison_datasets: list[ComparisonDataset] = []
        self.last_comparison_result: ComparisonResult | None = None
        self._derived_metric_cache_key: tuple[object, ...] | None = None
        self.dividers: list[Divider] = []
        self.selected_section: Section | None = None
        self.section_names: dict[str, str] = {}
        self._last_context_divider_id: str | None = None
        self._updating_controls = False
        self._section_manager = SectionManager()
        self._settings = QSettings("Battery Cycle Analyzer", "Battery Cycle Analyzer")

        self.discharge_curve_check = QCheckBox("Discharge energy")
        self.discharge_curve_check.setToolTip("Show or hide discharge energy on the plot.")
        self.discharge_curve_check.setChecked(True)
        self.discharge_curve_check.stateChanged.connect(self._controls_changed)
        self.charge_curve_check = QCheckBox("Charge energy")
        self.charge_curve_check.setToolTip("Show or hide charge energy on the plot.")
        self.charge_curve_check.setChecked(True)
        self.charge_curve_check.stateChanged.connect(self._controls_changed)

        self.x_axis_combo = QComboBox()
        self.x_axis_combo.setToolTip("Choose the x-axis column for plotting and section boundaries.")
        self.x_axis_combo.currentIndexChanged.connect(self._controls_changed)
        self.y_axis_combo = QComboBox()
        self.y_axis_combo.setToolTip("Add one optional numeric curve to the plot.")
        self.y_axis_combo.currentIndexChanged.connect(self._controls_changed)
        self.interpolation_combo = QComboBox()
        self.interpolation_combo.setToolTip("Choose nearest-row lookup or linear interpolation for cursor readout.")
        self.interpolation_combo.addItem("Nearest", "nearest")
        self.interpolation_combo.addItem("Linear", "linear")
        self.interpolation_combo.currentIndexChanged.connect(self._controls_changed)
        self.normalize_time_check = QCheckBox("Normalize time")
        self.normalize_time_check.setToolTip("Display the x-axis relative to the first valid value.")
        self.normalize_time_check.stateChanged.connect(self._controls_changed)

        self.plot_panel = PlotPanel()
        self.plot_panel.cursor_moved.connect(self._cursor_moved)
        self.plot_panel.add_divider_requested.connect(self.add_divider_at_time)
        self.plot_panel.clear_dividers_requested.connect(self.clear_dividers)
        self.plot_panel.export_plot_requested.connect(self.export_plot)
        self.plot_panel.integrate_selected_section_requested.connect(self.integrate_selected_section)
        self.plot_panel.save_selected_section_requested.connect(self.export_selected_section)
        self.plot_panel.copy_cursor_requested.connect(self.copy_cursor_values)
        self.plot_panel.divider_moved.connect(self._divider_moved)
        self.plot_panel.divider_context_requested.connect(self._divider_context_menu)
        self.plot_panel.divider_selected.connect(self._divider_selected)
        self.plot_panel.section_selected.connect(self._section_selected)
        self.plot_panel.section_context_requested.connect(self._section_context_menu)
        self.plot_panel.plot_context_requested.connect(self._plot_context_menu)
        self.table_panel = TablePanel()
        self.results_panel = ResultsPanel()
        self._analysis_task: ProgressTask | None = None
        self.advanced_panel = AdvancedAnalysisPanel()
        self.advanced_panel.apply_metrics_requested.connect(self.add_derived_metrics)
        self.advanced_panel.apply_filter_requested.connect(self.apply_data_filter)
        self.advanced_panel.reset_processed_view_requested.connect(self.reset_processed_view)
        self.advanced_panel.plot_energy_cycle_requested.connect(self.plot_energy_vs_cycle)
        self.advanced_panel.plot_retention_cycle_requested.connect(
            self.plot_retention_vs_cycle
        )
        self.advanced_panel.add_comparison_requested.connect(self.add_current_to_comparison)
        self.advanced_panel.export_comparison_requested.connect(
            self.export_comparison_results
        )
        self.advanced_panel.export_report_requested.connect(self.export_html_report)

        self._build_layout()
        self._build_advanced_dock()
        self._build_menus()
        self._build_shortcuts()
        self.statusBar().showMessage("Ready. Import a CSV file or open a project.")
        self._set_controls_enabled(False)

    def _build_layout(self) -> None:
        controls = QWidget()
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.addWidget(QLabel("Curves"), 0, 0)
        controls_layout.addWidget(self.discharge_curve_check, 0, 1)
        controls_layout.addWidget(self.charge_curve_check, 0, 2)
        controls_layout.addWidget(QLabel("X axis"), 0, 3)
        controls_layout.addWidget(self.x_axis_combo, 0, 4)
        controls_layout.addWidget(QLabel("Y curve"), 0, 5)
        controls_layout.addWidget(self.y_axis_combo, 0, 6)
        controls_layout.addWidget(QLabel("Interpolation"), 0, 7)
        controls_layout.addWidget(self.interpolation_combo, 0, 8)
        controls_layout.addWidget(self.normalize_time_check, 0, 9)
        controls_layout.setColumnStretch(10, 1)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.addWidget(self.table_panel)
        lower.addWidget(self.results_panel)
        lower.setStretchFactor(0, 3)
        lower.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(self.plot_panel)
        main_splitter.addWidget(lower)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)

        self.workspace_widget = QWidget()
        workspace_layout = QVBoxLayout(self.workspace_widget)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.addWidget(controls)
        workspace_layout.addWidget(main_splitter, 1)

        self.start_widget = self._build_start_screen()
        self.central_stack = QStackedWidget()
        self.central_stack.addWidget(self.start_widget)
        self.central_stack.addWidget(self.workspace_widget)
        self.setCentralWidget(self.central_stack)

    def _build_start_screen(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 48, 48, 48)
        title = QLabel("Battery Cycle Analyzer")
        title.setStyleSheet("font-size: 28px; font-weight: 600;")
        subtitle = QLabel(
            "Import cycling CSV data, inspect charge and discharge energy, add dividers, "
            "integrate selected sections, and export analysis results."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 14px; color: #4b5563;")
        workflow = QLabel(
            "Workflow: 1. Import CSV  2. Map time and energy columns  "
            "3. Plot curves  4. Add dividers  5. Integrate and export sections"
        )
        workflow.setWordWrap(True)
        workflow.setStyleSheet("color: #374151;")
        import_button = QPushButton("Import CSV")
        import_button.setToolTip("Start the CSV import wizard.")
        import_button.clicked.connect(self.import_csv)
        open_button = QPushButton("Open Project")
        open_button.setToolTip("Open a saved Battery Cycle Analyzer project.")
        open_button.clicked.connect(self.open_project)
        recent_button = QPushButton("Recent Projects")
        recent_button.setToolTip("Open a recently saved or loaded project.")
        recent_button.clicked.connect(self._show_recent_projects_menu)
        button_row = QHBoxLayout()
        for button in (import_button, open_button, recent_button):
            button.setMinimumHeight(38)
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addLayout(button_row)
        layout.addSpacing(16)
        layout.addWidget(workflow)
        layout.addStretch(2)
        return page

    def _build_advanced_dock(self) -> None:
        self.advanced_dock = QDockWidget("Advanced Analysis", self)
        self.advanced_dock.setWidget(self.advanced_panel)
        self.advanced_dock.setObjectName("advancedAnalysisDock")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.advanced_dock)
        self.advanced_dock.hide()

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("D"), self, activated=self.add_divider_at_cursor)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_last_context_divider)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.plot_panel.move_cursor_by_rows(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.plot_panel.move_cursor_by_rows(1))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self.plot_panel.move_cursor_by_rows(10))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self.plot_panel.move_cursor_by_rows(-10))

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.import_action = file_menu.addAction("Import CSV...", self.import_csv)
        self.import_action.setShortcut(QKeySequence("Ctrl+O"))
        self.import_action.setToolTip("Import a battery cycling CSV file.")
        self.import_comparison_action = file_menu.addAction(
            "Import CSV for Comparison...",
            self.import_comparison_csv,
        )
        self.import_comparison_action.setToolTip("Load another mapped CSV as a comparison dataset.")
        self.open_project_action = file_menu.addAction("Open Project...", self.open_project)
        self.open_project_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.open_project_action.setToolTip("Open a saved project session.")
        self.save_project_action = file_menu.addAction("Save Project...", self.save_project)
        self.save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_project_action.setToolTip("Save the current analysis session.")
        file_menu.addSeparator()
        self.export_section_action = file_menu.addAction(
            "Export Selected Section...",
            self.export_selected_section,
        )
        self.export_section_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_section_action.setToolTip("Export the currently selected section.")
        self.export_plot_action = file_menu.addAction("Export Plot...", self.export_plot)
        self.export_plot_action.setToolTip("Export the current plot image.")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        view_menu = self.menuBar().addMenu("&View")
        table_action = view_menu.addAction("Show Table")
        table_action.setCheckable(True)
        table_action.setChecked(True)
        table_action.toggled.connect(self.table_panel.setVisible)
        results_action = view_menu.addAction("Show Results Panel")
        results_action.setCheckable(True)
        results_action.setChecked(True)
        results_action.toggled.connect(self.results_panel.setVisible)
        advanced_action = self.advanced_dock.toggleViewAction()
        advanced_action.setText("Show Advanced Tools")
        view_menu.addAction(advanced_action)
        view_menu.addAction("Reset Plot View", self.plot_panel.reset_view)

        analysis_menu = self.menuBar().addMenu("&Analysis")
        self.integrate_action = analysis_menu.addAction("Integrate Selected Section", self.integrate_selected_section)
        self.integrate_action.setShortcut(QKeySequence("I"))
        self.integrate_action.setToolTip("Integrate visible curves over the selected section.")
        analysis_menu.addAction("Integrate Range...", self.integrate_all)
        analysis_menu.addAction("Section Statistics", self.section_statistics)
        analysis_menu.addAction("Derived Metrics", self.add_derived_metrics)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("About", self.about)

    def import_csv(self) -> None:
        dialog = ImportWizard(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        dataset = dialog.loaded_dataset
        if dataset is None:
            return
        self.dividers = []
        self.selected_section = None
        self.section_names = {}
        self.set_dataset(dataset)

    def set_dataset(self, dataset: LoadedDataset) -> None:
        self.dataset = dataset
        self._raw_frame = dataset.frame.copy()
        self.central_stack.setCurrentWidget(self.workspace_widget)
        self.table_panel.set_frame(dataset.frame)
        self._populate_controls(dataset)
        self.advanced_panel.configure(dataset)
        self._refresh_plot()
        self.plot_panel.set_dividers(self.dividers)
        self.plot_panel.set_selected_section(self.selected_section)
        self.results_panel.show_issues(dataset.validation_warnings)
        self.statusBar().showMessage(
            f"Loaded {len(dataset.frame):,} rows from {dataset.metadata.source_path.name}."
        )

    def import_comparison_csv(self) -> None:
        dialog = ImportWizard(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        dataset = dialog.loaded_dataset
        if dataset is None:
            return
        default_name = dataset.metadata.source_path.stem
        name, accepted = QInputDialog.getText(
            self,
            "Comparison Dataset Name",
            "Dataset name",
            text=default_name,
        )
        if not accepted:
            return
        self.comparison_datasets.append(
            ComparisonDataset(name.strip() or default_name, dataset)
        )
        self._refresh_comparison_summary()

    def _recent_projects(self) -> list[str]:
        value = self._settings.value("recent_projects", [])
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value] if value else []

    def _add_recent_project(self, path: Path) -> None:
        resolved = str(path.resolve())
        projects = [item for item in self._recent_projects() if item != resolved]
        projects.insert(0, resolved)
        self._settings.setValue("recent_projects", projects[:8])

    def _show_recent_projects_menu(self) -> None:
        menu = QMenu(self)
        projects = self._recent_projects()
        if not projects:
            action = menu.addAction("No recent projects")
            action.setEnabled(False)
        for project in projects:
            action = menu.addAction(Path(project).name)
            action.setToolTip(project)
            action.triggered.connect(lambda _checked=False, project=project: self._open_project_path(Path(project)))
        menu.exec(self.mapToGlobal(self.rect().center()))

    def _open_project_path(self, project_path: Path) -> None:
        if not project_path.exists():
            QMessageBox.warning(self, "Recent Project", f"Project file not found:\n{project_path}")
            return
        self._load_project_path(project_path)

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Project JSON (*.json);;All files (*)"
        )
        if not path:
            return
        self._load_project_path(Path(path))

    def _load_project_path(self, project_path: Path) -> None:
        store = ProjectStateStore()
        try:
            state = store.load(project_path)
            datasets = self._load_project_datasets(state, project_path)
        except Exception as exc:
            show_exception(
                self,
                "Open Project Failed",
                "The project could not be opened.",
                exc,
            )
            return
        if not datasets:
            QMessageBox.warning(self, "Open Project", "The project has no datasets.")
            return

        active_index = min(max(0, state.active_dataset_index), len(datasets) - 1)
        self.dividers = list(state.dividers)
        self.section_names = dict(state.section_names)
        self.comparison_datasets = [
            ComparisonDataset(
                state.datasets[index].name,
                datasets[index],
            )
            for index in state.comparison_dataset_indexes
            if 0 <= index < len(datasets) and index != active_index
        ]
        self.last_comparison_result = None
        self.selected_section = None
        self.set_dataset(datasets[active_index])
        self._restore_ui_state(state.plot_settings)
        self.advanced_panel.restore_state(state.advanced_settings)
        self._restore_selected_section(state.selected_section_id)
        if state.cursor_position is not None:
            self.plot_panel.set_cursor_value(float(state.cursor_position))
        if self.comparison_datasets:
            self._refresh_comparison_summary()
        self._add_recent_project(project_path)
        self.statusBar().showMessage(f"Opened project {project_path.name}.")

    def save_project(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Save Project", "Import a dataset first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "battery_cycle_project.json", "Project JSON (*.json)"
        )
        if not path:
            return
        project_path = Path(path)
        if not self._confirm_overwrite(project_path):
            return
        try:
            state = self._build_project_state(project_path)
            ProjectStateStore().save(state, project_path)
        except Exception as exc:
            show_exception(
                self,
                "Save Project Failed",
                "The project could not be saved.",
                exc,
            )
            return
        self._add_recent_project(project_path)
        self.statusBar().showMessage(f"Saved project {project_path.name}.")
        QMessageBox.information(self, "Save Project", f"Saved project to:\n{project_path}")

    def export_selected_section(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Export Selected Section", "Import a dataset first.")
            return
        if self.selected_section is None:
            QMessageBox.information(
                self, "Export Selected Section", "Select a section on the plot first."
            )
            return

        options_dialog = SectionExportOptionsDialog(self)
        if options_dialog.exec() != options_dialog.DialogCode.Accepted:
            return
        options = options_dialog.options()

        service = ExportService()
        try:
            payload = service.prepare_section_export(
                self.dataset,
                self.selected_section,
                self._visible_curve_columns(),
                options=options,
                axis_values=self.plot_panel.current_axis_values(),
                axis_unit=self._current_axis_unit(),
                dividers=self.dividers,
            )
        except Exception as exc:
            show_exception(
                self,
                "Export Selected Section Failed",
                "The selected section could not be prepared for export.",
                exc,
            )
            return

        if payload.point_count == 0:
            QMessageBox.warning(
                self,
                "Export Selected Section",
                "The selected section is empty. Nothing was exported.",
            )
            return

        if payload.point_count < 2:
            response = QMessageBox.question(
                self,
                "Export Selected Section",
                "The selected section contains fewer than 2 points. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Section",
            str(self._suggest_section_export_path()),
            "CSV files (*.csv)",
        )
        if not path:
            return

        output_path = Path(path)
        if output_path.exists():
            response = QMessageBox.question(
                self,
                "Export Selected Section",
                f"{output_path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        try:
            result = service.write_section_export(payload, output_path, options=options)
        except SectionExportError as exc:
            QMessageBox.warning(self, "Export Selected Section", str(exc))
            return
        except Exception as exc:
            show_exception(
                self,
                "Export Selected Section Failed",
                "The selected section could not be exported.",
                exc,
            )
            return

        warning_text = "\n".join(result.warnings)
        message = f"Exported {result.point_count} rows to:\n{result.output_path}"
        if result.metadata_path is not None:
            message += f"\n\nMetadata:\n{result.metadata_path}"
        if warning_text:
            message += f"\n\nWarnings:\n{warning_text}"
        QMessageBox.information(self, "Export Selected Section", message)

    def _build_project_state(self, project_path: Path) -> ProjectSessionState:
        assert self.dataset is not None
        store = ProjectStateStore()
        datasets: list[LoadedDataset] = [self.dataset]
        names: list[str] = [self.dataset.metadata.source_path.stem]
        for item in self.comparison_datasets:
            if item.dataset is self.dataset:
                continue
            datasets.append(item.dataset)
            names.append(item.name)

        dataset_states = [
            self._dataset_project_state(dataset, name, project_path, store)
            for dataset, name in zip(datasets, names)
        ]
        return ProjectSessionState(
            datasets=dataset_states,
            active_dataset_index=0,
            visible_curves=self._visible_curve_columns(),
            plot_settings=self._ui_state(),
            cursor_position=self.plot_panel.cursor_value(),
            dividers=list(self.dividers),
            selected_section_id=(
                self.selected_section.id if self.selected_section is not None else None
            ),
            section_names=dict(self.section_names),
            annotations=self._annotation_state(),
            advanced_settings=self.advanced_panel.state(),
            comparison_dataset_indexes=list(range(1, len(dataset_states))),
        )

    def _dataset_project_state(
        self,
        dataset: LoadedDataset,
        name: str,
        project_path: Path,
        store: ProjectStateStore,
    ) -> DatasetProjectState:
        if dataset.import_settings is None or dataset.column_mapping is None:
            raise ValueError(
                f"Dataset {name!r} does not include import settings and column mapping metadata."
            )
        source_path = dataset.metadata.source_path
        import_settings = dataset.import_settings.to_dict()
        relative_source = store.relative_path(source_path, project_path.parent)
        import_settings["path"] = relative_source
        return DatasetProjectState(
            name=name,
            source_csv_path=relative_source,
            source_csv_original_path=str(source_path),
            file_signature=FileSignature.from_path(source_path),
            import_settings=import_settings,
            column_mapping=dataset.column_mapping.to_dict(),
            units=dict(dataset.metadata.units),
            labels=dict(dataset.metadata.labels),
            source_columns=dict(dataset.metadata.source_columns),
            roles=dict(dataset.metadata.roles),
            clean_internal_column_names=list(dataset.frame.columns),
            derived_metric_settings=self.advanced_panel.state(),
            filter_settings=self.advanced_panel.state(),
            derived_metrics_applied=self._derived_metrics_applied(dataset),
            filter_applied=(
                dataset is self.dataset
                and self._raw_frame is not None
                and not dataset.frame.equals(self._raw_frame)
            ),
        )

    def _load_project_datasets(
        self,
        state: ProjectSessionState,
        project_path: Path,
    ) -> list[LoadedDataset]:
        store = ProjectStateStore()
        loaded: list[LoadedDataset] = []
        for dataset_state in state.datasets:
            source_path = self._project_source_path(dataset_state, project_path, store)
            if source_path is None:
                return []
            settings_data = dict(dataset_state.import_settings)
            settings_data["path"] = str(source_path)
            settings = ImportSettings.from_dict(settings_data)
            mapping = ColumnMapping.from_dict(dataset_state.column_mapping)
            dataset = CsvLoader().load(settings, mapping)
            self._restore_dataset_metadata(dataset, dataset_state)
            if dataset_state.filter_applied:
                filter_options = self._filter_options_from_state(
                    dataset,
                    dataset_state.filter_settings,
                )
                dataset.frame = DataFilterService().apply(dataset.frame, filter_options).frame
            if dataset_state.derived_metrics_applied:
                self.advanced_panel.configure(dataset)
                self.advanced_panel.restore_state(dataset_state.derived_metric_settings)
                metric_options = self.advanced_panel.metric_options(dataset)
                result = DerivedMetricsService().compute(
                    dataset,
                    metric_options,
                )
                dataset.frame = result.frame
                self._apply_metric_metadata(
                    result.created_columns,
                    metric_options,
                    dataset=dataset,
                )
            loaded.append(dataset)
        return loaded

    def _project_source_path(
        self,
        dataset_state: DatasetProjectState,
        project_path: Path,
        store: ProjectStateStore,
    ) -> Path | None:
        source_path = store.resolve_source_path(dataset_state.source_csv_path, project_path)
        if not source_path.exists():
            source_path = self._relocate_missing_source(dataset_state, project_path, store)
            if source_path is None:
                return None
        if store.source_changed(dataset_state, source_path):
            source_path = self._handle_changed_source(dataset_state, source_path, project_path, store)
        return source_path

    def _relocate_missing_source(
        self,
        dataset_state: DatasetProjectState,
        project_path: Path,
        store: ProjectStateStore,
    ) -> Path | None:
        QMessageBox.warning(
            self,
            "Source CSV Missing",
            f"Could not find:\n{dataset_state.source_csv_path}\n\nChoose the relocated CSV file.",
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate Source CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return None
        source_path = Path(path)
        store.relocate_source(dataset_state, source_path, project_path)
        return source_path

    def _handle_changed_source(
        self,
        dataset_state: DatasetProjectState,
        source_path: Path,
        project_path: Path,
        store: ProjectStateStore,
    ) -> Path | None:
        message = QMessageBox(self)
        message.setWindowTitle("Source CSV Changed")
        message.setText(
            f"The source CSV appears to have changed since this project was saved:\n{source_path}"
        )
        continue_button = message.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
        reload_button = message.addButton(
            "Reload with Current File",
            QMessageBox.ButtonRole.AcceptRole,
        )
        choose_button = message.addButton(
            "Choose Different File",
            QMessageBox.ButtonRole.ActionRole,
        )
        cancel_button = message.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked == cancel_button:
            return None
        if clicked == choose_button:
            relocated = self._relocate_missing_source(dataset_state, project_path, store)
            return relocated
        if clicked in (continue_button, reload_button):
            return source_path
        return None

    def _restore_dataset_metadata(
        self,
        dataset: LoadedDataset,
        state: DatasetProjectState,
    ) -> None:
        dataset.metadata.units.update(state.units)
        dataset.metadata.labels.update(state.labels)
        dataset.metadata.source_columns.update(state.source_columns)
        dataset.metadata.roles.update(state.roles)

    def _filter_options_from_state(self, dataset: LoadedDataset, state: dict[str, object]):
        self.advanced_panel.configure(dataset)
        self.advanced_panel.restore_state(state)
        return self.advanced_panel.filter_options(dataset)

    def _derived_metrics_applied(self, dataset: LoadedDataset) -> bool:
        derived_names = {
            "discharge_energy_retention_pct",
            "charge_energy_retention_pct",
            "energy_efficiency",
            "energy_loss",
            "discharge_percent_energy_fade",
            "charge_percent_energy_fade",
            "discharge_rolling_mean",
            "charge_rolling_mean",
            "discharge_rolling_std",
            "charge_rolling_std",
            "discharge_slope_over_time",
            "charge_slope_over_time",
            "discharge_cycle_delta",
            "charge_cycle_delta",
            "estimated_cycle_index",
        }
        return any(column in dataset.frame for column in derived_names)

    def _annotation_state(self) -> dict[str, object]:
        return {
            "divider_notes": {
                divider.id: divider.note for divider in self.dividers if divider.note
            },
            "section_names": dict(self.section_names),
        }

    def export_plot(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Export Plot", "Import a dataset first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Plot",
            "battery_cycle_plot.png",
            "PNG files (*.png);;SVG files (*.svg)",
        )
        if not path:
            return
        output_path = Path(path)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".png")
        if not self._confirm_overwrite(output_path):
            return
        try:
            self.plot_panel.export_plot(str(output_path))
        except Exception as exc:
            show_exception(
                self,
                "Export Plot Failed",
                "The plot image could not be exported.",
                exc,
            )

    def add_divider_at_time(self, time_value: float) -> None:
        if self.dataset is None:
            return
        self.dividers = self._section_manager.add_divider(self.dividers, time_value)
        self._sync_dividers_to_plot()
        self.statusBar().showMessage(f"Added divider at x={time_value:.8g}.")

    def add_divider_at_cursor(self) -> None:
        value = self.plot_panel.cursor_value()
        if value is not None:
            self.add_divider_at_time(value)

    def clear_dividers(self) -> None:
        if not self.dividers:
            return
        response = QMessageBox.question(
            self,
            "Clear Dividers",
            "Remove all dividers and section boundaries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self.dividers = []
        self._last_context_divider_id = None
        self._clear_section_selection()
        self._sync_dividers_to_plot()
        self.statusBar().showMessage("Cleared all dividers.")

    def integrate_selected_section(self) -> None:
        if self.selected_section is None:
            QMessageBox.information(self, "Integrate Section", "Select a section first.")
            return
        self._integrate_section(self.selected_section)

    def delete_last_context_divider(self) -> None:
        if self._last_context_divider_id is None:
            return
        self.dividers = self._section_manager.remove_divider(
            self.dividers,
            self._last_context_divider_id,
        )
        self._last_context_divider_id = None
        self._sync_dividers_to_plot()
        self._refresh_selected_section_after_divider_change()
        self.statusBar().showMessage("Deleted divider.")

    def copy_cursor_values(self) -> None:
        readout = self.plot_panel.cursor_readout()
        if readout is None:
            return
        lines = [f"row\t{readout.row_index + 1}", f"cursor_x\t{readout.cursor_time:.8g}"]
        for name, value in readout.values.items():
            label = (
                self._display_name(name)
                if self.dataset is not None and name in self.dataset.frame
                else name
            )
            lines.append(f"{label}\t{value}")
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage("Copied cursor values.")

    def _divider_moved(self, divider_id: str, time_value: float) -> None:
        self.dividers = self._section_manager.move_divider(
            self.dividers, divider_id, time_value
        )
        self._last_context_divider_id = divider_id
        self._sync_dividers_to_plot()
        self._refresh_selected_section_after_divider_change()

    def _divider_selected(self, divider_id: str) -> None:
        self._last_context_divider_id = divider_id
        divider = self._divider_by_id(divider_id)
        if divider is not None:
            self.statusBar().showMessage(f"Selected divider {divider.name}.")

    def _divider_context_menu(self, divider_id: str, global_pos) -> None:
        self._last_context_divider_id = divider_id
        menu = QMenu(self)
        rename_action = menu.addAction("Rename divider")
        delete_action = menu.addAction("Delete divider")
        snap_action = menu.addAction("Snap to nearest point")
        note_action = menu.addAction("Add note")
        action = menu.exec(global_pos)
        if action == rename_action:
            self._rename_divider(divider_id)
        elif action == delete_action:
            self.dividers = self._section_manager.remove_divider(self.dividers, divider_id)
            self._sync_dividers_to_plot()
            self._refresh_selected_section_after_divider_change()
        elif action == snap_action:
            axis = self.plot_panel.current_axis_values()
            if axis is not None:
                self.dividers = self._section_manager.snap_divider(
                    self.dividers, divider_id, axis
                )
                self._sync_dividers_to_plot()
                self._refresh_selected_section_after_divider_change()
        elif action == note_action:
            self._note_divider(divider_id)

    def _section_selected(self, section: Section) -> None:
        self._apply_section_name(section)
        self.selected_section = section
        self.plot_panel.set_selected_section(section)
        self.table_panel.highlight_rows(self.plot_panel.row_indexes_for_section(section))
        self._update_section_results(section)

    def _section_context_menu(self, section: Section, global_pos) -> None:
        self._apply_section_name(section)
        target_section = section
        if self.selected_section is None or self.selected_section.id != section.id:
            self._section_selected(section)
        selected_available = target_section is not None
        menu = QMenu(self)
        save_action = menu.addAction("Save data section")
        save_action.setEnabled(selected_available)
        integrate_action = menu.addAction("Integrate data")
        stats_action = menu.addAction("Section statistics")
        stats_action.setEnabled(selected_available)
        rename_action = menu.addAction("Rename section")
        note_action = menu.addAction("Add note")
        rename_action.setEnabled(selected_available)
        note_action.setEnabled(selected_available)
        clear_action = menu.addAction("Clear section selection")
        clear_action.setEnabled(selected_available)
        menu.addSeparator()
        integrate_visible_action = menu.addAction("Integrate visible range")
        reset_zoom_action = menu.addAction("Reset zoom")
        export_plot_action = menu.addAction("Export plot")
        action = menu.exec(global_pos)
        if action == save_action:
            self.export_selected_section()
        elif action == integrate_action:
            if target_section is None:
                self._integrate_with_prompt()
            else:
                self._integrate_section(target_section)
        elif action == stats_action:
            if target_section is not None:
                self._show_section_statistics(target_section)
        elif action == rename_action:
            if target_section is None:
                return
            name, accepted = QInputDialog.getText(
                self, "Rename Section", "Section name", text=target_section.name
            )
            if accepted and name.strip():
                self.section_names[target_section.id] = name.strip()
                target_section.name = name.strip()
                self._section_selected(target_section)
        elif action == note_action:
            if target_section is not None:
                note, accepted = QInputDialog.getMultiLineText(
                    self,
                    "Section Note",
                    target_section.name,
                    target_section.note,
                )
                if accepted:
                    target_section.note = note
                    self._section_selected(target_section)
        elif action == clear_action:
            self._clear_section_selection()
        elif action == integrate_visible_action:
            self._integrate_visible_range()
        elif action == reset_zoom_action:
            self.plot_panel.reset_view()
        elif action == export_plot_action:
            self.export_plot()

    def _plot_context_menu(self, time_value: float, global_pos) -> None:
        menu = QMenu(self)
        integrate_action = menu.addAction("Integrate visible range")
        reset_action = menu.addAction("Reset zoom")
        export_action = menu.addAction("Export plot")
        action = menu.exec(global_pos)
        if action == integrate_action:
            self._integrate_visible_range()
        elif action == reset_action:
            self.plot_panel.reset_view()
        elif action == export_action:
            self.export_plot()

    def _integrate_visible_range(self) -> None:
        if self.dataset is None:
            return
        start, end = self.plot_panel.visible_x_range()
        section = Section(
            id="visible:x-range",
            name="Visible x-range",
            start_time=min(start, end),
            end_time=max(start, end),
            end_inclusive=True,
        )
        options = self._analysis_options_for(section)
        if options is not None:
            self._start_integration_task(section, options)

    def integrate_all(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Integrate All", "Import a dataset first.")
            return
        self._integrate_with_prompt()

    def section_statistics(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Section Statistics", "Import a dataset first.")
            return
        if self.selected_section is None:
            QMessageBox.information(self, "Section Statistics", "Select a section first.")
            return
        self._show_section_statistics(self.selected_section)

    def add_derived_metrics(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Derived Metrics", "Import a dataset first.")
            return
        options = self.advanced_panel.metric_options(self.dataset)
        baseline_section = (
            self.selected_section if options.baseline.mode == "section" else None
        )
        cache_key = self._metric_cache_key(options, baseline_section)
        if cache_key == self._derived_metric_cache_key:
            self.results_panel.text.setPlainText("Derived metrics are already current.")
            return
        dataset = self.dataset
        axis_values = self.plot_panel.current_axis_values()
        self._analysis_task = ProgressTask(
            self,
            "Derived Metrics",
            "Computing derived metrics...",
            lambda *, progress_callback, cancel_token: self._compute_derived_metrics_task(
                dataset,
                options,
                baseline_section,
                axis_values,
                progress_callback,
                cancel_token,
            ),
        )
        signals = self._analysis_task.start()
        signals.finished.connect(
            lambda result, metric_options=options: self._derived_metrics_finished(
                result,
                metric_options,
                cache_key,
            )
        )
        signals.failed.connect(
            lambda exc: self._task_failed(
                "Derived Metrics Failed",
                "Derived metrics could not be computed.",
                exc,
            )
        )
        signals.cancelled.connect(
            lambda: QMessageBox.information(
                self,
                "Derived Metrics",
                "Operation cancelled.",
            )
        )

    def _compute_derived_metrics_task(
        self,
        dataset: LoadedDataset,
        options,
        baseline_section: Section | None,
        axis_values,
        progress_callback,
        cancel_token,
    ):
        progress_callback(5, "Preparing derived metric inputs")
        cancel_token.raise_if_cancelled()
        result = DerivedMetricsService().compute(
            dataset,
            options,
            baseline_section=baseline_section,
            axis_values=axis_values,
        )
        cancel_token.raise_if_cancelled()
        progress_callback(100, "Derived metrics complete")
        return result

    def _derived_metrics_finished(self, result, options, cache_key) -> None:
        self._analysis_task = None
        if self.dataset is None:
            return
        self.dataset.frame = result.frame
        self._derived_metric_cache_key = cache_key
        self._apply_metric_metadata(result.created_columns, options)
        self.table_panel.set_frame(self.dataset.frame)
        self._populate_controls(self.dataset)
        self.advanced_panel.configure(self.dataset)
        self._refresh_plot()
        rows = [[column] for column in result.created_columns]
        self.results_panel.show_table(
            "Derived metrics",
            ["Created column"],
            rows,
            message="\n".join(result.warnings),
        )
        if result.warnings:
            QMessageBox.warning(self, "Derived Metrics", "\n".join(result.warnings))

    def apply_data_filter(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Data Filtering", "Import a dataset first.")
            return
        if self._raw_frame is None:
            self._raw_frame = self.dataset.frame.copy()
        frame = self.dataset.frame
        options = self.advanced_panel.filter_options(self.dataset)
        self._analysis_task = ProgressTask(
            self,
            "Processed View",
            "Applying filters...",
            lambda *, progress_callback, cancel_token: self._filter_task(
                frame,
                options,
                progress_callback,
                cancel_token,
            ),
        )
        signals = self._analysis_task.start()
        signals.finished.connect(self._filter_finished)
        signals.failed.connect(
            lambda exc: self._task_failed(
                "Data Filtering Failed",
                "The processed view could not be created.",
                exc,
            )
        )
        signals.cancelled.connect(
            lambda: QMessageBox.information(
                self,
                "Data Filtering",
                "Operation cancelled.",
            )
        )

    def _filter_task(self, frame, options, progress_callback, cancel_token):
        progress_callback(5, "Preparing filters")
        cancel_token.raise_if_cancelled()
        result = DataFilterService().apply(frame, options)
        cancel_token.raise_if_cancelled()
        progress_callback(100, "Filtering complete")
        return result

    def _filter_finished(self, result) -> None:
        self._analysis_task = None
        if self.dataset is None:
            return
        self.dataset.frame = result.frame
        self._derived_metric_cache_key = None
        self.table_panel.set_frame(self.dataset.frame)
        self._populate_controls(self.dataset)
        self.advanced_panel.configure(self.dataset)
        self._refresh_plot()
        message = "\n".join(result.warnings)
        self.results_panel.show_table(
            "Processed view",
            ["Metric", "Value"],
            [
                ["Rows removed", str(result.removed_rows)],
                ["Rows remaining", str(len(result.frame))],
            ],
            message=message,
        )

    def reset_processed_view(self) -> None:
        if self.dataset is None or self._raw_frame is None:
            return
        self.dataset.frame = self._raw_frame.copy()
        self._derived_metric_cache_key = None
        self.table_panel.set_frame(self.dataset.frame)
        self._populate_controls(self.dataset)
        self.advanced_panel.configure(self.dataset)
        self._refresh_plot()

    def plot_energy_vs_cycle(self) -> None:
        if self.dataset is None:
            return
        self._ensure_cycle_metrics()
        cycle_column = self._cycle_column()
        if cycle_column is None:
            QMessageBox.warning(self, "Cycle Plot", "No cycle index is available.")
            return
        self.x_axis_combo.setCurrentIndex(max(0, self.x_axis_combo.findData(cycle_column)))
        self.normalize_time_check.setChecked(False)
        self._refresh_plot()

    def plot_retention_vs_cycle(self) -> None:
        if self.dataset is None:
            return
        self._ensure_cycle_metrics()
        cycle_column = self._cycle_column()
        retention_column = self._first_available_column(
            ["discharge_energy_retention_pct", "charge_energy_retention_pct"]
        )
        if cycle_column is None or retention_column is None:
            QMessageBox.warning(
                self,
                "Retention Plot",
                "Apply derived metrics first to create cycle and retention columns.",
            )
            return
        self._updating_controls = True
        try:
            self.discharge_curve_check.setChecked(False)
            self.charge_curve_check.setChecked(False)
            self.x_axis_combo.setCurrentIndex(max(0, self.x_axis_combo.findData(cycle_column)))
            self.y_axis_combo.setCurrentIndex(max(0, self.y_axis_combo.findData(retention_column)))
            self.normalize_time_check.setChecked(False)
        finally:
            self._updating_controls = False
        self._refresh_plot()

    def add_current_to_comparison(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Comparison", "Import a dataset first.")
            return
        default_name = self.dataset.metadata.source_path.stem
        name, accepted = QInputDialog.getText(
            self,
            "Comparison Dataset Name",
            "Dataset name",
            text=default_name,
        )
        if not accepted:
            return
        self.comparison_datasets.append(
            ComparisonDataset(name.strip() or default_name, self.dataset)
        )
        self._refresh_comparison_summary()

    def export_comparison_results(self) -> None:
        result = self._comparison_result()
        if result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Comparison Results",
            "battery_comparison_retention.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        output = Path(path)
        if not self._confirm_overwrite(output):
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        result.overlay_frame.to_csv(output, index=False)
        result.summary_frame.to_csv(output.with_suffix(".summary.csv"), index=False)
        QMessageBox.information(
            self,
            "Export Comparison Results",
            f"Exported comparison data to:\n{output}",
        )

    def export_html_report(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "HTML Report", "Import a dataset first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export HTML Report",
            "battery_aging_report.html",
            "HTML files (*.html)",
        )
        if not path:
            return
        if not self._confirm_overwrite(Path(path)):
            return
        stats = []
        if self.selected_section is not None:
            stats = AnalysisService().section_statistics(
                self.dataset,
                self._visible_curve_columns(),
                self.selected_section,
                axis_values=self.plot_panel.current_axis_values(),
                axis_unit=self._current_axis_unit(),
                options=AnalysisOptions(
                    missing_value_policy="drop",
                    time_order_policy="sort",
                    duplicate_time_policy="aggregate",
                ),
                curve_names=self._curve_name_map(),
            )
        comparison = self.last_comparison_result or self._comparison_result(show=False)
        report = AgingReportService().generate_html(
            [self.dataset],
            comparison=comparison,
            section_statistics=stats,
            options=AgingReportOptions(notes=""),
        )
        AgingReportService().write_html(report, Path(path))
        QMessageBox.information(self, "HTML Report", f"Exported report to:\n{path}")

    def about(self) -> None:
        QMessageBox.about(
            self,
            "About Battery Cycle Analyzer",
            "Battery Cycle Analyzer\nPython, PyQt6, PyQtGraph, pandas, NumPy, SciPy",
        )

    def _populate_controls(self, dataset: LoadedDataset) -> None:
        self._updating_controls = True
        try:
            self.x_axis_combo.clear()
            for column in dataset.frame.columns:
                self.x_axis_combo.addItem(self._display_name(column), column)
            self.x_axis_combo.setCurrentIndex(
                max(0, self.x_axis_combo.findData(dataset.time_column))
            )

            self.y_axis_combo.clear()
            self.y_axis_combo.addItem("(none)", None)
            for column in self._numeric_columns(dataset):
                if column != dataset.time_column:
                    self.y_axis_combo.addItem(self._display_name(column), column)
            self.y_axis_combo.setCurrentIndex(0)

            self._set_controls_enabled(True)
            discharge = dataset.discharge_energy_column
            charge = dataset.charge_energy_column
            self.discharge_curve_check.setEnabled(discharge is not None)
            self.charge_curve_check.setEnabled(charge is not None)
            if discharge:
                self.discharge_curve_check.setText(self._display_name(discharge))
                self.discharge_curve_check.setChecked(True)
            if charge:
                self.charge_curve_check.setText(self._display_name(charge))
                self.charge_curve_check.setChecked(True)
        finally:
            self._updating_controls = False

    def _controls_changed(self) -> None:
        if self._updating_controls or self.dataset is None:
            return
        self.plot_panel.set_interpolation_mode(self.interpolation_combo.currentData())
        self._refresh_plot()
        if self.selected_section is not None:
            self._update_section_results(self.selected_section)

    def _refresh_plot(self) -> None:
        if self.dataset is None:
            return
        x_axis = self.x_axis_combo.currentData() or self.dataset.time_column
        self.plot_panel.set_interpolation_mode(self.interpolation_combo.currentData())
        self.plot_panel.set_dataset(
            self.dataset,
            self._visible_curve_specs(),
            x_axis_column=x_axis,
            normalize_x_axis=self.normalize_time_check.isChecked(),
        )

    def _visible_curve_specs(self) -> list[CurveSpec]:
        assert self.dataset is not None
        columns: list[str] = []
        discharge = self.dataset.discharge_energy_column
        charge = self.dataset.charge_energy_column
        if discharge and self.discharge_curve_check.isChecked():
            columns.append(discharge)
        if charge and self.charge_curve_check.isChecked():
            columns.append(charge)
        selected = self.y_axis_combo.currentData()
        if selected and selected not in columns:
            columns.append(selected)

        colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed"]
        return [
            CurveSpec(
                name=self._display_name(column),
                column=column,
                unit=self.dataset.metadata.units.get(column, ""),
                color=colors[index % len(colors)],
            )
            for index, column in enumerate(columns)
        ]

    def _visible_curve_columns(self) -> list[str]:
        return [curve.column for curve in self._visible_curve_specs()]

    def _curve_name_map(self) -> dict[str, str]:
        return {column: self._display_name(column) for column in self._visible_curve_columns()}

    def _metric_cache_key(self, options, baseline_section: Section | None) -> tuple[object, ...]:
        assert self.dataset is not None
        frame = self.dataset.frame
        return (
            id(frame),
            len(frame),
            tuple(frame.columns),
            repr(options),
            baseline_section.id if baseline_section else None,
        )

    def _ensure_cycle_metrics(self) -> None:
        if self.dataset is None:
            return
        if self._cycle_column() is None or (
            "discharge_energy_retention_pct" not in self.dataset.frame
            and "charge_energy_retention_pct" not in self.dataset.frame
        ):
            self.add_derived_metrics()

    def _cycle_column(self) -> str | None:
        if self.dataset is None:
            return None
        selected = self.advanced_panel.cycle_column_combo.currentData()
        if selected and selected in self.dataset.frame:
            return selected
        if "estimated_cycle_index" in self.dataset.frame:
            return "estimated_cycle_index"
        for column in self.dataset.frame.columns:
            if "cycle" in str(column).casefold():
                return str(column)
        return None

    def _first_available_column(self, columns: list[str]) -> str | None:
        if self.dataset is None:
            return None
        for column in columns:
            if column in self.dataset.frame:
                return column
        return None

    def _comparison_result(self, *, show: bool = True) -> ComparisonResult | None:
        datasets = list(self.comparison_datasets)
        if self.dataset is not None and not datasets:
            datasets.append(
                ComparisonDataset(self.dataset.metadata.source_path.stem, self.dataset)
            )
        if not datasets:
            QMessageBox.information(self, "Comparison", "Add at least one dataset first.")
            return None
        result = ComparisonService().compare_discharge_retention(datasets)
        self.last_comparison_result = result
        if show:
            self._show_comparison_result(result)
        return result

    def _refresh_comparison_summary(self) -> None:
        self._comparison_result(show=True)

    def _show_comparison_result(self, result: ComparisonResult) -> None:
        rows = [
            [str(value) for value in row]
            for row in result.summary_frame.fillna("").itertuples(index=False, name=None)
        ]
        self.results_panel.show_table(
            "Comparison summary",
            [str(column) for column in result.summary_frame.columns],
            rows,
            message="\n".join(result.warnings),
        )
        self.plot_panel.plot_comparison_overlay(result.overlay_frame)

    def _apply_metric_metadata(
        self,
        created_columns: list[str],
        options,
        *,
        dataset: LoadedDataset | None = None,
    ) -> None:
        target = dataset or self.dataset
        if target is None:
            return
        time_unit = target.metadata.units.get(options.time_column or target.time_column, "")
        unit_by_prefix = {
            "discharge": target.metadata.units.get(options.discharge_column or "", ""),
            "charge": target.metadata.units.get(options.charge_column or "", ""),
        }
        labels = {
            "estimated_cycle_index": "Estimated Cycle Index",
            "discharge_energy_retention_pct": "Discharge Energy Retention",
            "charge_energy_retention_pct": "Charge Energy Retention",
            "discharge_percent_energy_fade": "Discharge Percent Energy Fade",
            "charge_percent_energy_fade": "Charge Percent Energy Fade",
            "energy_efficiency": "Energy Efficiency",
            "energy_loss": "Energy Loss",
            "discharge_rolling_mean": "Discharge Rolling Mean",
            "charge_rolling_mean": "Charge Rolling Mean",
            "discharge_rolling_std": "Discharge Rolling Standard Deviation",
            "charge_rolling_std": "Charge Rolling Standard Deviation",
            "discharge_slope_over_time": "Discharge Slope Over Time",
            "charge_slope_over_time": "Charge Slope Over Time",
            "discharge_cycle_delta": "Discharge Cycle Delta",
            "charge_cycle_delta": "Charge Cycle Delta",
        }
        for column in created_columns:
            target.metadata.labels[column] = labels.get(
                column,
                column.replace("_", " ").title(),
            )
            if "retention_pct" in column or "percent_energy_fade" in column:
                target.metadata.units[column] = "%"
            elif column == "energy_efficiency":
                target.metadata.units[column] = "ratio"
            elif column == "energy_loss":
                target.metadata.units[column] = unit_by_prefix.get("charge", "")
            elif column == "estimated_cycle_index":
                target.metadata.units[column] = "cycle"
            elif column.startswith("discharge_"):
                source_unit = unit_by_prefix.get("discharge", "")
                target.metadata.units[column] = (
                    f"{source_unit}/{time_unit}" if "slope_over_time" in column and time_unit else source_unit
                )
            elif column.startswith("charge_"):
                source_unit = unit_by_prefix.get("charge", "")
                target.metadata.units[column] = (
                    f"{source_unit}/{time_unit}" if "slope_over_time" in column and time_unit else source_unit
                )

    def _cursor_moved(self, value: float, row: int) -> None:
        if row < 0:
            return
        self.table_panel.select_row(row)
        readout = self.plot_panel.cursor_readout()
        if readout is not None:
            values = {
                self._display_name(name) if self.dataset is not None and name in self.dataset.frame else name: value
                for name, value in readout.values.items()
            }
            self.results_panel.show_cursor_readout(
                row=readout.row_index,
                cursor_value=readout.cursor_time,
                values=values,
            )

    def _sync_dividers_to_plot(self) -> None:
        self.dividers = self._section_manager.sorted_dividers(self.dividers)
        self.plot_panel.set_dividers(self.dividers)

    def _rename_divider(self, divider_id: str) -> None:
        divider = self._divider_by_id(divider_id)
        if divider is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename Divider", "Divider name", text=divider.name
        )
        if accepted and name.strip():
            self.dividers = self._section_manager.rename_divider(
                self.dividers, divider_id, name.strip()
            )
            self._sync_dividers_to_plot()

    def _note_divider(self, divider_id: str) -> None:
        divider = self._divider_by_id(divider_id)
        if divider is None:
            return
        note, accepted = QInputDialog.getMultiLineText(
            self, "Divider Note", divider.name, divider.note
        )
        if accepted:
            self.dividers = self._section_manager.note_divider(
                self.dividers, divider_id, note
            )
            self._sync_dividers_to_plot()

    def _divider_by_id(self, divider_id: str) -> Divider | None:
        return next((divider for divider in self.dividers if divider.id == divider_id), None)

    def _refresh_selected_section_after_divider_change(self) -> None:
        if self.selected_section is None:
            self.table_panel.highlight_rows([])
            self.plot_panel.set_selected_section(None)
            return
        matching = next(
            (
                section
                for section in self.plot_panel.controller.current_sections()
                if section.id == self.selected_section.id
            ),
            None,
        )
        if matching is None:
            self._clear_section_selection()
            return
        self._section_selected(matching)

    def _apply_section_name(self, section: Section) -> None:
        if section.id in self.section_names:
            section.name = self.section_names[section.id]

    def _restore_selected_section(self, section_id: str | None) -> None:
        if section_id is None:
            self._clear_section_selection()
            return
        section = next(
            (
                candidate
                for candidate in self.plot_panel.controller.current_sections()
                if candidate.id == section_id
            ),
            None,
        )
        if section is not None:
            self._section_selected(section)

    def _clear_section_selection(self) -> None:
        self.selected_section = None
        self.plot_panel.set_selected_section(None)
        self.table_panel.highlight_rows([])

    def _integrate_section(self, section: Section) -> None:
        if self.dataset is None:
            return
        options = self._analysis_options_for(section)
        if options is None:
            return
        self._start_integration_task(section, options)

    def _integrate_with_prompt(self) -> None:
        if self.dataset is None:
            return
        if self.selected_section is not None:
            self._integrate_section(self.selected_section)
            return

        dialog = IntegrationRangeDialog(
            self,
            visible_range=self.plot_panel.visible_x_range(),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        mode, start, end = dialog.range_selection()
        section: Section | None
        if mode == "whole":
            section = None
        else:
            lower = min(start, end)
            upper = max(start, end)
            if lower == upper:
                QMessageBox.warning(
                    self,
                    "Integrate Data",
                    "The selected integration range has zero width.",
                )
                return
            section = Section(
                id=f"integration:{mode}",
                name="Visible x-range" if mode == "visible" else "Manual range",
                start_time=lower,
                end_time=upper,
                end_inclusive=True,
            )
        options = self._analysis_options_for(section)
        if options is None:
            return
        self._start_integration_task(section, options)

    def _start_integration_task(self, section: Section | None, options: AnalysisOptions) -> None:
        if self.dataset is None:
            return
        dataset = self.dataset
        columns = self._visible_curve_columns()
        axis_values = self.plot_panel.current_axis_values()
        axis_unit = self._current_axis_unit()
        curve_names = self._curve_name_map()
        self._analysis_task = ProgressTask(
            self,
            "Integrate Data",
            "Integrating visible curves...",
            lambda *, progress_callback, cancel_token: self._integration_task(
                dataset,
                columns,
                section,
                axis_values,
                axis_unit,
                options,
                curve_names,
                progress_callback,
                cancel_token,
            ),
        )
        signals = self._analysis_task.start()
        signals.finished.connect(self._integration_finished)
        signals.failed.connect(
            lambda exc: self._task_failed(
                "Integration Failed",
                "Integration could not be completed.",
                exc,
            )
        )
        signals.cancelled.connect(
            lambda: QMessageBox.information(self, "Integrate Data", "Operation cancelled.")
        )

    def _integration_task(
        self,
        dataset,
        columns,
        section,
        axis_values,
        axis_unit,
        options,
        curve_names,
        progress_callback,
        cancel_token,
    ):
        progress_callback(5, "Preparing integration")
        cancel_token.raise_if_cancelled()
        results = AnalysisService().integrate(
            dataset,
            columns,
            section,
            axis_values=axis_values,
            axis_unit=axis_unit,
            options=options,
            curve_names=curve_names,
        )
        cancel_token.raise_if_cancelled()
        progress_callback(100, "Integration complete")
        return results

    def _integration_finished(self, results) -> None:
        self._analysis_task = None
        self._show_integration_results(results)

    def _show_section_statistics(self, section: Section) -> None:
        if self.dataset is None:
            return
        rows = self.plot_panel.row_indexes_for_section(section)
        if not rows:
            self.results_panel.text.setPlainText("Selected section has no rows.")
            return
        self._update_section_results(section)

    def _update_section_results(self, section: Section) -> None:
        if self.dataset is None:
            return
        stats = AnalysisService().section_statistics(
            self.dataset,
            self._visible_curve_columns(),
            section,
            axis_values=self.plot_panel.current_axis_values(),
            axis_unit=self._current_axis_unit(),
            options=AnalysisOptions(
                missing_value_policy="drop",
                time_order_policy="sort",
                duplicate_time_policy="aggregate",
            ),
            curve_names=self._curve_name_map(),
        )
        self.results_panel.show_section_statistics(
            section.name,
            stats,
            start_time=section.start_time,
            end_time=section.end_time,
        )

    def _analysis_options_for(self, section: Section | None) -> AnalysisOptions | None:
        if self.dataset is None:
            return None
        service = AnalysisService()
        diagnostics = service.selection_diagnostics(
            self.dataset,
            self._visible_curve_columns(),
            section,
            axis_values=self.plot_panel.current_axis_values(),
        )
        time_order_policy = "continue"
        duplicate_time_policy = "continue"
        missing_value_policy = "drop"

        if diagnostics.time_not_monotonic:
            response = QMessageBox.question(
                self,
                "Integrate Data",
                "Time values are not monotonic in the selected range. Sort by time before analysis?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            time_order_policy = "sort" if response == QMessageBox.StandardButton.Yes else "continue"

        if diagnostics.duplicate_timestamps:
            choice, accepted = QInputDialog.getItem(
                self,
                "Duplicate Timestamps",
                "Duplicate timestamps are present. Choose how to handle them.",
                [
                    "Aggregate duplicates by mean",
                    "Keep first duplicate",
                    "Keep last duplicate",
                    "Continue without changes",
                ],
                0,
                False,
            )
            if not accepted:
                return None
            duplicate_time_policy = {
                "Aggregate duplicates by mean": "aggregate",
                "Keep first duplicate": "keep_first",
                "Keep last duplicate": "keep_last",
                "Continue without changes": "continue",
            }[choice]

        if diagnostics.missing_values:
            choice, accepted = QInputDialog.getItem(
                self,
                "Missing Values",
                "Missing values are present in the selected range. Choose how to handle them.",
                ["Drop rows with NaN", "Interpolate missing values", "Cancel"],
                0,
                False,
            )
            if not accepted or choice == "Cancel":
                return None
            missing_value_policy = {
                "Drop rows with NaN": "drop",
                "Interpolate missing values": "interpolate",
            }[choice]

        return AnalysisOptions(
            missing_value_policy=missing_value_policy,
            time_order_policy=time_order_policy,
            duplicate_time_policy=duplicate_time_policy,
        )

    def _show_integration_results(self, results) -> None:
        if not results:
            QMessageBox.warning(
                self,
                "Integrate Data",
                "Fewer than 2 valid points are available for the visible curves.",
            )
            self.results_panel.show_integration_results([])
            return
        self.results_panel.show_integration_results(results)
        IntegrationResultsDialog(results, self).exec()

    def _task_failed(self, title: str, message: str, exc: object) -> None:
        self._analysis_task = None
        if isinstance(exc, BaseException):
            show_exception(self, title, message, exc)
        else:
            QMessageBox.critical(self, title, str(exc))

    def _ui_state(self) -> dict[str, object]:
        return {
            "x_axis": self.x_axis_combo.currentData(),
            "y_axis": self.y_axis_combo.currentData(),
            "show_discharge": self.discharge_curve_check.isChecked(),
            "show_charge": self.charge_curve_check.isChecked(),
            "interpolation": self.interpolation_combo.currentData(),
            "normalize_time": self.normalize_time_check.isChecked(),
        }

    def _restore_ui_state(self, state: dict[str, object]) -> None:
        self._updating_controls = True
        try:
            self.x_axis_combo.setCurrentIndex(
                max(0, self.x_axis_combo.findData(state.get("x_axis")))
            )
            self.y_axis_combo.setCurrentIndex(
                max(0, self.y_axis_combo.findData(state.get("y_axis")))
            )
            self.discharge_curve_check.setChecked(bool(state.get("show_discharge", True)))
            self.charge_curve_check.setChecked(bool(state.get("show_charge", True)))
            self.interpolation_combo.setCurrentIndex(
                max(0, self.interpolation_combo.findData(state.get("interpolation", "nearest")))
            )
            self.normalize_time_check.setChecked(bool(state.get("normalize_time", False)))
        finally:
            self._updating_controls = False
        self._refresh_plot()

    def _numeric_columns(self, dataset: LoadedDataset) -> list[str]:
        return [
            column
            for column in dataset.frame.columns
            if pd.api.types.is_numeric_dtype(dataset.frame[column])
        ]

    def _display_name(self, column: str) -> str:
        assert self.dataset is not None
        label = self.dataset.metadata.labels.get(column, column)
        unit = self.dataset.metadata.units.get(column, "")
        return f"{label} [{unit}]" if unit else label

    def _current_axis_unit(self) -> str:
        if self.dataset is None:
            return ""
        axis_column = self.x_axis_combo.currentData() or self.dataset.time_column
        return self.dataset.metadata.units.get(axis_column, "")

    def _suggest_section_export_path(self) -> Path:
        assert self.dataset is not None
        assert self.selected_section is not None
        source = self.dataset.metadata.source_path
        stem = self._safe_filename_part(source.stem) or "battery_cycle_data"
        section = self._safe_filename_part(self.selected_section.name) or "section"
        return source.parent / f"{stem}_{section}.csv"

    def _safe_filename_part(self, value: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
        return cleaned or "section"

    def _confirm_overwrite(self, path: Path) -> bool:
        if not path.exists():
            return True
        response = QMessageBox.question(
            self,
            "Confirm Overwrite",
            f"{path.name} already exists. Replace it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.discharge_curve_check,
            self.charge_curve_check,
            self.x_axis_combo,
            self.y_axis_combo,
            self.interpolation_combo,
            self.normalize_time_check,
        ):
            widget.setEnabled(enabled)
