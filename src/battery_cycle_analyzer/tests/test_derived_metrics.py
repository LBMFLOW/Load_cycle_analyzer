from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from battery_cycle_analyzer.core.data_model import LoadedDataset, LoadedDatasetMetadata, Section
from battery_cycle_analyzer.core.derived_metrics import (
    BaselineConfig,
    DerivedMetricOptions,
    DerivedMetricsService,
)


def test_derived_metrics_with_first_point_baseline() -> None:
    dataset = _dataset(
        discharge=[100.0, 90.0, 80.0, 70.0],
        charge=[110.0, 100.0, 90.0, 80.0],
    )

    result = DerivedMetricsService().compute(dataset)
    frame = result.frame

    assert frame["discharge_energy_retention_pct"].tolist() == pytest.approx(
        [100.0, 90.0, 80.0, 70.0]
    )
    assert frame["charge_energy_retention_pct"].tolist() == pytest.approx(
        [100.0, 100.0 / 110.0 * 100.0, 90.0 / 110.0 * 100.0, 80.0 / 110.0 * 100.0]
    )
    assert frame["discharge_percent_energy_fade"].tolist() == pytest.approx(
        [0.0, 10.0, 20.0, 30.0]
    )
    assert frame["energy_efficiency"].tolist() == pytest.approx(
        [100.0 / 110.0, 90.0 / 100.0, 80.0 / 90.0, 70.0 / 80.0]
    )
    assert frame["energy_loss"].tolist() == pytest.approx([10.0, 10.0, 10.0, 10.0])
    assert result.baseline_values == {"discharge_energy": 100.0, "charge_energy": 110.0}


def test_baseline_mean_first_n_manual_and_section() -> None:
    dataset = _dataset(
        discharge=[100.0, 90.0, 80.0, 70.0],
        charge=[110.0, 100.0, 90.0, 80.0],
    )
    service = DerivedMetricsService()

    mean_result = service.compute(
        dataset,
        DerivedMetricOptions(baseline=BaselineConfig(mode="mean_first_n", first_n=2)),
    )
    manual_result = service.compute(
        dataset,
        DerivedMetricOptions(baseline=BaselineConfig(mode="manual", manual_value=50.0)),
    )
    section = Section("section:test", "Middle", 1.0, 3.0)
    section_result = service.compute(
        dataset,
        DerivedMetricOptions(baseline=BaselineConfig(mode="section")),
        baseline_section=section,
    )

    assert mean_result.baseline_values["discharge_energy"] == pytest.approx(95.0)
    assert manual_result.baseline_values["discharge_energy"] == pytest.approx(50.0)
    assert section_result.baseline_values["discharge_energy"] == pytest.approx(85.0)


def test_rolling_metrics_derivative_and_cycle_delta() -> None:
    dataset = _dataset(
        discharge=[10.0, 12.0, 14.0, 16.0],
        charge=[11.0, 13.0, 15.0, 17.0],
    )

    frame = DerivedMetricsService().compute(
        dataset,
        DerivedMetricOptions(rolling_window=3),
    ).frame

    assert frame["discharge_rolling_mean"].tolist() == pytest.approx(
        [11.0, 12.0, 14.0, 15.0]
    )
    assert frame["discharge_rolling_std"].iloc[1] == pytest.approx(2.0)
    assert frame["discharge_slope_over_time"].tolist() == pytest.approx(
        [2.0, 2.0, 2.0, 2.0]
    )
    assert pd.isna(frame["discharge_cycle_delta"].iloc[0])
    assert frame["discharge_cycle_delta"].iloc[1:].tolist() == pytest.approx(
        [2.0, 2.0, 2.0]
    )


def test_cycle_column_selection_and_row_number_estimation() -> None:
    dataset = _dataset(
        discharge=[100.0, 99.0, 98.0],
        charge=[101.0, 100.0, 99.0],
        cycle=[10, 11, 12],
    )

    with_cycle = DerivedMetricsService().compute(
        dataset,
        DerivedMetricOptions(cycle_column="cycle"),
    )
    estimated = DerivedMetricsService().compute(_dataset([1.0, 2.0], [1.1, 2.1]))

    assert with_cycle.cycle_column == "cycle"
    assert "estimated_cycle_index" not in with_cycle.created_columns
    assert estimated.frame["estimated_cycle_index"].tolist() == [1, 2]


def test_event_structure_cycle_estimation() -> None:
    dataset = _dataset(
        discharge=[10.0, 8.0, 9.0, 7.0, 8.0],
        charge=[11.0, 9.0, 10.0, 8.0, 9.0],
    )

    frame = DerivedMetricsService().compute(
        dataset,
        DerivedMetricOptions(cycle_estimation="event_structure"),
    ).frame

    assert frame["estimated_cycle_index"].tolist() == [1, 1, 2, 3, 4]


def test_efficiency_warning_when_discharge_exceeds_charge() -> None:
    dataset = _dataset(
        discharge=[100.0, 105.0],
        charge=[100.0, 100.0],
    )

    result = DerivedMetricsService().compute(dataset)

    assert result.frame["energy_efficiency"].tolist() == pytest.approx([1.0, 1.05])
    assert result.warnings == ["1 efficiency values are greater than 100%."]


def test_derivative_handles_nonuniform_time() -> None:
    dataset = _dataset(
        discharge=[0.0, 2.0, 8.0],
        charge=[0.0, 2.0, 8.0],
        time=[0.0, 1.0, 3.0],
    )

    frame = DerivedMetricsService().compute(dataset).frame

    assert frame["discharge_slope_over_time"].tolist() == pytest.approx(
        [2.0, 7.0 / 3.0, 3.0]
    )


def _dataset(
    discharge: list[float],
    charge: list[float],
    *,
    time: list[float] | None = None,
    cycle: list[int] | None = None,
) -> LoadedDataset:
    data = {
        "time": time or list(range(len(discharge))),
        "discharge_energy": discharge,
        "charge_energy": charge,
    }
    labels = {
        "time": "Time",
        "discharge_energy": "Discharge Energy",
        "charge_energy": "Charge Energy",
    }
    units = {"time": "s", "discharge_energy": "Wh", "charge_energy": "Wh"}
    if cycle is not None:
        data["cycle"] = cycle
        labels["cycle"] = "Cycle"
        units["cycle"] = "cycle"
    return LoadedDataset(
        frame=pd.DataFrame(data),
        metadata=LoadedDatasetMetadata(
            source_path=Path("synthetic.csv"),
            labels=labels,
            units=units,
            roles={
                "time": "time",
                "discharge_energy": "discharge_energy",
                "charge_energy": "charge_energy",
            },
        ),
    )
