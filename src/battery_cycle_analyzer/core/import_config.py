from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COMMON_MISSING_MARKERS = ("", "NA", "N/A", "NaN", "nan", "NULL", "null", "-", "--")


@dataclass(slots=True)
class ImportSettings:
    """CSV parser settings selected by the user."""

    path: Path | None = None
    delimiter: str = ","
    decimal_separator: str = "."
    encoding: str = "utf-8"
    label_row: int | None = 0
    unit_row: int | None = 1
    first_data_row: int = 2
    auto_detect_numeric_columns: bool = True
    treat_missing_markers_as_nan: bool = True
    missing_markers: tuple[str, ...] = COMMON_MISSING_MARKERS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path) if self.path is not None else None
        data["missing_markers"] = list(self.missing_markers)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImportSettings":
        values = dict(data)
        values["path"] = Path(values["path"]) if values.get("path") else None
        if "missing_markers" in values:
            values["missing_markers"] = tuple(values["missing_markers"])
        return cls(**values)


@dataclass(slots=True)
class ImportPreset:
    name: str
    settings: ImportSettings
    mapping: dict[str, Any] = field(default_factory=dict)
