from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

InterpolationMode = Literal["nearest", "linear"]


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    column: str | None = None

    @property
    def is_fatal(self) -> bool:
        return self.severity == "error"


@dataclass(slots=True)
class LoadedDatasetMetadata:
    """Metadata captured during CSV import."""

    source_path: Path
    labels: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    source_columns: dict[str, int] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    import_rows: dict[str, int | None] = field(default_factory=dict)
    imported_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_path"] = str(self.source_path)
        return data


@dataclass(slots=True)
class LoadedDataset:
    """A loaded data table plus semantic metadata.

    The DataFrame stays in the core layer. UI code should view it through Qt
    models instead of copying rows into item widgets.
    """

    frame: pd.DataFrame
    metadata: LoadedDatasetMetadata
    import_settings: Any | None = None
    column_mapping: Any | None = None
    validation_warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def time_column(self) -> str:
        return self.metadata.roles["time"]

    @property
    def discharge_energy_column(self) -> str | None:
        return self.metadata.roles.get("discharge_energy")

    @property
    def charge_energy_column(self) -> str | None:
        return self.metadata.roles.get("charge_energy")


@dataclass(slots=True)
class CurveSpec:
    name: str
    column: str
    unit: str = ""
    color: str | None = None
    visible: bool = True
    y_axis: Literal["left", "right"] = "left"


@dataclass(slots=True)
class Divider:
    id: str
    name: str
    time_value: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Section:
    id: str
    name: str
    start_time: float | None
    end_time: float | None
    left_divider_id: str | None = None
    right_divider_id: str | None = None
    note: str = ""
    end_inclusive: bool = False

    def contains(self, time_value: float) -> bool:
        lower_ok = self.start_time is None or time_value >= self.start_time
        if self.end_time is None:
            upper_ok = True
        elif self.end_inclusive:
            upper_ok = time_value <= self.end_time
        else:
            upper_ok = time_value < self.end_time
        return lower_ok and upper_ok

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntegrationResult:
    curve_name: str
    curve_unit: str
    time_unit: str
    start_time: float
    end_time: float
    point_count: int
    value: float
    warnings: list[str] = field(default_factory=list)

    @property
    def result_unit(self) -> str:
        if self.curve_unit and self.time_unit:
            return f"{self.curve_unit}*{self.time_unit}"
        return self.curve_unit or "curve*time"


@dataclass(slots=True)
class SectionStatistics:
    curve_name: str
    curve_unit: str
    time_unit: str
    start_time: float
    end_time: float
    start_value: float
    end_value: float
    delta: float
    percent_change: float
    minimum: float
    maximum: float
    mean: float
    median: float
    standard_deviation: float
    slope: float
    integral: float
    valid_points: int
    missing_points: int
    warnings: list[str] = field(default_factory=list)

    @property
    def integral_unit(self) -> str:
        if self.curve_unit and self.time_unit:
            return f"{self.curve_unit}*{self.time_unit}"
        return self.curve_unit or "curve*time"


@dataclass(slots=True)
class ProjectState:
    file_paths: list[Path] = field(default_factory=list)
    mappings: dict[str, dict[str, Any]] = field(default_factory=dict)
    dividers: list[Divider] = field(default_factory=list)
    selected_section_id: str | None = None
    curves: list[CurveSpec] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    interpolation_mode: InterpolationMode = "nearest"
    analysis_settings: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "file_paths": [str(path) for path in self.file_paths],
            "mappings": self.mappings,
            "dividers": [divider.to_dict() for divider in self.dividers],
            "selected_section_id": self.selected_section_id,
            "curves": [asdict(curve) for curve in self.curves],
            "units": self.units,
            "interpolation_mode": self.interpolation_mode,
            "analysis_settings": self.analysis_settings,
        }

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(
            file_paths=[Path(path) for path in data.get("file_paths", [])],
            mappings=dict(data.get("mappings", {})),
            dividers=[Divider(**divider) for divider in data.get("dividers", [])],
            selected_section_id=data.get("selected_section_id"),
            curves=[CurveSpec(**curve) for curve in data.get("curves", [])],
            units=dict(data.get("units", {})),
            interpolation_mode=data.get("interpolation_mode", "nearest"),
            analysis_settings=dict(data.get("analysis_settings", {})),
        )
