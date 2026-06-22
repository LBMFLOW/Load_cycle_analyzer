from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from battery_cycle_analyzer import __version__
from battery_cycle_analyzer.core.data_model import (
    Divider,
    IntegrationResult,
    LoadedDataset,
    Section,
)
from battery_cycle_analyzer.core.sections import SectionManager

RelativeTimeUnit = Literal["seconds", "minutes", "hours", "days"]

_RELATIVE_TIME_UNITS: dict[RelativeTimeUnit, tuple[str, float]] = {
    "seconds": ("s", 1.0),
    "minutes": ("min", 60.0),
    "hours": ("h", 3600.0),
    "days": ("d", 86400.0),
}

_SOURCE_TIME_FACTORS: dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
}


@dataclass(slots=True)
class SectionExportOptions:
    """User-selectable options for saving a selected section."""

    include_all_columns: bool = False
    include_visible_curves: bool = True
    include_metadata_comments: bool = True
    create_sidecar_json: bool = True
    relative_time_unit: RelativeTimeUnit = "seconds"


@dataclass(slots=True)
class SectionExportPayload:
    """Prepared section export data before it is written to disk."""

    frame: pd.DataFrame
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    exported_columns: list[str] = field(default_factory=list)

    @property
    def point_count(self) -> int:
        return len(self.frame)


@dataclass(slots=True)
class SectionExportResult:
    output_path: Path
    metadata_path: Path | None
    point_count: int
    warnings: list[str] = field(default_factory=list)
    exported_columns: list[str] = field(default_factory=list)


class SectionExportError(ValueError):
    """Raised when a selected section cannot be exported."""

    def __init__(self, message: str, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.warnings = warnings or [message]


class ExportService:
    """Exports processed data and analysis artifacts."""

    def prepare_section_export(
        self,
        dataset: LoadedDataset,
        section: Section,
        curve_columns: list[str],
        *,
        options: SectionExportOptions | None = None,
        axis_values=None,
        axis_unit: str | None = None,
        dividers: list[Divider] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> SectionExportPayload:
        options = options or SectionExportOptions()
        frame = dataset.frame
        time_column = dataset.time_column
        mask_source = axis_values if axis_values is not None else frame[time_column]
        mask = SectionManager().mask(mask_source, section)
        row_indexes = np.flatnonzero(mask)

        internal_columns = self._selected_columns(
            dataset,
            curve_columns,
            include_all_columns=options.include_all_columns,
            include_visible_curves=options.include_visible_curves,
        )
        section_frame = frame.iloc[row_indexes][internal_columns].copy()
        display_columns = self._display_columns(dataset, internal_columns)
        section_frame.columns = display_columns

        relative_unit_label, relative_values = self._relative_time(
            dataset,
            row_indexes,
            axis_values=axis_values,
            axis_unit=axis_unit,
            relative_time_unit=options.relative_time_unit,
        )
        relative_column = f"Relative Time [{relative_unit_label}]"
        section_frame.insert(0, relative_column, relative_values)

        warnings = self._section_warnings(section_frame)
        selected_curve_columns = [
            column for column in curve_columns if column in internal_columns
        ]
        metadata = self._section_metadata(
            dataset,
            section,
            selected_curve_columns,
            internal_columns,
            display_columns,
            row_indexes,
            options,
            relative_column,
            dividers=dividers,
            annotations=annotations,
        )
        return SectionExportPayload(
            frame=section_frame,
            metadata=metadata,
            warnings=warnings,
            exported_columns=[relative_column, *display_columns],
        )

    def write_section_export(
        self,
        payload: SectionExportPayload,
        output_path: Path,
        *,
        options: SectionExportOptions | None = None,
    ) -> SectionExportResult:
        options = options or SectionExportOptions()
        if payload.frame.empty:
            raise SectionExportError("Selected section is empty.", payload.warnings)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            if options.include_metadata_comments:
                for line in self._metadata_comment_lines(payload.metadata):
                    handle.write(f"# {line}\n")
            payload.frame.to_csv(handle, index=False)

        metadata_path: Path | None = None
        if options.create_sidecar_json:
            metadata_path = output_path.with_suffix(".metadata.json")
            metadata_path.write_text(
                json.dumps(payload.metadata, indent=2, default=str),
                encoding="utf-8",
            )

        return SectionExportResult(
            output_path=output_path,
            metadata_path=metadata_path,
            point_count=payload.point_count,
            warnings=payload.warnings,
            exported_columns=payload.exported_columns,
        )

    def section_csv(
        self,
        dataset: LoadedDataset,
        section: Section,
        curve_columns: list[str],
        output_path: Path,
        *,
        options: SectionExportOptions | None = None,
        axis_values=None,
        axis_unit: str | None = None,
        dividers: list[Divider] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> Path:
        payload = self.prepare_section_export(
            dataset,
            section,
            curve_columns,
            options=options,
            axis_values=axis_values,
            axis_unit=axis_unit,
            dividers=dividers,
            annotations=annotations,
        )
        self.write_section_export(payload, output_path, options=options)
        return output_path

    def processed_dataset_csv(self, frame: pd.DataFrame, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_path, index=False)
        return output_path

    def integration_summary_csv(
        self, results: list[IntegrationResult], output_path: Path
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "curve": result.curve_name,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "point_count": result.point_count,
                    "integral": result.value,
                    "unit": result.result_unit,
                }
                for result in results
            ]
        ).to_csv(output_path, index=False)
        return output_path

    def metadata_json(
        self,
        dataset: LoadedDataset,
        section: Section | None,
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "dataset": dataset.metadata.to_jsonable(),
                    "section": section.to_dict() if section else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return output_path

    def _selected_columns(
        self,
        dataset: LoadedDataset,
        curve_columns: list[str],
        *,
        include_all_columns: bool,
        include_visible_curves: bool,
    ) -> list[str]:
        if include_all_columns:
            return list(dataset.frame.columns)

        columns = [dataset.time_column]
        if include_visible_curves:
            columns.extend(column for column in curve_columns if column in dataset.frame.columns)
        return self._unique(columns)

    def _display_columns(
        self, dataset: LoadedDataset, internal_columns: list[str]
    ) -> list[str]:
        display = [
            self._display_name(
                dataset.metadata.labels.get(column, column),
                dataset.metadata.units.get(column, ""),
            )
            for column in internal_columns
        ]
        return self._unique_display_names(display)

    def _relative_time(
        self,
        dataset: LoadedDataset,
        row_indexes: np.ndarray,
        *,
        axis_values,
        axis_unit: str | None,
        relative_time_unit: RelativeTimeUnit,
    ) -> tuple[str, np.ndarray]:
        unit_label, target_factor = _RELATIVE_TIME_UNITS[relative_time_unit]
        if row_indexes.size == 0:
            return unit_label, np.array([], dtype=float)

        if axis_values is not None:
            numeric_axis = np.asarray(axis_values, dtype=float)
            source_unit = axis_unit or dataset.metadata.units.get(dataset.time_column, "s")
        else:
            time_series = dataset.frame[dataset.time_column]
            numeric_axis = self._numeric_time_values(time_series)
            if pd.api.types.is_datetime64_any_dtype(time_series):
                source_unit = "s"
            else:
                source_unit = dataset.metadata.units.get(dataset.time_column, "s")

        selected = numeric_axis[row_indexes].astype(float)
        relative = selected - float(selected[0])
        source_factor = self._source_time_factor(source_unit)
        return unit_label, relative * source_factor / target_factor

    def _numeric_time_values(self, series: pd.Series) -> np.ndarray:
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime = pd.to_datetime(series, errors="coerce")
            valid = datetime.dropna()
            if valid.empty:
                return np.full(len(series), np.nan, dtype=float)
            return (datetime - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)

    def _source_time_factor(self, unit: str | None) -> float:
        normalized = (unit or "s").strip().casefold()
        return _SOURCE_TIME_FACTORS.get(normalized, 1.0)

    def _section_warnings(self, frame: pd.DataFrame) -> list[str]:
        if frame.empty:
            return ["Selected section is empty."]
        if len(frame) < 2:
            return ["Selected section contains fewer than 2 points."]
        return []

    def _section_metadata(
        self,
        dataset: LoadedDataset,
        section: Section,
        selected_curve_columns: list[str],
        internal_columns: list[str],
        display_columns: list[str],
        row_indexes: np.ndarray,
        options: SectionExportOptions,
        relative_column: str,
        *,
        dividers: list[Divider] | None,
        annotations: dict[str, Any] | None,
    ) -> dict[str, Any]:
        import_rows = dataset.metadata.import_rows
        selected_curve_names = [
            self._display_name(
                dataset.metadata.labels.get(column, column),
                dataset.metadata.units.get(column, ""),
            )
            for column in selected_curve_columns
        ]
        column_metadata = {
            display: {
                "internal_name": internal,
                "label": dataset.metadata.labels.get(internal, internal),
                "unit": dataset.metadata.units.get(internal, ""),
                "source_column": dataset.metadata.source_columns.get(internal),
            }
            for internal, display in zip(internal_columns, display_columns)
        }
        column_metadata[relative_column] = {
            "internal_name": "relative_time",
            "label": "Relative Time",
            "unit": _RELATIVE_TIME_UNITS[options.relative_time_unit][0],
            "source_column": None,
        }

        divider_notes = [
            divider.to_dict()
            for divider in dividers or []
            if divider.note
            and divider.id in {section.left_divider_id, section.right_divider_id}
        ]

        return {
            "source_csv_path": str(dataset.metadata.source_path),
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "parameter_label_row": import_rows.get("label_row"),
            "unit_row": import_rows.get("unit_row"),
            "first_data_row": import_rows.get("first_data_row"),
            "section_name": section.name,
            "section_id": section.id,
            "section_start_time": section.start_time,
            "section_end_time": section.end_time,
            "section_end_inclusive": section.end_inclusive,
            "number_of_points": int(row_indexes.size),
            "selected_curve_names": selected_curve_names,
            "units": dict(dataset.metadata.units),
            "column_metadata": column_metadata,
            "exported_columns": [relative_column, *display_columns],
            "software_version": __version__,
            "notes": {
                "section": section.note,
                "bordering_dividers": divider_notes,
                "annotations": annotations or {},
            },
        }

    def _metadata_comment_lines(self, metadata: dict[str, Any]) -> list[str]:
        compact_keys = [
            "source_csv_path",
            "export_timestamp",
            "parameter_label_row",
            "unit_row",
            "first_data_row",
            "section_name",
            "section_start_time",
            "section_end_time",
            "number_of_points",
            "selected_curve_names",
            "units",
            "software_version",
        ]
        lines: list[str] = []
        for key in compact_keys:
            value = metadata.get(key)
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, default=str)
            else:
                rendered = "" if value is None else str(value)
            lines.append(f"{key}: {rendered}")
        return lines

    def _display_name(self, label: str, unit: str) -> str:
        clean_label = label.strip()
        clean_unit = unit.strip()
        return f"{clean_label} [{clean_unit}]" if clean_unit else clean_label

    def _unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                unique_values.append(value)
        return unique_values

    def _unique_display_names(self, values: list[str]) -> list[str]:
        counts: dict[str, int] = {}
        result: list[str] = []
        for value in values:
            count = counts.get(value, 0) + 1
            counts[value] = count
            result.append(value if count == 1 else f"{value} ({count})")
        return result
