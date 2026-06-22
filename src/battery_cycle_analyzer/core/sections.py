from __future__ import annotations

from uuid import uuid4

import numpy as np
import pandas as pd

from battery_cycle_analyzer.core.data_model import Divider, Section


class SectionManager:
    """Pure divider and section logic.

    Section masks use value-based time boundaries rather than row numbers, so
    duplicate timestamps, non-monotonic rows, and filtered datasets still map
    correctly to the underlying DataFrame rows.
    """

    def create_divider(self, time_value: float, name: str | None = None) -> Divider:
        divider_id = uuid4().hex
        return Divider(divider_id, name or "D1", float(time_value))

    def add_divider(
        self,
        dividers: list[Divider],
        time_value: float,
        *,
        name: str | None = None,
    ) -> list[Divider]:
        next_name = name or f"D{len(dividers) + 1}"
        return self.sorted_dividers(
            [*dividers, Divider(uuid4().hex, next_name, float(time_value))]
        )

    def sorted_dividers(self, dividers: list[Divider]) -> list[Divider]:
        return sorted(dividers, key=lambda item: (item.time_value, item.name, item.id))

    def move_divider(
        self,
        dividers: list[Divider],
        divider_id: str,
        time_value: float,
    ) -> list[Divider]:
        updated: list[Divider] = []
        for divider in dividers:
            if divider.id == divider_id:
                updated.append(
                    Divider(
                        id=divider.id,
                        name=divider.name,
                        time_value=float(time_value),
                        note=divider.note,
                    )
                )
            else:
                updated.append(divider)
        return self.sorted_dividers(updated)

    def remove_divider(self, dividers: list[Divider], divider_id: str) -> list[Divider]:
        return self.sorted_dividers([item for item in dividers if item.id != divider_id])

    def rename_divider(
        self, dividers: list[Divider], divider_id: str, name: str
    ) -> list[Divider]:
        for divider in dividers:
            if divider.id == divider_id:
                divider.name = name
                break
        return self.sorted_dividers(dividers)

    def note_divider(
        self, dividers: list[Divider], divider_id: str, note: str
    ) -> list[Divider]:
        for divider in dividers:
            if divider.id == divider_id:
                divider.note = note
                break
        return self.sorted_dividers(dividers)

    def snap_divider(
        self,
        dividers: list[Divider],
        divider_id: str,
        time_values: pd.Series | np.ndarray,
    ) -> list[Divider]:
        divider = next((item for item in dividers if item.id == divider_id), None)
        if divider is None:
            return self.sorted_dividers(dividers)
        nearest = self.nearest_time_value(time_values, divider.time_value)
        if nearest is None:
            return self.sorted_dividers(dividers)
        return self.move_divider(dividers, divider_id, nearest)

    def nearest_time_value(
        self, time_values: pd.Series | np.ndarray, target: float
    ) -> float | None:
        values = self._values(time_values)
        valid = values[~np.isnan(values)]
        if valid.size == 0:
            return None
        return float(valid[int(np.argmin(np.abs(valid - float(target))))])

    def build_sections(
        self,
        dividers: list[Divider],
        *,
        time_min: float | None,
        time_max: float | None,
    ) -> list[Section]:
        ordered = self.sorted_dividers(dividers)
        if not ordered:
            return [
                Section(
                    "section:all",
                    "Whole dataset",
                    time_min,
                    time_max,
                    end_inclusive=True,
                )
            ]

        sections: list[Section] = []
        left_time = time_min
        left_id: str | None = None
        for index, divider in enumerate(ordered):
            sections.append(
                Section(
                    id=f"section:{left_id or 'start'}:{divider.id}",
                    name="Before first divider" if index == 0 else f"Section {index}",
                    start_time=left_time,
                    end_time=divider.time_value,
                    left_divider_id=left_id,
                    right_divider_id=divider.id,
                    end_inclusive=False,
                )
            )
            left_time = divider.time_value
            left_id = divider.id

        sections.append(
            Section(
                id=f"section:{left_id}:end",
                name="After last divider",
                start_time=left_time,
                end_time=time_max,
                left_divider_id=left_id,
                end_inclusive=True,
            )
        )
        return sections

    def sections_for_time_values(
        self, dividers: list[Divider], time_values: pd.Series | np.ndarray
    ) -> list[Section]:
        values = self._values(time_values)
        valid = values[~np.isnan(values)]
        return self.build_sections(
            dividers,
            time_min=float(valid.min()) if valid.size else None,
            time_max=float(valid.max()) if valid.size else None,
        )

    def section_at_time(
        self, dividers: list[Divider], time_values: pd.Series | np.ndarray, click_time: float
    ) -> Section | None:
        for section in self.sections_for_time_values(dividers, time_values):
            if section.contains(float(click_time)):
                return section
        return None

    def mask(self, time_values: pd.Series | np.ndarray, section: Section | None) -> np.ndarray:
        time = self._values(time_values)
        mask = ~np.isnan(time)
        if section is None:
            return mask
        if section.start_time is not None:
            mask &= time >= section.start_time
        if section.end_time is not None:
            if section.end_inclusive:
                mask &= time <= section.end_time
            else:
                mask &= time < section.end_time
        return mask

    def row_indexes(self, time_values: pd.Series | np.ndarray, section: Section) -> np.ndarray:
        return np.flatnonzero(self.mask(time_values, section))

    def _values(self, time_values: pd.Series | np.ndarray) -> np.ndarray:
        if isinstance(time_values, pd.Series) and pd.api.types.is_datetime64_any_dtype(
            time_values
        ):
            datetime = pd.to_datetime(time_values, errors="coerce")
            valid = datetime.dropna()
            if valid.empty:
                return np.full(len(time_values), np.nan, dtype=float)
            return (datetime - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return np.asarray(time_values, dtype=float)
