from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from battery_cycle_analyzer.core.data_model import (
    IntegrationResult,
    SectionStatistics,
    ValidationIssue,
)


class ResultsPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.copy_button = QPushButton("Copy results")
        self.copy_button.setToolTip("Copy the current results table to the clipboard.")
        self.copy_button.clicked.connect(self.copy_results)
        self.export_button = QPushButton("Export results CSV")
        self.export_button.setToolTip("Export the current results table as CSV.")
        self.export_button.clicked.connect(self.export_results)
        self._headers: list[str] = []
        self._rows: list[list[str]] = []
        button_row = QHBoxLayout()
        button_row.addWidget(self.copy_button)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.table, 2)
        layout.addLayout(button_row)

    def show_issues(self, issues: list[ValidationIssue]) -> None:
        self._clear_table()
        if not issues:
            self.text.setPlainText("No validation issues.")
            return
        self.text.setPlainText("\n".join(f"{item.severity}: {item.message}" for item in issues))

    def show_integration_results(self, results: list[IntegrationResult]) -> None:
        self.text.setPlainText("Integration results" if results else "No integration results.")
        headers = [
            "Curve",
            "Y unit",
            "Time unit",
            "Range",
            "Points",
            "Integral",
            "Result unit",
        ]
        rows = [
            [
                item.curve_name,
                item.curve_unit,
                item.time_unit,
                f"{item.start_time:.8g} to {item.end_time:.8g}",
                str(item.point_count),
                f"{item.value:.10g}",
                item.result_unit,
            ]
            for item in results
        ]
        self._set_table(headers, rows)

    def show_section_statistics(
        self,
        section_name: str,
        stats: list[SectionStatistics],
        *,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> None:
        bounds = ""
        if start_time is not None or end_time is not None:
            start = "start" if start_time is None else self._format(start_time)
            end = "end" if end_time is None else self._format(end_time)
            bounds = f"\nRange: {start} to {end}"
        self.text.setPlainText(
            f"Selected section: {section_name}{bounds}\n"
            f"Curves: {len(stats)}"
            if stats
            else f"Selected section: {section_name}{bounds}\nNo statistics available."
        )
        headers = [
            "Curve",
            "Start",
            "End",
            "Delta",
            "% change",
            "Min",
            "Max",
            "Mean",
            "Median",
            "Std",
            "Slope",
            "Integral",
            "Integral unit",
            "Valid",
            "Missing",
        ]
        rows = [
            [
                item.curve_name,
                self._format(item.start_value),
                self._format(item.end_value),
                self._format(item.delta),
                self._format(item.percent_change),
                self._format(item.minimum),
                self._format(item.maximum),
                self._format(item.mean),
                self._format(item.median),
                self._format(item.standard_deviation),
                self._format(item.slope),
                self._format(item.integral),
                item.integral_unit,
                str(item.valid_points),
                str(item.missing_points),
            ]
            for item in stats
        ]
        self._set_table(headers, rows)

    def show_table(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
        *,
        message: str = "",
    ) -> None:
        self.text.setPlainText(f"{title}\n{message}".strip())
        self._set_table(headers, rows)

    def show_cursor_readout(
        self,
        *,
        row: int,
        cursor_value: float,
        values: dict[str, object],
        prefix: str = "Cursor",
    ) -> None:
        self.text.setPlainText(f"{prefix}\nRow: {row + 1}\nCursor x: {cursor_value:.8g}")
        rows = []
        for name, value in values.items():
            rows.append([name, self._format(value)])
        self._set_table(["Field", "Value"], rows)

    def _set_table(self, headers: list[str], rows: list[list[str]]) -> None:
        self._headers = headers
        self._rows = rows
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(headers)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _clear_table(self) -> None:
        self._headers = []
        self._rows = []
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _format(self, value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        return "" if value is None else str(value)

    def copy_results(self) -> None:
        QApplication.clipboard().setText(self._table_text(separator="\t"))

    def export_results(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            "analysis_results.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        output_path = Path(path)
        if output_path.exists():
            response = QMessageBox.question(
                self,
                "Export Results",
                f"{output_path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        output_path.write_text(self._table_text(separator=","), encoding="utf-8")

    def _table_text(self, *, separator: str) -> str:
        rows = [self._headers, *self._rows] if self._headers else self._rows
        lines = []
        for row in rows:
            fields = []
            for value in row:
                text = str(value)
                if separator == "," and any(char in text for char in [",", "\"", "\n"]):
                    text = "\"" + text.replace("\"", "\"\"") + "\""
                fields.append(text)
            lines.append(separator.join(fields))
        return "\n".join(lines) + ("\n" if lines else "")
