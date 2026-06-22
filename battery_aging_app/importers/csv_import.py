from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from battery_aging_app.analysis.cleaning import analyze_data_quality
from battery_aging_app.models import (
    ColumnMapping,
    ColumnRef,
    DatasetMetadata,
    ImportedDataset,
    ImportWarning,
)


@dataclass(slots=True)
class CsvPreview:
    path: Path
    rows: list[list[str]]
    delimiter: str
    encoding: str

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)


def preview_csv(
    path: str | Path,
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
    row_count: int = 40,
) -> CsvPreview:
    csv_path = Path(path)
    rows: list[list[str]] = []
    with csv_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for idx, row in enumerate(reader):
            if idx >= row_count:
                break
            rows.append(row)
    return CsvPreview(csv_path, rows, delimiter, encoding)


def read_battery_csv(path: str | Path, mapping: ColumnMapping) -> ImportedDataset:
    csv_path = Path(path)
    raw = pd.read_csv(
        csv_path,
        sep=mapping.delimiter,
        encoding=mapping.encoding,
        header=None,
        dtype=str,
        engine="python",
        keep_default_na=False,
    )

    labels = _extract_row(raw, mapping.label_row)
    units = _extract_row(raw, mapping.unit_row)

    selected_indexes = _resolve_selected_indexes(raw, labels, mapping)
    if mapping.time_column is None:
        raise ValueError("A time column must be selected before import.")
    if not selected_indexes:
        raise ValueError("No columns were selected for import.")

    source_to_output: dict[int, str] = {}
    used_names: set[str] = set()
    for source_index in selected_indexes:
        preferred = labels.get(source_index) or f"Column {source_index + 1}"
        source_to_output[source_index] = _unique_name(preferred, used_names)

    data = raw.iloc[mapping.first_data_row :, selected_indexes].copy()
    data.columns = [source_to_output[index] for index in selected_indexes]
    data = data.reset_index(drop=True)

    warnings: list[ImportWarning] = []
    for output_name in data.columns:
        numeric, column_warnings = _coerce_numeric(
            data[output_name],
            output_name,
            decimal_separator=mapping.decimal_separator,
            first_data_row=mapping.first_data_row,
        )
        data[output_name] = numeric
        warnings.extend(column_warnings)

    roles = _build_roles(mapping, labels, source_to_output, raw)
    metadata = DatasetMetadata(
        source_file=str(csv_path),
        labels={name: labels.get(index, name) for index, name in source_to_output.items()},
        units={name: units.get(index, "") for index, name in source_to_output.items()},
        source_column_indexes={name: index for index, name in source_to_output.items()},
        roles=roles,
        selected_rows={
            "label_row": mapping.label_row,
            "unit_row": mapping.unit_row,
            "first_data_row": mapping.first_data_row,
        },
    )

    dataset = ImportedDataset(data, metadata, mapping, warnings)
    dataset.warnings.extend(analyze_data_quality(dataset))
    return dataset


def batch_read_battery_csv(
    paths: Iterable[str | Path], mapping: ColumnMapping
) -> list[ImportedDataset]:
    return [read_battery_csv(path, mapping) for path in paths]


def _extract_row(raw: pd.DataFrame, row_index: int | None) -> dict[int, str]:
    if row_index is None or row_index < 0 or row_index >= len(raw):
        return {}
    values: dict[int, str] = {}
    for index, value in enumerate(raw.iloc[row_index].tolist()):
        text = "" if value is None else str(value).strip()
        if text:
            values[index] = text
    return values


def _resolve_selected_indexes(
    raw: pd.DataFrame, labels: dict[int, str], mapping: ColumnMapping
) -> list[int]:
    indexes: list[int] = []
    for ref in mapping.selected_refs():
        index = resolve_column_ref(raw, labels, ref)
        if index not in indexes:
            indexes.append(index)
    return indexes


def resolve_column_ref(
    raw: pd.DataFrame, labels: dict[int, str], ref: ColumnRef
) -> int:
    if isinstance(ref, int):
        if ref < 0 or ref >= raw.shape[1]:
            raise ValueError(f"Column index {ref} is outside the CSV range.")
        return ref

    normalized = ref.strip().casefold()
    for index, label in labels.items():
        if label.casefold() == normalized:
            return index

    if normalized.startswith("column "):
        try:
            one_based = int(normalized.split(" ", 1)[1])
        except ValueError:
            pass
        else:
            return resolve_column_ref(raw, labels, one_based - 1)

    raise ValueError(f"Column label {ref!r} was not found in the CSV.")


def _coerce_numeric(
    series: pd.Series,
    column_name: str,
    *,
    decimal_separator: str,
    first_data_row: int,
) -> tuple[pd.Series, list[ImportWarning]]:
    text = series.astype(str).str.strip()
    missing_mask = text.eq("")
    if decimal_separator != ".":
        text = text.str.replace(decimal_separator, ".", regex=False)
    text = text.str.replace("\u00a0", "", regex=False)
    numeric = pd.to_numeric(text.mask(missing_mask), errors="coerce")

    non_numeric_mask = numeric.isna() & ~missing_mask
    warnings: list[ImportWarning] = []
    for row_index in non_numeric_mask[non_numeric_mask].index.tolist()[:20]:
        warnings.append(
            ImportWarning(
                code="non_numeric_cell",
                message=f"Non-numeric value in column {column_name}.",
                column=column_name,
                row=int(row_index) + first_data_row,
            )
        )
    if non_numeric_mask.sum() > 20:
        warnings.append(
            ImportWarning(
                code="non_numeric_cell_summary",
                message=(
                    f"{int(non_numeric_mask.sum())} non-numeric values were found "
                    f"in column {column_name}."
                ),
                column=column_name,
            )
        )
    return numeric, warnings


def _build_roles(
    mapping: ColumnMapping,
    labels: dict[int, str],
    source_to_output: dict[int, str],
    raw: pd.DataFrame,
) -> dict[str, str]:
    roles: dict[str, str] = {}
    role_refs = {
        "time": mapping.time_column,
        "discharge_energy": mapping.discharge_energy_column,
        "charge_energy": mapping.charge_energy_column,
    }
    for role, ref in role_refs.items():
        if ref is None:
            continue
        index = resolve_column_ref(raw, labels, ref)
        if index in source_to_output:
            roles[role] = source_to_output[index]
    return roles


def _unique_name(name: str, used_names: set[str]) -> str:
    cleaned = name.strip() or "Column"
    candidate = cleaned
    suffix = 2
    while candidate in used_names:
        candidate = f"{cleaned} ({suffix})"
        suffix += 1
    used_names.add(candidate)
    return candidate
