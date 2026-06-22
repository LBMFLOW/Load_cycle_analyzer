from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from battery_aging_app.analysis.metrics import energy_efficiency, energy_retention
from battery_aging_app.models import ColumnMapping, Divider
from battery_aging_app.plotting.sync import centered_table_window, nearest_index, trace_values
from battery_aging_app.session import ProjectSession


def test_trace_nearest_and_linear_modes() -> None:
    frame = pd.DataFrame(
        {
            "Time": [0.0, 10.0, 20.0],
            "Discharge": [100.0, 90.0, 70.0],
            "Charge": [110.0, 100.0, 90.0],
        }
    )

    assert nearest_index(frame["Time"], 12.0) == 1
    nearest = trace_values(
        frame,
        time_column="Time",
        value_columns=["Discharge", "Charge"],
        cursor_time=12.0,
        mode="nearest",
    )
    assert nearest.row_index == 1
    assert nearest.values["Discharge"] == 90.0

    linear = trace_values(
        frame,
        time_column="Time",
        value_columns=["Discharge"],
        cursor_time=15.0,
        mode="linear",
    )
    assert linear.row_index == 1
    assert linear.values["Discharge"] == pytest.approx(80.0)


def test_centered_table_window() -> None:
    assert centered_table_window(row_count=100, selected_row=50, visible_rows=11) == (45, 56)
    assert centered_table_window(row_count=10, selected_row=1, visible_rows=5) == (0, 5)
    assert centered_table_window(row_count=10, selected_row=9, visible_rows=5) == (5, 10)


def test_aging_metrics() -> None:
    discharge = pd.Series([100.0, 95.0, 90.0], name="Discharge")
    charge = pd.Series([110.0, 100.0, 95.0], name="Charge")

    assert energy_retention(discharge).tolist() == [100.0, 95.0, 90.0]
    assert energy_efficiency(discharge, charge).iloc[0] == pytest.approx(100.0 / 110.0)


def test_project_session_round_trip() -> None:
    session = ProjectSession(
        loaded_file_paths=["sample.csv"],
        mappings={"sample.csv": ColumnMapping(time_column=0)},
        dividers=[Divider(id="d1", name="Stress start", time=10.0, note="note")],
        visible_curves=["Discharge"],
    )
    path = Path(__file__).resolve().parents[1] / ".test_outputs" / "project.json"
    path.parent.mkdir(exist_ok=True)
    path.unlink(missing_ok=True)
    session.save(path)
    loaded = ProjectSession.load(path)

    assert loaded.loaded_file_paths == ["sample.csv"]
    assert loaded.mappings["sample.csv"].time_column == 0
    assert loaded.dividers[0].note == "note"
    assert loaded.visible_curves == ["Discharge"]
    path.unlink(missing_ok=True)
    path.parent.rmdir()
