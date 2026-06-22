from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Unit:
    category: str
    factor_to_base: float


UNITS: dict[str, Unit] = {
    "s": Unit("time", 1.0),
    "min": Unit("time", 60.0),
    "h": Unit("time", 3600.0),
    "Wh": Unit("energy", 1.0),
    "mWh": Unit("energy", 0.001),
    "kWh": Unit("energy", 1000.0),
    "J": Unit("energy", 1.0 / 3600.0),
    "W": Unit("power", 1.0),
    "mW": Unit("power", 0.001),
    "kW": Unit("power", 1000.0),
    "A": Unit("current", 1.0),
    "mA": Unit("current", 0.001),
    "V": Unit("voltage", 1.0),
    "mV": Unit("voltage", 0.001),
    "Ah": Unit("capacity", 1.0),
    "mAh": Unit("capacity", 0.001),
}


def normalize_unit(unit: str | None) -> str:
    return (unit or "").strip()


def get_unit(unit: str | None) -> Unit | None:
    normalized = normalize_unit(unit)
    if normalized in UNITS:
        return UNITS[normalized]
    folded = normalized.casefold()
    for name, definition in UNITS.items():
        if name.casefold() == folded:
            return definition
    return None


def are_compatible(source_unit: str | None, target_unit: str | None) -> bool:
    source = get_unit(source_unit)
    target = get_unit(target_unit)
    return source is not None and target is not None and source.category == target.category


def convert(values: np.ndarray, source_unit: str, target_unit: str) -> np.ndarray:
    source = get_unit(source_unit)
    target = get_unit(target_unit)
    if source is None:
        raise ValueError(f"Unknown unit: {source_unit!r}")
    if target is None:
        raise ValueError(f"Unknown unit: {target_unit!r}")
    if source.category != target.category:
        raise ValueError(f"Cannot convert {source_unit!r} to {target_unit!r}.")
    return np.asarray(values, dtype=float) * source.factor_to_base / target.factor_to_base
