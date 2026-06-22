from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from battery_cycle_analyzer.core.derived_metrics import (
    BaselineConfig,
    DerivedMetricOptions,
)
from battery_cycle_analyzer.core.filtering import DataFilterOptions
from battery_cycle_analyzer.core.data_model import LoadedDataset


class AdvancedAnalysisPanel(QWidget):
    apply_metrics_requested = pyqtSignal()
    apply_filter_requested = pyqtSignal()
    reset_processed_view_requested = pyqtSignal()
    plot_energy_cycle_requested = pyqtSignal()
    plot_retention_cycle_requested = pyqtSignal()
    add_comparison_requested = pyqtSignal()
    export_comparison_requested = pyqtSignal()
    export_report_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(280)
        self.baseline_combo = QComboBox()
        self.baseline_combo.addItem("First data point", "first")
        self.baseline_combo.addItem("Mean of first N points", "mean_first_n")
        self.baseline_combo.addItem("Selected section", "section")
        self.baseline_combo.addItem("Manual value", "manual")
        self.baseline_combo.setToolTip("Controls the baseline used for retention and fade metrics.")

        self.first_n_spin = QSpinBox()
        self.first_n_spin.setRange(1, 100000)
        self.first_n_spin.setValue(5)
        self.manual_value = QLineEdit()
        self.manual_value.setPlaceholderText("Optional baseline value")

        self.cycle_column_combo = QComboBox()
        self.cycle_column_combo.setToolTip("Use a cycle-index column when present, or estimate cycles.")
        self.cycle_estimation_combo = QComboBox()
        self.cycle_estimation_combo.addItem("Row number", "row_number")
        self.cycle_estimation_combo.addItem("Charge/discharge event structure", "event_structure")

        self.rolling_window_spin = QSpinBox()
        self.rolling_window_spin.setRange(1, 100000)
        self.rolling_window_spin.setValue(5)
        self.rolling_window_spin.setToolTip("Window used for rolling mean, rolling standard deviation, and smoothing.")

        self.time_min = QLineEdit()
        self.time_max = QLineEdit()
        self.cycle_min = QLineEdit()
        self.cycle_max = QLineEdit()
        self.remove_nan_check = QCheckBox("Remove NaN rows")
        self.remove_duplicates_check = QCheckBox("Remove duplicate timestamps")
        self.outlier_combo = QComboBox()
        self.outlier_combo.addItem("No outlier filter", "none")
        self.outlier_combo.addItem("Z-score", "zscore")
        self.outlier_combo.addItem("IQR", "iqr")
        self.smoothing_check = QCheckBox("Create smoothed columns")

        self.apply_metrics_button = QPushButton("Apply Derived Metrics")
        self.apply_metrics_button.setToolTip(
            "Adds retention, efficiency, loss, fade, rolling, slope, and delta columns."
        )
        self.apply_filter_button = QPushButton("Apply Processed View")
        self.reset_button = QPushButton("Reset Raw View")
        self.plot_energy_button = QPushButton("Plot Energy vs Cycle")
        self.plot_retention_button = QPushButton("Plot Retention vs Cycle")
        self.add_comparison_button = QPushButton("Add Current Dataset")
        self.export_comparison_button = QPushButton("Export Comparison CSV")
        self.export_report_button = QPushButton("Export HTML Report")

        self.apply_metrics_button.clicked.connect(self.apply_metrics_requested.emit)
        self.apply_filter_button.clicked.connect(self.apply_filter_requested.emit)
        self.reset_button.clicked.connect(self.reset_processed_view_requested.emit)
        self.plot_energy_button.clicked.connect(self.plot_energy_cycle_requested.emit)
        self.plot_retention_button.clicked.connect(self.plot_retention_cycle_requested.emit)
        self.add_comparison_button.clicked.connect(self.add_comparison_requested.emit)
        self.export_comparison_button.clicked.connect(self.export_comparison_requested.emit)
        self.export_report_button.clicked.connect(self.export_report_requested.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(self._baseline_group())
        layout.addWidget(self._cycle_group())
        layout.addWidget(self._filter_group())
        layout.addWidget(self._comparison_group())
        layout.addStretch(1)
        self.setEnabled(False)

    def configure(self, dataset: LoadedDataset | None) -> None:
        self.setEnabled(dataset is not None)
        self.cycle_column_combo.clear()
        self.cycle_column_combo.addItem("(estimate cycle index)", None)
        if dataset is None:
            return
        for column in dataset.frame.columns:
            self.cycle_column_combo.addItem(self._display_name(dataset, column), column)
            if "cycle" in str(column).casefold():
                self.cycle_column_combo.setCurrentIndex(self.cycle_column_combo.count() - 1)

    def metric_options(self, dataset: LoadedDataset) -> DerivedMetricOptions:
        manual = self._float_or_none(self.manual_value.text())
        return DerivedMetricOptions(
            discharge_column=dataset.discharge_energy_column,
            charge_column=dataset.charge_energy_column,
            time_column=dataset.time_column,
            cycle_column=self.cycle_column_combo.currentData(),
            baseline=BaselineConfig(
                mode=self.baseline_combo.currentData(),
                first_n=self.first_n_spin.value(),
                manual_value=manual,
            ),
            rolling_window=self.rolling_window_spin.value(),
            cycle_estimation=self.cycle_estimation_combo.currentData(),
        )

    def filter_options(self, dataset: LoadedDataset) -> DataFilterOptions:
        columns = tuple(
            column
            for column in [
                dataset.discharge_energy_column,
                dataset.charge_energy_column,
            ]
            if column is not None
        )
        return DataFilterOptions(
            time_column=dataset.time_column,
            cycle_column=self.cycle_column_combo.currentData(),
            time_min=self._float_or_none(self.time_min.text()),
            time_max=self._float_or_none(self.time_max.text()),
            cycle_min=self._float_or_none(self.cycle_min.text()),
            cycle_max=self._float_or_none(self.cycle_max.text()),
            remove_nan_rows=self.remove_nan_check.isChecked(),
            remove_duplicate_timestamps=self.remove_duplicates_check.isChecked(),
            outlier_method=self.outlier_combo.currentData(),
            outlier_columns=columns,
            smoothing_window=self.rolling_window_spin.value() if self.smoothing_check.isChecked() else 1,
            smoothing_columns=columns,
            preserve_raw=True,
        )

    def state(self) -> dict[str, object]:
        return {
            "baseline_mode": self.baseline_combo.currentData(),
            "first_n": self.first_n_spin.value(),
            "manual_value": self.manual_value.text(),
            "cycle_column": self.cycle_column_combo.currentData(),
            "cycle_estimation": self.cycle_estimation_combo.currentData(),
            "rolling_window": self.rolling_window_spin.value(),
            "time_min": self.time_min.text(),
            "time_max": self.time_max.text(),
            "cycle_min": self.cycle_min.text(),
            "cycle_max": self.cycle_max.text(),
            "remove_nan_rows": self.remove_nan_check.isChecked(),
            "remove_duplicate_timestamps": self.remove_duplicates_check.isChecked(),
            "outlier_method": self.outlier_combo.currentData(),
            "create_smoothed_columns": self.smoothing_check.isChecked(),
        }

    def restore_state(self, state: dict[str, object]) -> None:
        self._set_combo_data(self.baseline_combo, state.get("baseline_mode"))
        self.first_n_spin.setValue(int(state.get("first_n", self.first_n_spin.value())))
        self.manual_value.setText(str(state.get("manual_value", "") or ""))
        self._set_combo_data(self.cycle_column_combo, state.get("cycle_column"))
        self._set_combo_data(self.cycle_estimation_combo, state.get("cycle_estimation"))
        self.rolling_window_spin.setValue(
            int(state.get("rolling_window", self.rolling_window_spin.value()))
        )
        self.time_min.setText(str(state.get("time_min", "") or ""))
        self.time_max.setText(str(state.get("time_max", "") or ""))
        self.cycle_min.setText(str(state.get("cycle_min", "") or ""))
        self.cycle_max.setText(str(state.get("cycle_max", "") or ""))
        self.remove_nan_check.setChecked(bool(state.get("remove_nan_rows", False)))
        self.remove_duplicates_check.setChecked(
            bool(state.get("remove_duplicate_timestamps", False))
        )
        self._set_combo_data(self.outlier_combo, state.get("outlier_method"))
        self.smoothing_check.setChecked(bool(state.get("create_smoothed_columns", False)))

    def _baseline_group(self) -> QGroupBox:
        group = QGroupBox("Derived Metrics")
        form = QFormLayout(group)
        form.addRow("Baseline", self.baseline_combo)
        form.addRow("First N", self.first_n_spin)
        form.addRow("Manual value", self.manual_value)
        form.addRow("Rolling window", self.rolling_window_spin)
        form.addRow(self.apply_metrics_button)
        return group

    def _cycle_group(self) -> QGroupBox:
        group = QGroupBox("Cycle Handling")
        form = QFormLayout(group)
        form.addRow("Cycle column", self.cycle_column_combo)
        form.addRow("Estimate by", self.cycle_estimation_combo)
        row = QHBoxLayout()
        row.addWidget(self.plot_energy_button)
        row.addWidget(self.plot_retention_button)
        form.addRow(row)
        return group

    def _filter_group(self) -> QGroupBox:
        group = QGroupBox("Processed View")
        form = QFormLayout(group)
        form.addRow("Time min", self.time_min)
        form.addRow("Time max", self.time_max)
        form.addRow("Cycle min", self.cycle_min)
        form.addRow("Cycle max", self.cycle_max)
        form.addRow(self.remove_nan_check)
        form.addRow(self.remove_duplicates_check)
        form.addRow("Outliers", self.outlier_combo)
        form.addRow(self.smoothing_check)
        form.addRow(self.apply_filter_button)
        form.addRow(self.reset_button)
        return group

    def _comparison_group(self) -> QGroupBox:
        group = QGroupBox("Comparison and Report")
        layout = QVBoxLayout(group)
        layout.addWidget(QLabel("Overlay discharge retention curves across files."))
        layout.addWidget(self.add_comparison_button)
        layout.addWidget(self.export_comparison_button)
        layout.addWidget(self.export_report_button)
        return group

    def _display_name(self, dataset: LoadedDataset, column: str) -> str:
        label = dataset.metadata.labels.get(column, column)
        unit = dataset.metadata.units.get(column, "")
        return f"{label} [{unit}]" if unit else label

    def _float_or_none(self, text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None

    def _set_combo_data(self, combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
