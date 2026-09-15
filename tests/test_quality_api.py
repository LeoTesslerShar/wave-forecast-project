"""API-level quality tests -- prompts/phase-3-quality.md acceptance checks 3, 5."""
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.api.beaches import beach_quality
from app.models import Beach, Forecast
from app.schemas import QualityConfidence


async def _seed(
    db_session, *, beach_id="herzliya", wind_dir_offset=180, wind_speed=8, gusts=10, wave_peak_period=None
):
    beach = Beach(id=beach_id, name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add(beach)
    await db_session.commit()

    valid_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    issued_at = datetime.now(UTC)
    db_session.add(
        Forecast(
            beach_id=beach.id,
            issued_at=issued_at,
            valid_at=valid_at,
            wave_height=1.3,
            wave_direction=300.0,
            wave_period=6.5,  # mean period (Tm) -- deliberately lower than a plausible Tp
            wave_peak_period=wave_peak_period,
            swell_wave_height=1.2,
            swell_wave_direction=300.0,
            wind_wave_height=0.15,
            wind_speed_10m=wind_speed,
            wind_direction_10m=(301.1 + wind_dir_offset) % 360,
            wind_gusts_10m=gusts,
            fetched_at=issued_at,
        )
    )
    await db_session.commit()
    return beach, valid_at


async def test_quality_response_has_every_component_and_verdict(db_session):
    beach, _ = await _seed(db_session)

    out = await beach_quality(beach.id, hours=6, session=db_session)
    assert len(out) >= 1
    row = out[0]

    # Acceptance check 3: every component individually visible, plus the combined verdict.
    assert row.size.wave_height_estimate is not None
    assert row.size.wave_height_range is not None
    assert row.period_s is not None
    assert row.period_band in ("weak", "workable", "good", "unknown")
    assert row.wind.speed_kmh is not None
    assert row.wind.relation_to_shore in ("onshore", "cross-shore", "offshore", "glassy", "unknown")
    assert row.chop_ratio is not None
    assert row.chop_band in ("clean", "mixed", "choppy", "unknown")
    assert row.quality_verdict in ("flat", "poor", "fair", "good", "excellent")
    assert row.quality_reasoning
    assert row.swell_direction_deg == 300.0
    assert 0.0 <= row.quality_score <= 10.0  # scale, not the old 0..1

    # confidence markers throughout
    assert row.confidence.size == "unvalidated_heuristic"
    assert row.confidence.wind == "measured_forecast"
    assert row.confidence.quality_verdict == "unvalidated_heuristic"
    # No peak period seeded here -- falls back to the mean period, and must say so plainly
    # rather than presenting mean and peak period as interchangeable (docs/DECISIONS.md).
    assert row.period_s == 6.5
    assert "substituted_mean_period_tm" in row.confidence.period
    assert "LOW" in row.confidence.period


async def test_peak_period_preferred_over_mean_period_when_available(db_session):
    """Regression test for the Tm/Tp mixup (docs/DECISIONS.md): a real peak period, when
    present, must be what period_s and period_band are computed from -- not the mean
    period, which runs meaningfully lower and would silently under-rate the day."""
    beach, _ = await _seed(db_session, wave_peak_period=9.0)

    out = await beach_quality(beach.id, hours=6, session=db_session)
    row = out[0]

    assert row.period_s == 9.0  # the peak period, not the 6.5s mean period seeded alongside it
    assert "~" in row.confidence.period  # e.g. "measured_peak_period_tp ~1s"
    assert "measured_peak_period_tp" in row.confidence.period
    assert row.period_band == "good"  # 9.0s clears GOOD_PERIOD_S; 6.5s would not


async def test_offshore_wind_scores_better_than_onshore_same_swell(db_session):
    onshore_beach, valid_at = await _seed(
        db_session, beach_id="herzliya_onshore", wind_dir_offset=0, wind_speed=15, gusts=18
    )
    onshore_out = await beach_quality(onshore_beach.id, hours=1, session=db_session)

    offshore_beach, _ = await _seed(
        db_session, beach_id="herzliya_offshore", wind_dir_offset=180, wind_speed=8, gusts=10
    )
    offshore_out = await beach_quality(offshore_beach.id, hours=1, session=db_session)

    assert offshore_out[0].quality_score > onshore_out[0].quality_score


def test_no_quality_confidence_ever_marks_verdict_as_validated():
    """Acceptance check 5."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    pattern = re.compile(r"QualityConfidence\([^)]*quality_verdict\s*=(?!\s*\"unvalidated_heuristic\")")
    offending = [str(p) for p in app_dir.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offending == [], f"quality_verdict confidence overridden away from unvalidated in: {offending}"
    assert QualityConfidence(period="x").quality_verdict == "unvalidated_heuristic"
    assert QualityConfidence(period="x").size == "unvalidated_heuristic"
