from __future__ import annotations

from uuid import uuid4

import numpy as np

from battery_aging_app.models import Divider, Section


def new_divider(time_value: float, name: str | None = None) -> Divider:
    identifier = uuid4().hex
    return Divider(
        id=identifier,
        name=name or f"Divider {identifier[:6]}",
        time=float(time_value),
    )


def build_sections(
    dividers: list[Divider],
    *,
    time_min: float | None,
    time_max: float | None,
) -> list[Section]:
    ordered = sorted(dividers, key=lambda divider: divider.time)
    sections: list[Section] = []
    left_time: float | None = time_min
    left_id: str | None = None

    if not ordered:
        return [
            Section(
                id="section:all",
                name="Whole dataset",
                start_time=time_min,
                end_time=time_max,
            )
        ]

    for index, divider in enumerate(ordered):
        sections.append(
            Section(
                id=f"section:{left_id or 'start'}:{divider.id}",
                name="Before first divider" if index == 0 else f"Section {index}",
                start_time=left_time,
                end_time=divider.time,
                left_divider_id=left_id,
                right_divider_id=divider.id,
            )
        )
        left_time = divider.time
        left_id = divider.id

    sections.append(
        Section(
            id=f"section:{left_id}:end",
            name="After last divider",
            start_time=left_time,
            end_time=time_max,
            left_divider_id=left_id,
        )
    )
    if len(sections) > 2:
        for index, section in enumerate(sections[1:-1], start=1):
            section.name = f"Section {index}"
    return sections


def section_for_time(sections: list[Section], time_value: float) -> Section | None:
    for section in sections:
        if section.contains(float(time_value)):
            return section
    return None


def section_mask(time_values: np.ndarray, section: Section) -> np.ndarray:
    time = np.asarray(time_values, dtype=float)
    mask = ~np.isnan(time)
    if section.start_time is not None:
        mask &= time >= section.start_time
    if section.end_time is not None:
        mask &= time <= section.end_time
    return mask


def row_indexes_for_section(time_values: np.ndarray, section: Section) -> np.ndarray:
    return np.flatnonzero(section_mask(time_values, section))
