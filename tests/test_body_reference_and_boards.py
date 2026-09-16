"""Body-reference scale and board recommendation -- app/quality/body_reference.py,
app/quality/boards.py. Both operate on surf height, display-only, never used in scoring."""
from app.quality.body_reference import classify_body_reference
from app.quality.boards import LONGBOARD, SHORTBOARD, SOFT_TOP, recommend_boards


def test_body_reference_monotonic_bands():
    assert classify_body_reference(None).label == "אין נתונים"
    assert classify_body_reference(0.1).label == "קרסול"
    assert classify_body_reference(0.5).label == "ברך"
    assert classify_body_reference(1.0).label == "מעל מותניים"
    assert classify_body_reference(2.5).label == "מעל הראש"


def test_body_reference_boundaries_are_half_open():
    # Each band's own upper bound belongs to the NEXT band (strict <), not this one.
    assert classify_body_reference(0.29).label == "קרסול"
    assert classify_body_reference(0.30).label == "מעל קרסול"


def test_boards_small_surf_excludes_shortboard():
    rec = recommend_boards(0.3, 6.0)
    assert SHORTBOARD not in rec.boards
    assert LONGBOARD in rec.boards
    assert SOFT_TOP in rec.boards


def test_boards_mid_size_allows_everything():
    rec = recommend_boards(0.9, 7.0)
    assert rec.boards[0] == SHORTBOARD  # best-first
    assert LONGBOARD in rec.boards
    assert SOFT_TOP in rec.boards


def test_boards_big_short_period_shortboard_only():
    """A steep, fast, big day -- too quick for a longboard to turn in time."""
    rec = recommend_boards(1.8, 6.0)
    assert rec.boards == [SHORTBOARD]


def test_boards_big_long_period_still_allows_longboard():
    """Same height, but slow/powerful (long period) -- more time per wave, a longboard is
    still workable even though it's big."""
    rec = recommend_boards(1.8, 10.0)
    assert SHORTBOARD in rec.boards
    assert LONGBOARD in rec.boards


def test_boards_no_data_returns_empty_not_a_crash():
    rec = recommend_boards(None, 8.0)
    assert rec.boards == []
