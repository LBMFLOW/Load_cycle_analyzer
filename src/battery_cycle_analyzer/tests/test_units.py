from __future__ import annotations

import numpy as np
import pytest

from battery_cycle_analyzer.core.units import are_compatible, convert


def test_unit_conversion() -> None:
    assert convert(np.array([3600.0]), "s", "h")[0] == pytest.approx(1.0)
    assert convert(np.array([1.0]), "kWh", "Wh")[0] == pytest.approx(1000.0)
    assert are_compatible("Wh", "J")
    assert not are_compatible("Wh", "A")
