from __future__ import annotations

from pathlib import Path

from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.data_model import Divider
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.core.project_state import (
    DatasetProjectState,
    FileSignature,
    ProjectSessionState,
    ProjectStateStore,
)


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = Path(__file__).parent / "sample_data" / "basic_cycle.csv"


def test_project_json_serialization_and_deserialization() -> None:
    output_dir = ROOT / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    project_path = output_dir / "session.json"
    project_path.unlink(missing_ok=True)
    store = ProjectStateStore()
    state = _project_state(project_path, store)

    store.save(state, project_path)
    loaded = store.load(project_path)

    assert loaded.format_version == state.format_version
    assert loaded.datasets[0].name == "basic_cycle"
    assert loaded.visible_curves == ["discharge_energy", "charge_energy"]
    assert loaded.plot_settings["x_axis"] == "time"
    assert loaded.cursor_position == 10.0

    _clean(project_path)


def test_import_setting_restoration() -> None:
    project_path = ROOT / ".test_outputs" / "settings_project.json"
    store = ProjectStateStore()
    state = _project_state(project_path, store)

    settings = ImportSettings.from_dict(state.datasets[0].import_settings)
    mapping = ColumnMapping.from_dict(state.datasets[0].column_mapping)

    assert settings.delimiter == ";"
    assert settings.decimal_separator == ","
    assert settings.encoding == "utf-8"
    assert settings.label_row == 2
    assert settings.unit_row == 3
    assert settings.first_data_row == 4
    assert mapping.time == 0
    assert mapping.discharge_energy == 1
    assert mapping.charge_energy == 2
    assert mapping.additional == [3]


def test_path_relocation() -> None:
    output_dir = ROOT / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    project_path = output_dir / "relocation.json"
    store = ProjectStateStore()
    dataset = _dataset_state(project_path, store)
    dataset.source_csv_path = "missing.csv"
    dataset.import_settings["path"] = "missing.csv"

    relocated = store.relocate_source(dataset, SAMPLE, project_path)
    resolved = store.resolve_source_path(relocated.source_csv_path, project_path)

    assert resolved == SAMPLE.resolve()
    assert relocated.import_settings["path"] == relocated.source_csv_path
    assert relocated.file_signature.matches(FileSignature.from_path(SAMPLE))

    _clean(project_path)


def test_divider_and_selected_section_restoration() -> None:
    project_path = ROOT / ".test_outputs" / "dividers.json"
    store = ProjectStateStore()
    state = _project_state(project_path, store)
    payload = state.to_dict()

    loaded = ProjectSessionState.from_dict(payload)

    assert [divider.name for divider in loaded.dividers] == ["D1", "D2"]
    assert [divider.time_value for divider in loaded.dividers] == [10.0, 20.0]
    assert loaded.selected_section_id == "section:d1:d2"
    assert loaded.section_names["section:d1:d2"] == "Middle cycle"


def test_source_signature_detects_changed_file() -> None:
    output_dir = ROOT / ".test_outputs"
    output_dir.mkdir(exist_ok=True)
    source = output_dir / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    store = ProjectStateStore()
    dataset = _dataset_state(output_dir / "changed.json", store, source=source)

    source.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    assert store.source_changed(dataset, source)

    _clean(source)


def _project_state(project_path: Path, store: ProjectStateStore) -> ProjectSessionState:
    return ProjectSessionState(
        datasets=[_dataset_state(project_path, store)],
        active_dataset_index=0,
        visible_curves=["discharge_energy", "charge_energy"],
        plot_settings={
            "x_axis": "time",
            "y_axis": None,
            "show_discharge": True,
            "show_charge": True,
            "interpolation": "nearest",
            "normalize_time": False,
        },
        cursor_position=10.0,
        dividers=[
            Divider("d1", "D1", 10.0, note="start"),
            Divider("d2", "D2", 20.0),
        ],
        selected_section_id="section:d1:d2",
        section_names={"section:d1:d2": "Middle cycle"},
        annotations={"notes": "project note"},
        advanced_settings={
            "baseline_mode": "mean_first_n",
            "first_n": 3,
            "rolling_window": 5,
        },
        comparison_dataset_indexes=[],
    )


def _dataset_state(
    project_path: Path,
    store: ProjectStateStore,
    *,
    source: Path = SAMPLE,
) -> DatasetProjectState:
    settings = ImportSettings(
        path=source,
        delimiter=";",
        decimal_separator=",",
        encoding="utf-8",
        label_row=2,
        unit_row=3,
        first_data_row=4,
    )
    relative_source = store.relative_path(source, project_path.parent)
    settings_dict = settings.to_dict()
    settings_dict["path"] = relative_source
    return DatasetProjectState(
        name="basic_cycle",
        source_csv_path=relative_source,
        source_csv_original_path=str(source),
        file_signature=FileSignature.from_path(source),
        import_settings=settings_dict,
        column_mapping=ColumnMapping(
            time=0,
            discharge_energy=1,
            charge_energy=2,
            additional=[3],
        ).to_dict(),
        units={"time": "s", "discharge_energy": "Wh", "charge_energy": "Wh"},
        labels={
            "time": "Time",
            "discharge_energy": "Discharge Energy",
            "charge_energy": "Charge Energy",
        },
        source_columns={"time": 0, "discharge_energy": 1, "charge_energy": 2},
        roles={
            "time": "time",
            "discharge_energy": "discharge_energy",
            "charge_energy": "charge_energy",
        },
        clean_internal_column_names=["time", "discharge_energy", "charge_energy"],
        derived_metric_settings={"baseline_mode": "first"},
        filter_settings={"remove_nan_rows": True},
    )


def _clean(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
    output_dir = ROOT / ".test_outputs"
    try:
        output_dir.rmdir()
    except OSError:
        pass
