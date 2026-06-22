from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.csv_loader import CsvLoader
from battery_cycle_analyzer.core.data_model import Section
from battery_cycle_analyzer.core.export import (
    ExportService,
    SectionExportError,
    SectionExportOptions,
)
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.core.sections import SectionManager


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = Path(__file__).parent / "sample_data" / "basic_cycle.csv"


def test_export_section_csv_slices_rows_and_relative_time() -> None:
    dataset = _dataset()
    manager = SectionManager()
    section = manager.build_sections(
        [manager.create_divider(10), manager.create_divider(30)],
        time_min=0,
        time_max=30,
    )[1]
    output = _output_path("section_slice.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    ExportService().section_csv(
        dataset,
        section,
        ["discharge_energy"],
        output,
        options=SectionExportOptions(include_metadata_comments=False),
    )

    exported = pd.read_csv(output)
    assert exported["Relative Time [s]"].tolist() == [0.0, 10.0]
    assert exported["Time [s]"].tolist() == [10, 20]
    assert exported["Discharge Energy [Wh]"].tolist() == [99, 98]
    assert json.loads(metadata.read_text(encoding="utf-8"))["number_of_points"] == 2

    _clean(output, metadata)


def test_export_relative_time_starts_at_zero_with_unit_conversion() -> None:
    dataset = _dataset()
    manager = SectionManager()
    section = manager.build_sections(
        [manager.create_divider(10), manager.create_divider(30)],
        time_min=0,
        time_max=30,
    )[1]
    output = _output_path("relative_minutes.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    ExportService().section_csv(
        dataset,
        section,
        ["discharge_energy"],
        output,
        options=SectionExportOptions(
            include_metadata_comments=False,
            create_sidecar_json=False,
            relative_time_unit="minutes",
        ),
    )

    exported = pd.read_csv(output)
    assert exported["Relative Time [min]"].iloc[0] == pytest.approx(0.0)
    assert exported["Relative Time [min]"].iloc[1] == pytest.approx(10.0 / 60.0)
    assert not metadata.exists()

    _clean(output, metadata)


def test_export_includes_only_visible_curves_by_default() -> None:
    dataset = _dataset()
    section = Section(
        "section:all",
        "Whole dataset",
        0,
        30,
        end_inclusive=True,
    )
    output = _output_path("visible_curves.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    ExportService().section_csv(
        dataset,
        section,
        ["discharge_energy"],
        output,
        options=SectionExportOptions(include_metadata_comments=False),
    )

    exported = pd.read_csv(output)
    assert list(exported.columns) == [
        "Relative Time [s]",
        "Time [s]",
        "Discharge Energy [Wh]",
    ]

    _clean(output, metadata)


def test_export_can_include_all_imported_columns() -> None:
    dataset = _dataset()
    section = Section(
        "section:all",
        "Whole dataset",
        0,
        30,
        end_inclusive=True,
    )
    output = _output_path("all_columns.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    ExportService().section_csv(
        dataset,
        section,
        ["discharge_energy"],
        output,
        options=SectionExportOptions(
            include_all_columns=True,
            include_metadata_comments=False,
            create_sidecar_json=False,
        ),
    )

    exported = pd.read_csv(output)
    assert "Discharge Energy [Wh]" in exported.columns
    assert "Charge Energy [Wh]" in exported.columns
    assert "Voltage [V]" in exported.columns

    _clean(output, metadata)


def test_export_metadata_comments_and_json() -> None:
    dataset = _dataset()
    section = Section(
        "section:note",
        "Formation hold",
        10,
        30,
        note="reviewed region",
    )
    output = _output_path("metadata_section.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    result = ExportService().section_csv(
        dataset,
        section,
        ["discharge_energy", "charge_energy"],
        output,
        options=SectionExportOptions(include_metadata_comments=True),
    )

    text = output.read_text(encoding="utf-8")
    assert text.startswith("# source_csv_path:")
    assert "# section_name: Formation hold" in text
    exported = pd.read_csv(output, comment="#")
    assert len(exported) == 2

    sidecar = json.loads(metadata.read_text(encoding="utf-8"))
    assert sidecar["section_name"] == "Formation hold"
    assert sidecar["selected_curve_names"] == [
        "Discharge Energy [Wh]",
        "Charge Energy [Wh]",
    ]
    assert sidecar["notes"]["section"] == "reviewed region"
    assert sidecar["software_version"]
    assert result == output

    _clean(output, metadata)


def test_empty_section_prepare_warns_and_write_raises() -> None:
    dataset = _dataset()
    section = Section("section:empty", "Empty", 100, 200)
    output = _output_path("empty_section.csv")
    metadata = output.with_suffix(".metadata.json")
    _clean(output, metadata)

    service = ExportService()
    payload = service.prepare_section_export(
        dataset,
        section,
        ["discharge_energy"],
        options=SectionExportOptions(include_metadata_comments=False),
    )

    assert payload.point_count == 0
    assert payload.warnings == ["Selected section is empty."]
    with pytest.raises(SectionExportError):
        service.write_section_export(
            payload,
            output,
            options=SectionExportOptions(include_metadata_comments=False),
        )
    assert not output.exists()
    assert not metadata.exists()


def _dataset():
    return CsvLoader().load(
        ImportSettings(path=SAMPLE),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
    )


def _output_path(name: str) -> Path:
    output_dir = ROOT / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir / name


def _clean(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
    output_dir = ROOT / ".test_outputs"
    try:
        output_dir.rmdir()
    except OSError:
        pass
