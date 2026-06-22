from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.errors import ParserError

from battery_cycle_analyzer.core.column_mapping import ColumnMapping
from battery_cycle_analyzer.core.data_model import (
    LoadedDataset,
    LoadedDatasetMetadata,
    ValidationIssue,
)
from battery_cycle_analyzer.core.import_config import ImportSettings
from battery_cycle_analyzer.core.tasks import CancellationToken, ProgressCallback, report_progress
from battery_cycle_analyzer.core.validation import DatasetValidator


@dataclass(slots=True)
class CsvPreview:
    path: Path
    rows: list[list[str]]
    labels: dict[int, str]
    units: dict[int, str]

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    def display_label(self, column_index: int) -> str:
        label = self.labels.get(column_index, "").strip()
        unit = self.units.get(column_index, "").strip()
        if label and unit:
            return f"{label} [{unit}]"
        if label:
            return label
        if unit:
            return f"Column {column_index + 1} [{unit}]"
        return f"Column {column_index + 1}"


class CsvImportError(ValueError):
    """Friendly CSV import error with optional technical details."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail or message


class CsvLoader:
    """Loads mapped battery-cycle CSV files into pandas DataFrames.

    The loader has no Qt dependency. The UI can call `preview`, `validate_import`,
    and `load` from dialogs or tests.
    """

    def preview(self, settings: ImportSettings, row_count: int = 50) -> CsvPreview:
        if settings.path is None:
            raise ValueError("ImportSettings.path is required for preview.")
        if not settings.path.exists():
            raise CsvImportError(f"CSV file does not exist: {settings.path}")
        rows: list[list[str]] = []
        try:
            with settings.path.open("r", encoding=settings.encoding, newline="") as handle:
                reader = csv.reader(handle, delimiter=settings.delimiter, strict=True)
                for index, row in enumerate(reader):
                    if index >= row_count:
                        break
                    rows.append(row)
        except UnicodeDecodeError as exc:
            raise CsvImportError(
                "The CSV file could not be decoded with the selected encoding.",
                str(exc),
            ) from exc
        except (OSError, csv.Error) as exc:
            raise CsvImportError("The CSV file could not be read.", str(exc)) from exc
        labels = self._extract_row_from_rows(rows, settings.label_row)
        units = self._extract_row_from_rows(rows, settings.unit_row)
        return CsvPreview(settings.path, rows, labels, units)

    def validate_import(
        self, settings: ImportSettings, mapping: ColumnMapping
    ) -> list[ValidationIssue]:
        try:
            return self.load(settings, mapping).validation_warnings
        except ValueError as exc:
            return [ValidationIssue("import_error", str(exc), "error")]

    def load(
        self,
        settings: ImportSettings,
        mapping: ColumnMapping,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> LoadedDataset:
        self._check_cancel(cancel_token)
        report_progress(progress_callback, 0, "Validating import settings")
        if settings.path is None:
            raise ValueError("ImportSettings.path is required for loading.")
        if not settings.path.exists():
            raise CsvImportError(f"CSV file does not exist: {settings.path}")
        if mapping.time is None:
            raise ValueError("A time column must be selected.")
        if mapping.discharge_energy is None and mapping.charge_energy is None:
            raise ValueError("Select at least one energy column.")

        report_progress(progress_callback, 10, "Reading CSV header rows")
        labels, units, column_count = self._read_header_metadata(settings)
        self._check_cancel(cancel_token)
        resolver = _MetadataColumnResolver(labels, column_count)
        source_indexes = [resolver.resolve_ref(ref) for ref in mapping.selected_refs()]
        output_names = self._output_names(source_indexes, labels)
        source_to_output = dict(zip(source_indexes, output_names))

        role_sources = self._role_sources_from_metadata(resolver, mapping)
        roles = {
            role: source_to_output[source_index]
            for role, source_index in role_sources.items()
            if source_index in source_to_output
        }

        report_progress(progress_callback, 30, "Reading selected CSV columns")
        selected = self._read_selected_columns(settings, source_indexes, output_names)
        self._check_cancel(cancel_token)

        report_progress(progress_callback, 65, "Converting columns")
        issues: list[ValidationIssue] = []
        frame = pd.DataFrame(index=selected.index)
        for source_index, output_name in zip(source_indexes, output_names):
            role = next(
                (role_name for role_name, index in role_sources.items() if index == source_index),
                None,
            )
            series = selected[output_name]
            if role == "time":
                frame[output_name], column_issues = self._coerce_time(
                    series, output_name, settings
                )
            else:
                frame[output_name], column_issues = self._coerce_numeric(
                    series, output_name, settings, required=role is not None
            )
            issues.extend(column_issues)
            self._check_cancel(cancel_token)

        metadata = LoadedDatasetMetadata(
            source_path=settings.path,
            labels={
                name: labels.get(index, f"Column {index + 1}")
                for index, name in zip(source_indexes, output_names)
            },
            units={name: units.get(index, "") for index, name in zip(source_indexes, output_names)},
            source_columns={name: index for index, name in zip(source_indexes, output_names)},
            roles=roles,
            import_rows={
                "label_row": settings.label_row,
                "unit_row": settings.unit_row,
                "first_data_row": settings.first_data_row,
            },
        )
        dataset = LoadedDataset(
            frame=frame,
            metadata=metadata,
            import_settings=settings,
            column_mapping=mapping,
            validation_warnings=issues,
        )
        report_progress(progress_callback, 85, "Validating loaded data")
        dataset.validation_warnings.extend(DatasetValidator().validate(dataset))
        report_progress(progress_callback, 100, "Import complete")
        return dataset

    def likely_numeric_columns(self, settings: ImportSettings) -> list[int]:
        preview = self.preview(settings)
        numeric_columns: list[int] = []
        for index in range(preview.column_count):
            values = [
                row[index] if index < len(row) else ""
                for row in preview.rows[settings.first_data_row :]
            ]
            if self._numeric_ratio(values, settings) >= 0.8:
                numeric_columns.append(index)
        return numeric_columns

    def _read_raw(self, settings: ImportSettings) -> pd.DataFrame:
        if settings.path is None:
            raise ValueError("ImportSettings.path is required for loading.")
        rows: list[list[str]] = []
        with settings.path.open("r", encoding=settings.encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=settings.delimiter)
            rows = [row for row in reader]
        width = max((len(row) for row in rows), default=0)
        padded = [row + [""] * (width - len(row)) for row in rows]
        return pd.DataFrame(padded, dtype=str)

    def _read_header_metadata(
        self, settings: ImportSettings
    ) -> tuple[dict[int, str], dict[int, str], int]:
        preview_rows = max(
            1,
            settings.first_data_row,
            -1 if settings.label_row is None else settings.label_row,
            -1 if settings.unit_row is None else settings.unit_row,
        ) + 1
        preview = self.preview(settings, row_count=preview_rows)
        return preview.labels, preview.units, preview.column_count

    def _read_selected_columns(
        self,
        settings: ImportSettings,
        source_indexes: list[int],
        output_names: list[str],
    ) -> pd.DataFrame:
        na_values = list(settings.missing_markers) if settings.treat_missing_markers_as_nan else None
        try:
            frame = pd.read_csv(
                settings.path,
                sep=settings.delimiter,
                decimal=settings.decimal_separator,
                encoding=settings.encoding,
                header=None,
                skiprows=settings.first_data_row,
                usecols=source_indexes,
                dtype=str,
                na_values=na_values,
                keep_default_na=settings.treat_missing_markers_as_nan,
                engine="python" if settings.delimiter == " " else "c",
                on_bad_lines="error",
            )
        except UnicodeDecodeError as exc:
            raise CsvImportError(
                "The CSV file could not be decoded with the selected encoding.",
                str(exc),
            ) from exc
        except ParserError as exc:
            raise CsvImportError(
                "The CSV file appears to be malformed.",
                str(exc),
            ) from exc
        except ValueError as exc:
            raise CsvImportError(
                "The selected columns could not be read from the CSV file.",
                str(exc),
            ) from exc
        except OSError as exc:
            raise CsvImportError("The CSV file could not be read.", str(exc)) from exc
        frame = frame.loc[:, source_indexes]
        frame.columns = output_names
        return frame.reset_index(drop=True)

    def _extract_row(self, frame: pd.DataFrame, row: int | None) -> dict[int, str]:
        if row is None or row < 0 or row >= len(frame):
            return {}
        return {
            index: str(value).strip()
            for index, value in enumerate(frame.iloc[row].tolist())
            if str(value).strip()
        }

    def _extract_row_from_rows(
        self, rows: list[list[str]], row: int | None
    ) -> dict[int, str]:
        if row is None or row < 0 or row >= len(rows):
            return {}
        return {
            index: value.strip()
            for index, value in enumerate(rows[row])
            if value.strip()
        }

    def _output_names(self, indexes: list[int], labels: dict[int, str]) -> list[str]:
        used: set[str] = set()
        names: list[str] = []
        for index in indexes:
            base = self._clean_column_name(labels.get(index, ""), f"column_{index + 1}")
            name = base
            suffix = 2
            while name in used:
                name = f"{base}_{suffix}"
                suffix += 1
            used.add(name)
            names.append(name)
        return names

    def _role_sources(
        self,
        raw: pd.DataFrame,
        resolver: ColumnResolver,
        mapping: ColumnMapping,
    ) -> dict[str, int]:
        roles: dict[str, int] = {}
        for role_name, ref in {
            "time": mapping.time,
            "discharge_energy": mapping.discharge_energy,
            "charge_energy": mapping.charge_energy,
        }.items():
            if ref is not None:
                roles[role_name] = resolver.resolve(raw, ref)
        return roles

    def _role_sources_from_metadata(
        self,
        resolver: "_MetadataColumnResolver",
        mapping: ColumnMapping,
    ) -> dict[str, int]:
        roles: dict[str, int] = {}
        for role_name, ref in {
            "time": mapping.time,
            "discharge_energy": mapping.discharge_energy,
            "charge_energy": mapping.charge_energy,
        }.items():
            if ref is not None:
                roles[role_name] = resolver.resolve_ref(ref)
        return roles

    def _coerce_time(
        self, series: pd.Series, column_name: str, settings: ImportSettings
    ) -> tuple[pd.Series, list[ValidationIssue]]:
        text = self._normalize_missing(series, settings)
        numeric = self._numeric_series(text, settings)
        non_missing = int(text.notna().sum())
        numeric_valid = int(numeric.notna().sum())
        if non_missing and numeric_valid == non_missing:
            return numeric, []
        if numeric_valid >= 2:
            return numeric, [
                ValidationIssue(
                    "partial_numeric_time",
                    f"Some time values in {column_name} could not be converted to numeric.",
                    "warning",
                    column_name,
                )
            ]

        parsed_datetime = pd.to_datetime(text, errors="coerce")
        datetime_valid = int(parsed_datetime.notna().sum())
        if non_missing and datetime_valid == non_missing:
            return parsed_datetime, []
        if datetime_valid >= 2:
            return parsed_datetime, [
                ValidationIssue(
                    "partial_datetime_time",
                    f"Some time values in {column_name} could not be converted to datetime.",
                    "warning",
                    column_name,
                )
            ]

        return numeric, [
            ValidationIssue(
                "invalid_time_column",
                f"Time column {column_name} cannot be converted to numeric or datetime.",
                "error",
                column_name,
            )
        ]

    def _coerce_numeric(
        self,
        series: pd.Series,
        column_name: str,
        settings: ImportSettings,
        *,
        required: bool,
    ) -> tuple[pd.Series, list[ValidationIssue]]:
        text = self._normalize_missing(series, settings)
        numeric = self._numeric_series(text, settings)
        non_missing = int(text.notna().sum())
        invalid = int((numeric.isna() & text.notna()).sum())
        valid = int(numeric.notna().sum())
        issues: list[ValidationIssue] = []
        if invalid:
            severity = "error" if required and valid == 0 else "warning"
            issues.append(
                ValidationIssue(
                    "non_numeric_values",
                    f"{invalid} values in {column_name} could not be converted to numeric.",
                    severity,
                    column_name,
                )
            )
        if required and non_missing == 0:
            issues.append(
                ValidationIssue(
                    "empty_required_column",
                    f"Required column {column_name} has no data values.",
                    "error",
                    column_name,
                )
            )
        return numeric, issues

    def _normalize_missing(
        self, series: pd.Series, settings: ImportSettings
    ) -> pd.Series:
        text = series.astype(str).str.strip()
        if settings.treat_missing_markers_as_nan:
            markers = {marker.strip() for marker in settings.missing_markers}
            text = text.mask(text.isin(markers))
        return text

    def _numeric_series(self, text: pd.Series, settings: ImportSettings) -> pd.Series:
        normalized = text
        if settings.decimal_separator != ".":
            normalized = normalized.str.replace(settings.decimal_separator, ".", regex=False)
        return pd.to_numeric(normalized, errors="coerce")

    def _numeric_ratio(self, values: list[str], settings: ImportSettings) -> float:
        if not values:
            return 0.0
        series = self._normalize_missing(pd.Series(values), settings)
        non_missing = series.dropna()
        if non_missing.empty:
            return 0.0
        numeric = self._numeric_series(non_missing, settings)
        return float(numeric.notna().sum() / len(non_missing))

    def _clean_column_name(self, label: str, fallback: str) -> str:
        base = label.strip() or fallback
        cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", base).strip("_").lower()
        return cleaned or fallback

    def _check_cancel(self, cancel_token: CancellationToken | None) -> None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()


class _MetadataColumnResolver:
    def __init__(self, labels: dict[int, str], column_count: int) -> None:
        self.labels = labels
        self.column_count = column_count

    def resolve_ref(self, ref) -> int:
        if isinstance(ref, int):
            if ref < 0 or ref >= self.column_count:
                raise ValueError(f"Column index {ref} is outside the CSV range.")
            return ref
        target = str(ref).strip().casefold()
        for index, label in self.labels.items():
            if label.casefold() == target:
                return index
        raise ValueError(f"Column label {ref!r} was not found.")
