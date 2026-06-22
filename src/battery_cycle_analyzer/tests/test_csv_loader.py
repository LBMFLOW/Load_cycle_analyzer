from __future__ import annotations

from pathlib import Path

import pytest

from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.csv_loader import CsvImportError, CsvLoader
from battery_cycle_analyzer.core.import_config import ImportSettings


SAMPLE = Path(__file__).parent / "sample_data" / "basic_cycle.csv"
METADATA_ROWS = Path(__file__).parent / "sample_data" / "metadata_rows_cycle.csv"
MISSING_VALUES = Path(__file__).parent / "sample_data" / "missing_values_cycle.csv"
DUPLICATE_LABELS = Path(__file__).parent / "sample_data" / "duplicate_labels_cycle.csv"
SEMICOLON = Path(__file__).parent / "sample_data" / "semicolon_cycle.csv"


def test_csv_loader_uses_user_mapping() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=SAMPLE),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
    )

    assert dataset.time_column == "time"
    assert dataset.discharge_energy_column == "discharge_energy"
    assert dataset.metadata.labels["discharge_energy"] == "Discharge Energy"
    assert dataset.metadata.units["voltage"] == "V"
    assert dataset.frame["charge_energy"].iloc[-1] == 102
    assert dataset.import_settings is not None
    assert dataset.column_mapping is not None
    assert not [issue for issue in dataset.validation_warnings if issue.is_fatal]


def test_preview_labels_combine_parameter_and_unit() -> None:
    preview = CsvLoader().preview(ImportSettings(path=SAMPLE))

    assert preview.display_label(1) == "Discharge Energy [Wh]"
    assert preview.display_label(3) == "Voltage [V]"


def test_extra_metadata_rows_before_labels() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=METADATA_ROWS, label_row=3, unit_row=4, first_data_row=5),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
    )

    assert dataset.time_column == "elapsed_time"
    assert dataset.metadata.labels["elapsed_time"] == "Elapsed Time"
    assert dataset.metadata.units["temperature"] == "C"
    assert dataset.frame["discharge_energy"].tolist() == [101, 100, 99]


def test_missing_values_become_nan_and_warn() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=MISSING_VALUES, treat_missing_markers_as_nan=True),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2),
    )

    assert dataset.frame["discharge_energy"].isna().sum() == 2
    assert dataset.frame["charge_energy"].isna().sum() == 1
    assert any(issue.code == "missing_values" for issue in dataset.validation_warnings)


def test_duplicate_labels_are_resolved_by_index() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=DUPLICATE_LABELS),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
    )

    assert dataset.frame.columns.tolist() == ["time", "energy", "energy_2", "energy_3"]
    assert dataset.discharge_energy_column == "energy"
    assert dataset.charge_energy_column == "energy_2"
    assert dataset.metadata.units["energy_3"] == "mWh"


def test_semicolon_delimiter_and_decimal_comma() -> None:
    dataset = CsvLoader().load(
        ImportSettings(path=SEMICOLON, delimiter=";", decimal_separator=","),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
    )

    assert dataset.time_column == "zeit"
    assert dataset.frame["entladeenergie"].iloc[1] == pytest.approx(99.5)
    assert dataset.frame["spannung"].iloc[0] == pytest.approx(4.2)


def test_validation_requires_time_and_energy_columns() -> None:
    loader = CsvLoader()
    issues = loader.validate_import(
        ImportSettings(path=SAMPLE),
        ColumnMapping(time=None, discharge_energy=1),
    )
    assert issues[0].severity == "error"

    issues = loader.validate_import(
        ImportSettings(path=SAMPLE),
        ColumnMapping(time=0, discharge_energy=None, charge_energy=None),
    )
    assert issues[0].severity == "error"


def test_malformed_csv_raises_friendly_error() -> None:
    path = _output_path("malformed.csv")
    path.write_text('Time,Energy\ns,Wh\n0,"unterminated\n', encoding="utf-8")

    with pytest.raises(CsvImportError, match="could not be read"):
        CsvLoader().load(
            ImportSettings(path=path, unit_row=1, first_data_row=2),
            ColumnMapping(time=0, discharge_energy=1),
        )

    _clean(path)


def test_bad_units_warn_without_crashing() -> None:
    path = _output_path("bad_units.csv")
    path.write_text(
        "Time,Discharge Energy,Charge Energy\n"
        "s,bananas,Wh\n"
        "0,100,105\n"
        "1,99,104\n",
        encoding="utf-8",
    )

    dataset = CsvLoader().load(
        ImportSettings(path=path),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2),
    )

    assert any(issue.code == "unknown_unit" for issue in dataset.validation_warnings)

    _clean(path)


def test_missing_labels_fall_back_to_column_indexes() -> None:
    path = _output_path("missing_labels.csv")
    path.write_text(
        "s,Wh,Wh\n"
        "0,100,105\n"
        "1,99,104\n",
        encoding="utf-8",
    )

    dataset = CsvLoader().load(
        ImportSettings(path=path, label_row=None, unit_row=0, first_data_row=1),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2),
    )

    assert dataset.frame.columns.tolist() == ["column_1", "column_2", "column_3"]
    assert dataset.metadata.labels["column_2"] == "Column 2"
    assert dataset.metadata.units["column_2"] == "Wh"

    _clean(path)


def test_non_numeric_required_energy_column_is_fatal() -> None:
    path = _output_path("non_numeric.csv")
    path.write_text(
        "Time,Discharge Energy\n"
        "s,Wh\n"
        "0,bad\n"
        "1,worse\n",
        encoding="utf-8",
    )

    dataset = CsvLoader().load(
        ImportSettings(path=path),
        ColumnMapping(time=0, discharge_energy=1),
    )

    assert any(
        issue.code == "non_numeric_values" and issue.is_fatal
        for issue in dataset.validation_warnings
    )

    _clean(path)


def test_large_synthetic_csv_import_uses_selected_columns_and_progress() -> None:
    path = _output_path("large_500k.csv")
    row_count = 500_000
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("Time,Discharge Energy,Charge Energy,Voltage,Unused\n")
        handle.write("s,Wh,Wh,V,A\n")
        for index in range(row_count):
            handle.write(f"{index},{1000-index * 0.001:.6f},{1005-index * 0.001:.6f},4.0,9\n")

    progress: list[tuple[int, str]] = []
    dataset = CsvLoader().load(
        ImportSettings(path=path),
        ColumnMapping(time=0, discharge_energy=1, charge_energy=2, additional=[3]),
        progress_callback=lambda value, message: progress.append((value, message)),
    )

    assert len(dataset.frame) == row_count
    assert dataset.frame.columns.tolist() == [
        "time",
        "discharge_energy",
        "charge_energy",
        "voltage",
    ]
    assert progress[-1][0] == 100

    _clean(path)


def _output_path(name: str) -> Path:
    output_dir = Path(__file__).resolve().parents[3] / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir / name


def _clean(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
    output_dir = Path(__file__).resolve().parents[3] / ".test_outputs"
    try:
        output_dir.rmdir()
    except OSError:
        pass
