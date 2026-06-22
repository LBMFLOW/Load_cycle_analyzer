from __future__ import annotations

import numpy as np
import pytest

from battery_aging_app.analysis.units import compatible_units, convert_values, unit_category


def test_time_unit_conversion() -> None:
    converted = convert_values(np.array([0.0, 60.0, 120.0]), "s", "min")
    assert converted.tolist() == [0.0, 1.0, 2.0]


def test_energy_unit_conversion() -> None:
    assert convert_values([1.5], "kWh", "Wh")[0] == pytest.approx(1500.0)
    assert unit_category("mAh") == "capacity"
    assert compatible_units("Wh", "kWh")
    assert not compatible_units("Wh", "A")


def test_incompatible_units_raise() -> None:
    with pytest.raises(ValueError):
        convert_values([1.0], "Wh", "s")
