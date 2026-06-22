from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from battery_aging_app.importers.csv_import import CsvPreview, preview_csv
from battery_aging_app.importers.presets import MappingPresetStore
from battery_aging_app.models import ColumnMapping


class ImportDialog(QDialog):
    def __init__(self, path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.setWindowTitle(f"Import CSV: {self.path.name}")
        self.resize(980, 720)
        self._preview: CsvPreview | None = None
        self._preset_store = MappingPresetStore()

        self.delimiter_combo = QComboBox()
        self.delimiter_combo.setEditable(True)
        for text, value in [
            ("Comma (,)", ","),
            ("Semicolon (;)", ";"),
            ("Tab", "\t"),
            ("Pipe (|)", "|"),
        ]:
            self.delimiter_combo.addItem(text, value)

        self.decimal_combo = QComboBox()
        self.decimal_combo.addItem("Period (.)", ".")
        self.decimal_combo.addItem("Comma (,)", ",")

        self.encoding_combo = QComboBox()
        self.encoding_combo.setEditable(True)
        for encoding in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
            self.encoding_combo.addItem(encoding)

        self.label_row_spin = _optional_row_spin(default=1)
        self.unit_row_spin = _optional_row_spin(default=2)
        self.first_data_row_spin = QSpinBox()
        self.first_data_row_spin.setRange(1, 1_000_000)
        self.first_data_row_spin.setValue(3)

        self.time_combo = QComboBox()
        self.discharge_combo = QComboBox()
        self.charge_combo = QComboBox()
        self.additional_list = QListWidget()
        self.additional_list.setAlternatingRowColors(True)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)

        reload_button = QPushButton("Reload Preview")
        reload_button.clicked.connect(self.reload_preview)
        preset_button = QPushButton("Save Preset")
        preset_button.clicked.connect(self.save_preset)
        load_preset_button = QPushButton("Load Preset")
        load_preset_button.clicked.connect(self.load_preset)

        options = QFormLayout()
        options.addRow("Delimiter", self.delimiter_combo)
        options.addRow("Decimal separator", self.decimal_combo)
        options.addRow("Encoding", self.encoding_combo)
        options.addRow("Parameter-label row", self.label_row_spin)
        options.addRow("Unit row", self.unit_row_spin)
        options.addRow("First data row", self.first_data_row_spin)

        columns = QFormLayout()
        columns.addRow("Time column", self.time_combo)
        columns.addRow("Discharge-energy column", self.discharge_combo)
        columns.addRow("Charge-energy column", self.charge_combo)
        columns.addRow(QLabel("Additional columns"), self.additional_list)

        top = QGridLayout()
        top.addLayout(options, 0, 0)
        top.addLayout(columns, 0, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(reload_button)
        buttons.addWidget(load_preset_button)
        buttons.addWidget(preset_button)
        buttons.addStretch(1)
        top.addLayout(buttons, 1, 0, 1, 2)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        dialog_buttons.accepted.connect(self._validate_and_accept)
        dialog_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.preview_table, 1)
        layout.addWidget(dialog_buttons)

        for widget in [
            self.label_row_spin,
            self.unit_row_spin,
            self.first_data_row_spin,
            self.delimiter_combo,
            self.encoding_combo,
        ]:
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._refresh_column_choices)
            else:
                widget.currentTextChanged.connect(lambda _text: self.reload_preview())

        self.reload_preview()

    def mapping(self) -> ColumnMapping:
        return ColumnMapping(
            label_row=_spin_to_optional_row(self.label_row_spin),
            unit_row=_spin_to_optional_row(self.unit_row_spin),
            first_data_row=max(0, self.first_data_row_spin.value() - 1),
            delimiter=self._delimiter(),
            decimal_separator=self.decimal_combo.currentData(),
            encoding=self.encoding_combo.currentText(),
            time_column=self.time_combo.currentData(),
            discharge_energy_column=self.discharge_combo.currentData(),
            charge_energy_column=self.charge_combo.currentData(),
            additional_columns=self._selected_additional_columns(),
        )

    def reload_preview(self) -> None:
        try:
            self._preview = preview_csv(
                self.path,
                delimiter=self._delimiter(),
                encoding=self.encoding_combo.currentText(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "CSV Preview Failed", str(exc))
            return
        self._fill_preview_table()
        self._refresh_column_choices()

    def save_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save Preset", "Preset name")
        if not accepted or not name.strip():
            return
        self._preset_store.save(name.strip(), self.mapping())
        QMessageBox.information(self, "Preset Saved", f"Saved preset '{name.strip()}'.")

    def load_preset(self) -> None:
        presets = self._preset_store.load_all()
        if not presets:
            QMessageBox.information(self, "No Presets", "No mapping presets are saved.")
            return
        name, accepted = QInputDialog.getItem(
            self, "Load Preset", "Preset", sorted(presets), editable=False
        )
        if not accepted:
            return
        self._apply_mapping(presets[name])

    def _validate_and_accept(self) -> None:
        mapping = self.mapping()
        if mapping.time_column is None:
            QMessageBox.warning(self, "Missing Column", "Select a time column.")
            return
        if (
            mapping.discharge_energy_column is None
            and mapping.charge_energy_column is None
            and not mapping.additional_columns
        ):
            QMessageBox.warning(
                self,
                "Missing Data Columns",
                "Select at least one energy or additional data column.",
            )
            return
        self.accept()

    def _delimiter(self) -> str:
        data = self.delimiter_combo.currentData()
        if data:
            return str(data)
        text = self.delimiter_combo.currentText()
        return "\t" if text.casefold() == "tab" else text[:1]

    def _fill_preview_table(self) -> None:
        preview = self._preview
        if preview is None:
            return
        self.preview_table.clear()
        self.preview_table.setRowCount(len(preview.rows))
        self.preview_table.setColumnCount(preview.column_count)
        self.preview_table.setHorizontalHeaderLabels(
            [f"Column {index + 1}" for index in range(preview.column_count)]
        )
        for row_index, row in enumerate(preview.rows):
            for column_index in range(preview.column_count):
                value = row[column_index] if column_index < len(row) else ""
                self.preview_table.setItem(
                    row_index, column_index, QTableWidgetItem(value)
                )
        self.preview_table.resizeColumnsToContents()

    def _refresh_column_choices(self) -> None:
        preview = self._preview
        if preview is None:
            return
        selected = {
            "time": self.time_combo.currentData(),
            "discharge": self.discharge_combo.currentData(),
            "charge": self.charge_combo.currentData(),
            "additional": set(self._selected_additional_columns()),
        }
        labels = self._labels_from_preview()
        for combo in [self.time_combo, self.discharge_combo, self.charge_combo]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(not selected)", None)
            for index in range(preview.column_count):
                combo.addItem(_column_display(index, labels), index)
            combo.blockSignals(False)
        self._restore_combo(self.time_combo, selected["time"])
        self._restore_combo(self.discharge_combo, selected["discharge"])
        self._restore_combo(self.charge_combo, selected["charge"])

        self.additional_list.clear()
        for index in range(preview.column_count):
            item = QListWidgetItem(_column_display(index, labels))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if index in selected["additional"]
                else Qt.CheckState.Unchecked
            )
            self.additional_list.addItem(item)

    def _labels_from_preview(self) -> dict[int, str]:
        preview = self._preview
        label_row = _spin_to_optional_row(self.label_row_spin)
        if preview is None or label_row is None or label_row >= len(preview.rows):
            return {}
        return {
            index: value.strip()
            for index, value in enumerate(preview.rows[label_row])
            if value.strip()
        }

    def _selected_additional_columns(self) -> list[int]:
        refs: list[int] = []
        for index in range(self.additional_list.count()):
            item = self.additional_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                refs.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return refs

    def _restore_combo(self, combo: QComboBox, value: object) -> None:
        if value is None:
            combo.setCurrentIndex(0)
            return
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _apply_mapping(self, mapping: ColumnMapping) -> None:
        self.delimiter_combo.setCurrentText(mapping.delimiter)
        self.decimal_combo.setCurrentIndex(
            max(0, self.decimal_combo.findData(mapping.decimal_separator))
        )
        self.encoding_combo.setCurrentText(mapping.encoding)
        self.label_row_spin.setValue(0 if mapping.label_row is None else mapping.label_row + 1)
        self.unit_row_spin.setValue(0 if mapping.unit_row is None else mapping.unit_row + 1)
        self.first_data_row_spin.setValue(mapping.first_data_row + 1)
        self.reload_preview()
        self._restore_combo(self.time_combo, mapping.time_column)
        self._restore_combo(self.discharge_combo, mapping.discharge_energy_column)
        self._restore_combo(self.charge_combo, mapping.charge_energy_column)
        selected = {int(ref) for ref in mapping.additional_columns if isinstance(ref, int)}
        for index in range(self.additional_list.count()):
            item = self.additional_list.item(index)
            item.setCheckState(
                Qt.CheckState.Checked
                if int(item.data(Qt.ItemDataRole.UserRole)) in selected
                else Qt.CheckState.Unchecked
            )


def _optional_row_spin(default: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, 1_000_000)
    spin.setSpecialValueText("None")
    spin.setValue(default)
    return spin


def _spin_to_optional_row(spin: QSpinBox) -> int | None:
    return None if spin.value() == 0 else spin.value() - 1


def _column_display(index: int, labels: dict[int, str]) -> str:
    label = labels.get(index, "").strip()
    return f"{index + 1}: {label}" if label else f"{index + 1}: Column {index + 1}"
