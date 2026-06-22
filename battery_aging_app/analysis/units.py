from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    category: str
    factor_to_base: float
    canonical: str


_UNITS: dict[str, UnitDefinition] = {
    "s": UnitDefinition("time", 1.0, "s"),
    "sec": UnitDefinition("time", 1.0, "s"),
    "second": UnitDefinition("time", 1.0, "s"),
    "seconds": UnitDefinition("time", 1.0, "s"),
    "min": UnitDefinition("time", 60.0, "min"),
    "minute": UnitDefinition("time", 60.0, "min"),
    "minutes": UnitDefinition("time", 60.0, "min"),
    "h": UnitDefinition("time", 3600.0, "h"),
    "hr": UnitDefinition("time", 3600.0, "h"),
    "hour": UnitDefinition("time", 3600.0, "h"),
    "hours": UnitDefinition("time", 3600.0, "h"),
    "d": UnitDefinition("time", 86400.0, "d"),
    "day": UnitDefinition("time", 86400.0, "d"),
    "days": UnitDefinition("time", 86400.0, "d"),
    "wh": UnitDefinition("energy", 1.0, "Wh"),
    "mwh": UnitDefinition("energy", 0.001, "mWh"),
    "kwh": UnitDefinition("energy", 1000.0, "kWh"),
    "j": UnitDefinition("energy", 1.0 / 3600.0, "J"),
    "kj": UnitDefinition("energy", 1000.0 / 3600.0, "kJ"),
    "w": UnitDefinition("power", 1.0, "W"),
    "mw": UnitDefinition("power", 0.001, "mW"),
    "kw": UnitDefinition("power", 1000.0, "kW"),
    "a": UnitDefinition("current", 1.0, "A"),
    "ma": UnitDefinition("current", 0.001, "mA"),
    "v": UnitDefinition("voltage", 1.0, "V"),
    "mv": UnitDefinition("voltage", 0.001, "mV"),
    "ah": UnitDefinition("capacity", 1.0, "Ah"),
    "mah": UnitDefinition("capacity", 0.001, "mAh"),
}


def normalize_unit(unit: str | None) -> str:
    return (unit or "").strip()


def unit_definition(unit: str | None) -> UnitDefinition | None:
    normalized = normalize_unit(unit).replace(" ", "").casefold()
    return _UNITS.get(normalized)


def unit_category(unit: str | None) -> str | None:
    definition = unit_definition(unit)
    return definition.category if definition else None


def compatible_units(from_unit: str | None, to_unit: str | None) -> bool:
    source = unit_definition(from_unit)
    target = unit_definition(to_unit)
    return source is not None and target is not None and source.category == target.category


def convert_values(
    values: Iterable[float] | np.ndarray,
    from_unit: str | None,
    to_unit: str | None,
) -> np.ndarray:
    if normalize_unit(from_unit) == normalize_unit(to_unit):
        return np.asarray(values, dtype=float)
    source = unit_definition(from_unit)
    target = unit_definition(to_unit)
    if source is None:
        raise ValueError(f"Unknown source unit: {from_unit!r}")
    if target is None:
        raise ValueError(f"Unknown target unit: {to_unit!r}")
    if source.category != target.category:
        raise ValueError(
            f"Incompatible unit conversion from {from_unit!r} to {to_unit!r}."
        )
    return np.asarray(values, dtype=float) * source.factor_to_base / target.factor_to_base


def available_units(category: str | None = None) -> list[str]:
    seen: set[str] = set()
    units: list[str] = []
    for definition in _UNITS.values():
        if category is not None and definition.category != category:
            continue
        if definition.canonical not in seen:
            units.append(definition.canonical)
            seen.add(definition.canonical)
    return units
