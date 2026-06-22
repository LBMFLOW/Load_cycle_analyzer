from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.csv_loader import CsvLoader, CsvPreview
from battery_cycle_analyzer.core.data_model import LoadedDataset, ValidationIssue
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.ui.dialogs import show_exception
from battery_cycle_analyzer.ui.workers import ProgressTask


class ImportWizard(QDialog):
    """CSV import wizard with preview, row selection, mapping, and validation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self.resize(1100, 780)
        self._loader = CsvLoader()
        self._preview: CsvPreview | None = None
        self._dataset: LoadedDataset | None = None
        self._import_task: ProgressTask | None = None

        self.path_edit = QLineEdit()
        self.path_edit.editingFinished.connect(self.reload_preview)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        self.delimiter = QComboBox()
        self.delimiter.addItem("Comma (,)", ",")
        self.delimiter.addItem("Semicolon (;)", ";")
        self.delimiter.addItem("Tab", "\t")
        self.delimiter.addItem("Space", " ")
        self.delimiter.addItem("Custom", None)
        self.delimiter.currentIndexChanged.connect(self._delimiter_changed)

        self.custom_delimiter = QLineEdit()
        self.custom_delimiter.setMaxLength(1)
        self.custom_delimiter.setEnabled(False)
        self.custom_delimiter.textChanged.connect(lambda _text: self.reload_preview())

        self.decimal_separator = QComboBox()
        self.decimal_separator.addItem("Dot (.)", ".")
        self.decimal_separator.addItem("Comma (,)", ",")
        self.decimal_separator.currentIndexChanged.connect(self._rows_or_labels_changed)

        self.encoding = QComboBox()
        self.encoding.setEditable(True)
        self.encoding.addItems(["utf-8", "utf-8-sig", "cp1252", "latin-1"])
        self.encoding.currentTextChanged.connect(lambda _text: self.reload_preview())

        self.label_row = _optional_row_spin(1)
        self.unit_row = _optional_row_spin(2)
        self.first_data_row = _required_row_spin(3)
        for spin in (self.label_row, self.unit_row, self.first_data_row):
            spin.valueChanged.connect(self._rows_or_labels_changed)

        self.time_column = QComboBox()
        self.discharge_column = QComboBox()
        self.charge_column = QComboBox()
        self.additional_columns = QListWidget()
        self.additional_columns.setAlternatingRowColors(True)

        self.auto_detect_numeric = QCheckBox("Auto-detect numeric columns")
        self.auto_detect_numeric.setChecked(True)
        self.auto_detect_numeric.stateChanged.connect(self._auto_detect_if_enabled)
        self.treat_missing = QCheckBox("Treat blanks and common missing markers as NaN")
        self.treat_missing.setChecked(True)
        self.treat_missing.stateChanged.connect(self._rows_or_labels_changed)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)

        self.validation_text = QPlainTextEdit()
        self.validation_text.setReadOnly(True)
        self.validation_text.setMaximumHeight(110)

        reload_button = QPushButton("Reload Preview")
        reload_button.clicked.connect(self.reload_preview)

        file_form = QFormLayout()
        file_form.addRow("CSV file", path_row)
        file_form.addRow("Delimiter", self.delimiter)
        file_form.addRow("Custom delimiter", self.custom_delimiter)
        file_form.addRow("Decimal separator", self.decimal_separator)
        file_form.addRow("Encoding", self.encoding)
        file_form.addRow(reload_button)

        row_form = QFormLayout()
        row_form.addRow("Parameter-label row", self.label_row)
        row_form.addRow("Unit row", self.unit_row)
        row_form.addRow("First data row", self.first_data_row)
        row_form.addRow(self.treat_missing)

        mapping = QFormLayout()
        mapping.addRow("Time column", self.time_column)
        mapping.addRow("Discharge energy column", self.discharge_column)
        mapping.addRow("Charge energy column", self.charge_column)
        mapping.addRow(self.auto_detect_numeric)
        mapping.addRow(QLabel("Additional columns"), self.additional_columns)

        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        file_layout.addWidget(QLabel("Step 1: choose the source CSV and parser settings."))
        file_layout.addLayout(file_form)
        file_layout.addStretch(1)

        rows_tab = QWidget()
        rows_layout = QVBoxLayout(rows_tab)
        rows_layout.addWidget(
            QLabel("Step 2: identify the rows containing labels, units, and data.")
        )
        rows_layout.addLayout(row_form)
        rows_layout.addWidget(QLabel("Preview: highlighted label, unit, and first-data rows"))
        rows_layout.addWidget(self.preview_table, 1)

        mapping_tab = QWidget()
        mapping_layout = QVBoxLayout(mapping_tab)
        mapping_layout.addWidget(
            QLabel("Step 3: map battery cycling columns used for plotting and analysis.")
        )
        mapping_layout.addLayout(mapping)

        validation_tab = QWidget()
        validation_layout = QVBoxLayout(validation_tab)
        validation_layout.addWidget(QLabel("Step 4: review import validation messages."))
        validation_layout.addWidget(self.validation_text, 1)

        self.steps = QTabWidget()
        self.steps.addTab(file_tab, "1. File")
        self.steps.addTab(rows_tab, "2. Rows")
        self.steps.addTab(mapping_tab, "3. Columns")
        self.steps.addTab(validation_tab, "4. Validation")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_import)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.steps)
        layout.addWidget(buttons)

    @property
    def loaded_dataset(self) -> LoadedDataset | None:
        return self._dataset

    def settings(self) -> ImportSettings:
        return ImportSettings(
            path=Path(self.path_edit.text()) if self.path_edit.text().strip() else None,
            delimiter=self._current_delimiter(),
            decimal_separator=self.decimal_separator.currentData(),
            encoding=self.encoding.currentText(),
            label_row=_optional_row_value(self.label_row),
            unit_row=_optional_row_value(self.unit_row),
            first_data_row=self.first_data_row.value() - 1,
            auto_detect_numeric_columns=self.auto_detect_numeric.isChecked(),
            treat_missing_markers_as_nan=self.treat_missing.isChecked(),
        )

    def mapping(self) -> ColumnMapping:
        return ColumnMapping(
            time=self.time_column.currentData(),
            discharge_energy=self.discharge_column.currentData(),
            charge_energy=self.charge_column.currentData(),
            additional=self._selected_additional_indexes(),
        )

    def reload_preview(self) -> None:
        if not self.path_edit.text().strip():
            return
        try:
            self._preview = self._loader.preview(self.settings())
        except Exception as exc:
            self.validation_text.setPlainText(f"Preview failed: {exc}")
            return
        self._fill_preview_table()
        self._update_column_choices()
        self._auto_detect_if_enabled()
        self.validation_text.setPlainText("")

    def _delimiter_changed(self) -> None:
        self.custom_delimiter.setEnabled(self.delimiter.currentData() is None)
        self.reload_preview()

    def _rows_or_labels_changed(self) -> None:
        self.reload_preview()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self.path_edit.setText(path)
            self.reload_preview()

    def _accept_import(self) -> None:
        settings = self.settings()
        mapping = self.mapping()
        self._import_task = ProgressTask(
            self,
            "Import CSV",
            "Reading CSV data...",
            lambda *, progress_callback, cancel_token: self._loader.load(
                settings,
                mapping,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
            ),
        )
        signals = self._import_task.start()
        signals.finished.connect(self._import_finished)
        signals.failed.connect(self._import_failed)
        signals.cancelled.connect(self._import_cancelled)

    def _import_finished(self, dataset: LoadedDataset) -> None:
        self._import_task = None
        fatal = [issue for issue in dataset.validation_warnings if issue.is_fatal]
        self._show_validation(dataset.validation_warnings)
        if fatal:
            QMessageBox.critical(
                self,
                "Import Validation Failed",
                self._issues_to_text(fatal),
            )
            return

        warnings = [
            issue for issue in dataset.validation_warnings if issue.severity != "info"
        ]
        if warnings:
            choice = QMessageBox.warning(
                self,
                "Import Warnings",
                self._issues_to_text(warnings)
                + "\n\nImport anyway?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if choice != QMessageBox.StandardButton.Ok:
                return

        self._dataset = dataset
        self.accept()

    def _import_failed(self, exc: object) -> None:
        self._import_task = None
        if isinstance(exc, BaseException):
            show_exception(
                self,
                "Import Failed",
                "The CSV file could not be imported. Check the selected file, encoding, delimiter, and column mapping.",
                exc,
            )
        else:
            QMessageBox.critical(self, "Import Failed", str(exc))

    def _import_cancelled(self) -> None:
        self._import_task = None
        QMessageBox.information(self, "Import CSV", "Import cancelled.")

    def _current_delimiter(self) -> str:
        data = self.delimiter.currentData()
        if data is not None:
            return str(data)
        custom = self.custom_delimiter.text()
        return custom if custom else ","

    def _fill_preview_table(self) -> None:
        preview = self._preview
        if preview is None:
            return
        self.preview_table.clear()
        self.preview_table.setRowCount(len(preview.rows))
        self.preview_table.setColumnCount(preview.column_count)
        self.preview_table.setHorizontalHeaderLabels(
            [f"{index + 1}: {preview.display_label(index)}" for index in range(preview.column_count)]
        )
        self.preview_table.setVerticalHeaderLabels(
            [str(index + 1) for index in range(len(preview.rows))]
        )
        for row_index, row in enumerate(preview.rows):
            for column_index in range(preview.column_count):
                value = row[column_index] if column_index < len(row) else ""
                item = QTableWidgetItem(value)
                background = self._row_background(row_index)
                if background is not None:
                    item.setBackground(background)
                self.preview_table.setItem(row_index, column_index, item)
        self.preview_table.resizeColumnsToContents()

    def _row_background(self, zero_based_row: int) -> QColor | None:
        label_row = _optional_row_value(self.label_row)
        unit_row = _optional_row_value(self.unit_row)
        first_data = self.first_data_row.value() - 1
        if zero_based_row == label_row:
            return QColor("#dbeafe")
        if zero_based_row == unit_row:
            return QColor("#dcfce7")
        if zero_based_row == first_data:
            return QColor("#fff2b8")
        return None

    def _update_column_choices(self) -> None:
        preview = self._preview
        if preview is None:
            return
        current = {
            "time": self.time_column.currentData(),
            "discharge": self.discharge_column.currentData(),
            "charge": self.charge_column.currentData(),
            "additional": set(self._selected_additional_indexes()),
        }
        for combo in (self.time_column, self.discharge_column, self.charge_column):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(not selected)", None)
            for index in range(preview.column_count):
                combo.addItem(self._column_display(index), index)
            combo.blockSignals(False)
        self._restore_combo(self.time_column, current["time"])
        self._restore_combo(self.discharge_column, current["discharge"])
        self._restore_combo(self.charge_column, current["charge"])

        self.additional_columns.clear()
        for index in range(preview.column_count):
            item = QListWidgetItem(self._column_display(index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if index in current["additional"]
                else Qt.CheckState.Unchecked
            )
            self.additional_columns.addItem(item)

    def _auto_detect_if_enabled(self) -> None:
        if self._preview is None or not self.auto_detect_numeric.isChecked():
            return
        try:
            numeric = set(self._loader.likely_numeric_columns(self.settings()))
        except Exception:
            return

        self._guess_role(self.time_column, ("time", "timestamp", "date", "zeit"))
        self._guess_role(
            self.discharge_column,
            ("discharge", "entlade", "dis_energy", "discharge_energy"),
        )
        self._guess_role(
            self.charge_column,
            ("charge", "lade", "chg_energy", "charge_energy"),
        )

        role_columns = {
            self.time_column.currentData(),
            self.discharge_column.currentData(),
            self.charge_column.currentData(),
        }
        for index in range(self.additional_columns.count()):
            item = self.additional_columns.item(index)
            column_index = int(item.data(Qt.ItemDataRole.UserRole))
            item.setCheckState(
                Qt.CheckState.Checked
                if column_index in numeric and column_index not in role_columns
                else Qt.CheckState.Unchecked
            )

    def _guess_role(self, combo: QComboBox, needles: tuple[str, ...]) -> None:
        if combo.currentData() is not None or self._preview is None:
            return
        for index, label in self._preview.labels.items():
            normalized = label.lower().replace(" ", "_")
            if any(needle in normalized for needle in needles):
                self._restore_combo(combo, index)
                return

    def _selected_additional_indexes(self) -> list[int]:
        indexes: list[int] = []
        for row in range(self.additional_columns.count()):
            item = self.additional_columns.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                indexes.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return indexes

    def _column_display(self, column_index: int) -> str:
        assert self._preview is not None
        return f"{column_index + 1}: {self._preview.display_label(column_index)}"

    def _restore_combo(self, combo: QComboBox, value: object) -> None:
        combo.setCurrentIndex(max(0, combo.findData(value)))

    def _show_validation(self, issues: list[ValidationIssue]) -> None:
        self.validation_text.setPlainText(
            self._issues_to_text(issues) if issues else "No validation warnings. Ready to import."
        )

    def _issues_to_text(self, issues: list[ValidationIssue]) -> str:
        return "\n".join(
            f"{issue.severity.upper()}: {issue.message}" for issue in issues
        )


def _optional_row_spin(default: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, 1_000_000)
    spin.setSpecialValueText("None")
    spin.setValue(default)
    return spin


def _required_row_spin(default: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 1_000_000)
    spin.setValue(default)
    return spin


def _optional_row_value(spin: QSpinBox) -> int | None:
    return None if spin.value() == 0 else spin.value() - 1
