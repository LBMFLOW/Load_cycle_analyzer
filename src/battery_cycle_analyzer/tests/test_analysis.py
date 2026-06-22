from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from battery_cycle_analyzer.core.analysis import AnalysisOptions, AnalysisService
from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.csv_loader import CsvLoader
from battery_cycle_analyzer.core.data_model import LoadedDataset, LoadedDatasetMetadata
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.core.sections import SectionManager


SAMPLE = Path(__file__).parent / "sample_data" / "basic_cycle.csv"


def test_integrates_curve_over_section() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=SAMPLE),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2),
    )
    section = SectionManager().build_sections(
        [SectionManager().create_divider(10), SectionManager().create_divider(30)],
        time_min=0,
        time_max=30,
    )[1]

    result = AnalysisService().integrate(dataset, ["discharge_energy"], section)[0]

    assert result.value == pytest.approx((99 + 98) / 2 * 10)
    assert result.result_unit == "Wh*s"


def test_trapezoid_integration_with_known_values() -> None:
    dataset = _synthetic_dataset([0, 1, 2], [0, 1, 2])

    result = AnalysisService().integrate(dataset, ["energy"])[0]

    assert result.value == pytest.approx(2.0)
    assert result.result_unit == "Wh*s"


def test_integration_with_nonuniform_time_spacing() -> None:
    dataset = _synthetic_dataset([0, 1, 3], [0, 2, 2])

    result = AnalysisService().integrate(dataset, ["energy"])[0]

    assert result.value == pytest.approx(5.0)


def test_integration_after_time_normalization_axis_values() -> None:
    dataset = _synthetic_dataset([10, 20, 30], [1, 1, 1])

    result = AnalysisService().integrate(
        dataset,
        ["energy"],
        axis_values=np.array([0.0, 10.0, 20.0]),
        axis_unit="s",
    )[0]

    assert result.start_time == pytest.approx(0.0)
    assert result.end_time == pytest.approx(20.0)
    assert result.value == pytest.approx(20.0)


def test_missing_value_handling() -> None:
    dataset = _synthetic_dataset([0, 1, 2], [1, np.nan, 1])
    service = AnalysisService()

    dropped = service.integrate(
        dataset,
        ["energy"],
        options=AnalysisOptions(missing_value_policy="drop"),
    )[0]
    cancelled = service.integrate(
        dataset,
        ["energy"],
        options=AnalysisOptions(missing_value_policy="cancel"),
    )

    assert dropped.point_count == 2
    assert "Rows with missing x or y values were dropped." in dropped.warnings
    assert cancelled == []


def test_section_statistics() -> None:
    dataset = _synthetic_dataset([0, 1, 2], [1, 3, 5])

    stats = AnalysisService().section_statistics(dataset, ["energy"])[0]

    assert stats.start_value == pytest.approx(1.0)
    assert stats.end_value == pytest.approx(5.0)
    assert stats.delta == pytest.approx(4.0)
    assert stats.percent_change == pytest.approx(400.0)
    assert stats.minimum == pytest.approx(1.0)
    assert stats.maximum == pytest.approx(5.0)
    assert stats.mean == pytest.approx(3.0)
    assert stats.median == pytest.approx(3.0)
    assert stats.standard_deviation == pytest.approx(2.0)
    assert stats.slope == pytest.approx(2.0)
    assert stats.integral == pytest.approx(6.0)
    assert stats.valid_points == 3
    assert stats.missing_points == 0
    assert stats.integral_unit == "Wh*s"


def test_unit_labeling_of_integration_results() -> None:
    dataset = _synthetic_dataset([0, 1], [10, 10], time_unit="h", curve_unit="kWh")

    result = AnalysisService().integrate(dataset, ["energy"])[0]

    assert result.time_unit == "h"
    assert result.curve_unit == "kWh"
    assert result.result_unit == "kWh*h"


def _synthetic_dataset(
    time_values: list[float],
    energy_values: list[float],
    *,
    time_unit: str = "s",
    curve_unit: str = "Wh",
) -> LoadedDataset:
    frame = pd.DataFrame({"time": time_values, "energy": energy_values})
    metadata = LoadedDatasetMetadata(
        source_path=Path("synthetic.csv"),
        labels={"time": "Time", "energy": "Energy"},
        units={"time": time_unit, "energy": curve_unit},
        roles={"time": "time"},
    )
    return LoadedDataset(frame=frame, metadata=metadata)
