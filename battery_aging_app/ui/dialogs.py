from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from battery_aging_app.analysis.integration import IntegrationResult
from battery_aging_app.models import ImportWarning


class IntegrationResultsDialog(QDialog):
    def __init__(
        self,
        results: list[IntegrationResult],
        warnings: list[ImportWarning],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Integration Results")
        self.resize(720, 420)

        table = QTableWidget(len(results), 5)
        table.setHorizontalHeaderLabels(
            ["Curve", "Unit", "Time range", "Points", "Integral"]
        )
        for row, result in enumerate(results):
            values = [
                result.curve_name,
                result.curve_unit,
                f"{result.time_start:.8g} to {result.time_end:.8g} {result.time_unit}",
                str(result.point_count),
                f"{result.integral_value:.10g} {result.integral_unit}",
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()

        warnings_text = "\n".join(f"- {warning.message}" for warning in warnings)
        warning_label = QLabel(warnings_text or "No integration warnings.")
        warning_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(table, 1)
        layout.addWidget(warning_label)
        layout.addWidget(buttons)
