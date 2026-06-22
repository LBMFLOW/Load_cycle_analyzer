from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from battery_cycle_analyzer import __version__
from battery_cycle_analyzer.core.data_model import Divider

PROJECT_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class FileSignature:
    size: int | None = None
    modified_ns: int | None = None

    @classmethod
    def from_path(cls, path: Path | None) -> "FileSignature":
        if path is None or not path.exists():
            return cls()
        stat = path.stat()
        return cls(size=int(stat.st_size), modified_ns=int(stat.st_mtime_ns))

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FileSignature":
        data = data or {}
        return cls(size=data.get("size"), modified_ns=data.get("modified_ns"))

    def to_dict(self) -> dict[str, int | None]:
        return asdict(self)

    def matches(self, other: "FileSignature") -> bool:
        return self.size == other.size and self.modified_ns == other.modified_ns


@dataclass(slots=True)
class DatasetProjectState:
    name: str
    source_csv_path: str
    source_csv_original_path: str
    file_signature: FileSignature
    import_settings: dict[str, Any]
    column_mapping: dict[str, Any]
    units: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    source_columns: dict[str, int] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    clean_internal_column_names: list[str] = field(default_factory=list)
    derived_metric_settings: dict[str, Any] = field(default_factory=dict)
    filter_settings: dict[str, Any] = field(default_factory=dict)
    derived_metrics_applied: bool = False
    filter_applied: bool = False
    embedded_data: list[dict[str, Any]] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetProjectState":
        values = dict(data)
        values["file_signature"] = FileSignature.from_dict(values.get("file_signature"))
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["file_signature"] = self.file_signature.to_dict()
        return data


@dataclass(slots=True)
class ProjectSessionState:
    format_version: int = PROJECT_FORMAT_VERSION
    software_version: str = __version__
    saved_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    datasets: list[DatasetProjectState] = field(default_factory=list)
    active_dataset_index: int = 0
    visible_curves: list[str] = field(default_factory=list)
    plot_settings: dict[str, Any] = field(default_factory=dict)
    cursor_position: float | None = None
    dividers: list[Divider] = field(default_factory=list)
    selected_section_id: str | None = None
    section_names: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)
    advanced_settings: dict[str, Any] = field(default_factory=dict)
    comparison_dataset_indexes: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSessionState":
        return cls(
            format_version=int(data.get("format_version", PROJECT_FORMAT_VERSION)),
            software_version=data.get("software_version", ""),
            saved_at_utc=data.get("saved_at_utc", ""),
            datasets=[
                DatasetProjectState.from_dict(item)
                for item in data.get("datasets", [])
            ],
            active_dataset_index=int(data.get("active_dataset_index", 0)),
            visible_curves=list(data.get("visible_curves", [])),
            plot_settings=dict(data.get("plot_settings", {})),
            cursor_position=data.get("cursor_position"),
            dividers=[Divider(**item) for item in data.get("dividers", [])],
            selected_section_id=data.get("selected_section_id"),
            section_names=dict(data.get("section_names", {})),
            annotations=dict(data.get("annotations", {})),
            advanced_settings=dict(data.get("advanced_settings", {})),
            comparison_dataset_indexes=list(data.get("comparison_dataset_indexes", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "software_version": self.software_version,
            "saved_at_utc": self.saved_at_utc,
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "active_dataset_index": self.active_dataset_index,
            "visible_curves": self.visible_curves,
            "plot_settings": self.plot_settings,
            "cursor_position": self.cursor_position,
            "dividers": [divider.to_dict() for divider in self.dividers],
            "selected_section_id": self.selected_section_id,
            "section_names": self.section_names,
            "annotations": self.annotations,
            "advanced_settings": self.advanced_settings,
            "comparison_dataset_indexes": self.comparison_dataset_indexes,
        }


class ProjectStateStore:
    """JSON persistence for battery-cycle project/session state."""

    def load(self, path: Path) -> ProjectSessionState:
        return ProjectSessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, state: ProjectSessionState, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        return path

    def resolve_source_path(self, stored_path: str, project_path: Path) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return (project_path.parent / path).resolve()

    def source_changed(self, dataset: DatasetProjectState, source_path: Path) -> bool:
        return not dataset.file_signature.matches(FileSignature.from_path(source_path))

    def relocate_source(
        self,
        dataset: DatasetProjectState,
        new_source_path: Path,
        project_path: Path,
    ) -> DatasetProjectState:
        dataset.source_csv_path = self.relative_path(new_source_path, project_path.parent)
        dataset.source_csv_original_path = str(new_source_path)
        dataset.file_signature = FileSignature.from_path(new_source_path)
        dataset.import_settings["path"] = dataset.source_csv_path
        return dataset

    def relative_path(self, path: Path, base_dir: Path) -> str:
        try:
            return os.path.relpath(path.resolve(), base_dir.resolve())
        except ValueError:
            return str(path.resolve())
