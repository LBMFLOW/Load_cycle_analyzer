from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from battery_aging_app.analysis.integration import integrate_visible_curves
from battery_aging_app.analysis.sections import build_sections, new_divider
from battery_aging_app.exports.csv_export import export_section_csv, section_dataframe
from battery_aging_app.importers.csv_import import read_battery_csv
from battery_aging_app.models import ColumnMapping


ROOT = Path(__file__).resolve().parents[1]


def _dataset():
    return read_battery_csv(
        ROOT / "sample_data" / "battery_cycle_basic.csv",
        ColumnMapping(
            label_row=0,
            unit_row=1,
            first_data_row=2,
            time_column=0,
            discharge_energy_column=1,
            charge_energy_column=2,
            additional_columns=[3],
        ),
    )


def test_sections_are_built_from_dividers() -> None:
    dividers = [new_divider(20.0, "Start stress"), new_divider(40.0, "Stop stress")]
    sections = build_sections(dividers, time_min=0.0, time_max=50.0)

    assert [(section.start_time, section.end_time) for section in sections] == [
        (0.0, 20.0),
        (20.0, 40.0),
        (40.0, 50.0),
    ]


def test_integrates_visible_curves_over_section() -> None:
    dataset = _dataset()
    section = build_sections([new_divider(20.0), new_divider(40.0)], time_min=0.0, time_max=50.0)[1]

    results, warnings = integrate_visible_curves(
        dataset,
        visible_curves=["Discharge Energy", "Charge Energy"],
        section=section,
    )

    assert {result.curve_name for result in results} == {
        "Discharge Energy",
        "Charge Energy",
    }
    discharge = next(result for result in results if result.curve_name == "Discharge Energy")
    assert discharge.integral_value == pytest.approx((98.5 + 97.9) / 2 * 10 + (97.9 + 97.1) / 2 * 10)
    assert not [warning for warning in warnings if warning.severity == "error"]


def test_export_section_csv_and_metadata() -> None:
    dataset = _dataset()
    section = build_sections([new_divider(20.0), new_divider(40.0)], time_min=0.0, time_max=50.0)[1]
    output_dir = ROOT / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / "section.csv"
    sidecar = output.with_suffix(".csv.metadata.json")
    output.unlink(missing_ok=True)
    sidecar.unlink(missing_ok=True)

    export_section_csv(
        dataset,
        section,
        output,
        curves=["Discharge Energy", "Charge Energy", "Voltage"],
    )

    exported = pd.read_csv(output)
    assert exported["relative_time"].tolist() == [0.0, 10.0, 20.0]
    assert exported["Time"].tolist() == [20.0, 30.0, 40.0]

    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["source_file"].endswith("battery_cycle_basic.csv")
    assert metadata["units"]["Discharge Energy"] == "Wh"
    output.unlink(missing_ok=True)
    sidecar.unlink(missing_ok=True)
    output_dir.rmdir()


def test_section_dataframe_empty_section_has_expected_columns() -> None:
    dataset = _dataset()
    section = build_sections([new_divider(100.0)], time_min=0.0, time_max=50.0)[1]
    frame = section_dataframe(dataset, section, curves=["Discharge Energy"])

    assert frame.columns.tolist() == ["relative_time", "Time", "Discharge Energy"]
