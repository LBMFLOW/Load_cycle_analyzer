from __future__ import annotations

from pathlib import Path

import pytest

from battery_aging_app.importers.csv_import import read_battery_csv
from battery_aging_app.models import ColumnMapping


ROOT = Path(__file__).resolve().parents[1]


def test_import_basic_csv_with_metadata() -> None:
    dataset = read_battery_csv(
        ROOT / "sample_data" / "battery_cycle_basic.csv",
        ColumnMapping(
            label_row=0,
            unit_row=1,
            first_data_row=2,
            time_column=0,
            discharge_energy_column=1,
            charge_energy_column=2,
            additional_columns=[3, 4],
        ),
    )

    assert dataset.time_column == "Time"
    assert dataset.discharge_column == "Discharge Energy"
    assert dataset.charge_column == "Charge Energy"
    assert dataset.metadata.units["Time"] == "s"
    assert dataset.metadata.units["Voltage"] == "V"
    assert len(dataset.frame) == 6
    assert dataset.frame["Discharge Energy"].iloc[1] == pytest.approx(99.2)
    assert not [warning for warning in dataset.warnings if warning.severity == "error"]


def test_import_decimal_comma_semicolon_csv() -> None:
    dataset = read_battery_csv(
        ROOT / "sample_data" / "battery_cycle_semicolon_decimal_comma.csv",
        ColumnMapping(
            label_row=0,
            unit_row=1,
            first_data_row=2,
            delimiter=";",
            decimal_separator=",",
            time_column=0,
            discharge_energy_column=1,
            charge_energy_column=2,
        ),
    )

    assert dataset.frame["Entladeenergie"].iloc[1] == pytest.approx(99.5)
    assert any(warning.code == "large_time_gaps" for warning in dataset.warnings)
