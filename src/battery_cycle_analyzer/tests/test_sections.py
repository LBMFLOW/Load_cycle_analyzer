from __future__ import annotations

import numpy as np

from battery_cycle_analyzer.core.sections import SectionManager


def test_sections_from_dividers_and_row_mask() -> None:
    manager = SectionManager()
    dividers = []
    dividers = manager.add_divider(dividers, 10)
    dividers = manager.add_divider(dividers, 20)
    sections = manager.build_sections(
        dividers,
        time_min=0,
        time_max=30,
    )

    assert [(section.start_time, section.end_time) for section in sections] == [
        (0, 10),
        (10, 20),
        (20, 30),
    ]
    assert manager.row_indexes(np.array([0, 10, 15, 20, 25]), sections[1]).tolist() == [1, 2]
    assert manager.row_indexes(np.array([0, 10, 15, 20, 25, 30]), sections[-1]).tolist() == [3, 4, 5]


def test_add_sort_move_and_remove_dividers() -> None:
    manager = SectionManager()
    dividers = manager.add_divider([], 20)
    dividers = manager.add_divider(dividers, 5)
    dividers = manager.add_divider(dividers, 12)

    assert [divider.time_value for divider in dividers] == [5, 12, 20]
    assert [divider.name for divider in dividers] == ["D2", "D3", "D1"]

    moved = manager.move_divider(dividers, dividers[-1].id, 1)
    assert [divider.time_value for divider in moved] == [1, 5, 12]

    removed = manager.remove_divider(moved, moved[1].id)
    assert [divider.time_value for divider in removed] == [1, 12]


def test_select_section_by_click_time() -> None:
    manager = SectionManager()
    dividers = manager.add_divider([], 10)
    dividers = manager.add_divider(dividers, 20)
    values = np.array([0, 10, 15, 20, 25, 30])

    section = manager.section_at_time(dividers, values, 19.9)
    assert section is not None
    assert section.start_time == 10
    assert section.end_time == 20

    final_section = manager.section_at_time(dividers, values, 30)
    assert final_section is not None
    assert final_section.end_inclusive


def test_snap_divider_to_nearest_time_value() -> None:
    manager = SectionManager()
    dividers = manager.add_divider([], 13)
    snapped = manager.snap_divider(dividers, dividers[0].id, np.array([0, 10, 20]))

    assert snapped[0].time_value == 10


def test_non_monotonic_and_duplicate_time_rows_are_value_masked() -> None:
    manager = SectionManager()
    dividers = manager.add_divider([], 10)
    dividers = manager.add_divider(dividers, 20)
    section = manager.sections_for_time_values(dividers, np.array([20, 0, 10, 10, 30]))[1]

    assert manager.row_indexes(np.array([20, 0, 10, 10, 30]), section).tolist() == [2, 3]
