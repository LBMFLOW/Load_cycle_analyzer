from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from battery_cycle_analyzer.core.data_model import IntegrationResult
from battery_cycle_analyzer.core.export import SectionExportOptions


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def show_exception(
    parent: QWidget | None,
    title: str,
    message: str,
    exc: BaseException,
) -> None:
    logging.getLogger(__name__).error(
        "%s: %s",
        title,
        message,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setWindowTitle(title)
    dialog.setText(message)
    detail = getattr(exc, "detail", None) or "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    dialog.setDetailedText(str(detail))
    dialog.exec()


class SectionExportOptionsDialog(QDialog):
    """Collect options for saving a selected data section."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Data Section Options")

        self.include_all_columns_check = QCheckBox("Include all imported columns")
        self.visible_curves_check = QCheckBox("Include only visible curves")
        self.visible_curves_check.setChecked(True)
        self.metadata_comments_check = QCheckBox("Include metadata comments")
        self.metadata_comments_check.setChecked(True)
        self.sidecar_json_check = QCheckBox("Create sidecar JSON metadata file")
        self.sidecar_json_check.setChecked(True)

        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItem("seconds", "seconds")
        self.time_unit_combo.addItem("minutes", "minutes")
        self.time_unit_combo.addItem("hours", "hours")
        self.time_unit_combo.addItem("days", "days")

        self.include_all_columns_check.toggled.connect(self._all_columns_toggled)

        form = QFormLayout()
        form.addRow("Relative time unit", self.time_unit_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.include_all_columns_check)
        layout.addWidget(self.visible_curves_check)
        layout.addWidget(self.metadata_comments_check)
        layout.addWidget(self.sidecar_json_check)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> SectionExportOptions:
        return SectionExportOptions(
            include_all_columns=self.include_all_columns_check.isChecked(),
            include_visible_curves=self.visible_curves_check.isChecked(),
            include_metadata_comments=self.metadata_comments_check.isChecked(),
            create_sidecar_json=self.sidecar_json_check.isChecked(),
            relative_time_unit=self.time_unit_combo.currentData(),
        )

    def _all_columns_toggled(self, checked: bool) -> None:
        self.visible_curves_check.setEnabled(not checked)


class IntegrationRangeDialog(QDialog):
    """Choose what x-range to integrate when no section is selected."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        visible_range: tuple[float, float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Integrate Data")
        start, end = visible_range or (0.0, 0.0)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Whole dataset", "whole")
        self.mode_combo.addItem("Visible x-range", "visible")
        self.mode_combo.addItem("Manual start/end time", "manual")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)

        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(8)
        self.start_spin.setRange(-1e18, 1e18)
        self.start_spin.setValue(float(start))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setDecimals(8)
        self.end_spin.setRange(-1e18, 1e18)
        self.end_spin.setValue(float(end))

        form = QFormLayout()
        form.addRow("Range", self.mode_combo)
        form.addRow("Start", self.start_spin)
        form.addRow("End", self.end_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._mode_changed()

    def range_selection(self) -> tuple[str, float, float]:
        return (
            self.mode_combo.currentData(),
            float(self.start_spin.value()),
            float(self.end_spin.value()),
        )

    def _mode_changed(self) -> None:
        enabled = self.mode_combo.currentData() == "manual"
        self.start_spin.setEnabled(enabled)
        self.end_spin.setEnabled(enabled)


class IntegrationResultsDialog(QDialog):
    """Show integration results and provide copy/export actions."""

    HEADERS = [
        "Curve",
        "Y unit",
        "Time unit",
        "Range",
        "Points",
        "Integral",
        "Result unit",
        "Warnings",
    ]

    def __init__(
        self,
        results: list[IntegrationResult],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Integration Results")
        self.results = results
        self.table = QTableWidget(len(results), len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self._populate_table()
        self.table.resizeColumnsToContents()

        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self.copy_to_clipboard)
        export_button = QPushButton("Export Results CSV")
        export_button.clicked.connect(self.export_csv)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(copy_button)
        button_row.addWidget(export_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Integration results"))
        layout.addWidget(self.table)
        layout.addLayout(button_row)
        self.resize(900, 320)

    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self._csv_text())

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Integration Results", "integration_results.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        output_path = Path(path)
        if output_path.exists():
            response = QMessageBox.question(
                self,
                "Export Integration Results",
                f"{output_path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(self._csv_text())

    def _populate_table(self) -> None:
        for row, result in enumerate(self.results):
            values = [
                result.curve_name,
                result.curve_unit,
                result.time_unit,
                f"{result.start_time:.8g} to {result.end_time:.8g}",
                str(result.point_count),
                f"{result.value:.10g}",
                result.result_unit,
                "; ".join(result.warnings),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _csv_text(self) -> str:
        rows = [
            [
                result.curve_name,
                result.curve_unit,
                result.time_unit,
                result.start_time,
                result.end_time,
                result.point_count,
                result.value,
                result.result_unit,
                "; ".join(result.warnings),
            ]
            for result in self.results
        ]
        output: list[str] = []
        output.append(
            "curve,y_unit,time_unit,start_time,end_time,point_count,integral,result_unit,warnings"
        )
        for row in rows:
            line = []
            for value in row:
                text = str(value)
                if any(char in text for char in [",", "\"", "\n"]):
                    text = "\"" + text.replace("\"", "\"\"") + "\""
                line.append(text)
            output.append(",".join(line))
        return "\n".join(output) + "\n"
