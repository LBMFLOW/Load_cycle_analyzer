from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

ColumnRef = int | str
InterpolationMode = Literal["nearest", "linear"]


@dataclass(slots=True)
class ImportWarning:
    code: str
    message: str
    column: str | None = None
    row: int | None = None
    severity: Literal["info", "warning", "error"] = "warning"


@dataclass(slots=True)
class ColumnMapping:
    """User-selected CSV interpretation and semantic column roles.

    Row numbers are zero-based internally. The UI displays them as one-based.
    Column references may be integer source-column indexes or label strings.
    """

    label_row: int | None = 0
    unit_row: int | None = 1
    first_data_row: int = 2
    delimiter: str = ","
    decimal_separator: str = "."
    encoding: str = "utf-8"
    time_column: ColumnRef | None = None
    discharge_energy_column: ColumnRef | None = None
    charge_energy_column: ColumnRef | None = None
    additional_columns: list[ColumnRef] = field(default_factory=list)
    preset_name: str | None = None

    def selected_refs(self) -> list[ColumnRef]:
        refs: list[ColumnRef] = []
        for ref in (
            self.time_column,
            self.discharge_energy_column,
            self.charge_energy_column,
            *self.additional_columns,
        ):
            if ref is not None and ref not in refs:
                refs.append(ref)
        return refs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnMapping":
        return cls(**data)


@dataclass(slots=True)
class DatasetMetadata:
    source_file: str
    labels: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    source_column_indexes: dict[str, int] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    selected_rows: dict[str, int | None] = field(default_factory=dict)
    imported_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(slots=True)
class ImportedDataset:
    frame: pd.DataFrame
    metadata: DatasetMetadata
    mapping: ColumnMapping
    warnings: list[ImportWarning] = field(default_factory=list)

    @property
    def source_path(self) -> Path:
        return Path(self.metadata.source_file)

    @property
    def time_column(self) -> str:
        return self.metadata.roles["time"]

    @property
    def discharge_column(self) -> str | None:
        return self.metadata.roles.get("discharge_energy")

    @property
    def charge_column(self) -> str | None:
        return self.metadata.roles.get("charge_energy")

    @property
    def plottable_columns(self) -> list[str]:
        time_col = self.time_column
        return [
            name
            for name in self.frame.columns
            if name != time_col and pd.api.types.is_numeric_dtype(self.frame[name])
        ]


@dataclass(slots=True)
class Divider:
    id: str
    name: str
    time: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Divider":
        return cls(**data)


@dataclass(slots=True)
class Section:
    id: str
    name: str
    start_time: float | None
    end_time: float | None
    left_divider_id: str | None = None
    right_divider_id: str | None = None
    note: str = ""

    def contains(self, value: float) -> bool:
        left_ok = True if self.start_time is None else value >= self.start_time
        right_ok = True if self.end_time is None else value <= self.end_time
        return left_ok and right_ok

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Section":
        return cls(**data)


@dataclass(slots=True)
class AnalysisSettings:
    interpolation_mode: InterpolationMode = "nearest"
    large_gap_factor: float = 5.0
    smoothing_window: int = 5
    visible_scope: Literal["section", "visible_plot", "whole_dataset"] = (
        "whole_dataset"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisSettings":
        return cls(**data)
