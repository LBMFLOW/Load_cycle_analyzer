from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

ColumnRef = int | str


@dataclass(slots=True)
class ColumnMapping:
    """User-selected semantic roles for source CSV columns."""

    time: ColumnRef | None = None
    discharge_energy: ColumnRef | None = None
    charge_energy: ColumnRef | None = None
    additional: list[ColumnRef] = field(default_factory=list)

    def selected_refs(self) -> list[ColumnRef]:
        refs: list[ColumnRef] = []
        for ref in [self.time, self.discharge_energy, self.charge_energy, *self.additional]:
            if ref is not None and ref not in refs:
                refs.append(ref)
        return refs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnMapping":
        return cls(**data)


class ColumnResolver:
    """Resolves integer or label references to source DataFrame column indexes."""

    def __init__(self, labels: dict[int, str]) -> None:
        self.labels = labels

    def resolve(self, frame: pd.DataFrame, ref: ColumnRef) -> int:
        if isinstance(ref, int):
            if ref < 0 or ref >= frame.shape[1]:
                raise ValueError(f"Column index {ref} is outside the CSV range.")
            return ref

        target = ref.strip().casefold()
        for index, label in self.labels.items():
            if label.casefold() == target:
                return index
        raise ValueError(f"Column label {ref!r} was not found.")
