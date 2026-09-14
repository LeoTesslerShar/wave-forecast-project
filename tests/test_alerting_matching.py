from datetime import UTC, datetime, timedelta

from app.alerting.matching import (
    Cluster,
    HourMatch,
    best_cluster,
    cluster_qualifying_hours,
    direction_in_range,
)


def test_direction_range_normal():
    assert direction_in_range(300, 280, 320) is True
    assert direction_in_range(270, 280, 320) is False


def test_direction_range_wraps_across_zero():
    assert direction_in_range(350, 300, 30) is True
    assert direction_in_range(10, 300, 30) is True
    assert direction_in_range(150, 300, 30) is False


def _fake_match(hour_offset: int, qualifies: bool, score: float = 0.7):
    class FakeQuality:
        valid_at = datetime(2026, 1, 1, 6, tzinfo=UTC) + timedelta(hours=hour_offset)
        quality_score = score

    return HourMatch(hour=FakeQuality(), qualifies=qualifies, effective_min_height=None)


def test_contiguous_hours_form_one_cluster():
    matches = [_fake_match(0, True), _fake_match(1, True), _fake_match(2, True)]
    clusters = cluster_qualifying_hours(matches)
    assert len(clusters) == 1
    assert len(clusters[0].hours) == 3


def test_gap_splits_into_separate_clusters():
    matches = [_fake_match(0, True), _fake_match(1, True), _fake_match(2, False), _fake_match(3, True)]
    clusters = cluster_qualifying_hours(matches)
    assert len(clusters) == 2
    assert len(clusters[0].hours) == 2
    assert len(clusters[1].hours) == 1


def test_no_qualifying_hours_produces_no_clusters():
    matches = [_fake_match(0, False), _fake_match(1, False)]
    assert cluster_qualifying_hours(matches) == []


def test_best_cluster_picks_highest_average_score():
    low = Cluster(hours=[_fake_match(0, True, score=0.3)])
    high = Cluster(hours=[_fake_match(5, True, score=0.9)])
    assert best_cluster([low, high]) is high


def test_best_cluster_none_when_no_clusters():
    assert best_cluster([]) is None
