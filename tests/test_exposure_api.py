"""API-level exposure tests -- prompts/phase-2-exposure.md acceptance checks 4-5."""
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.api.beaches import beach_exposure, ranked_conditions
from app.models import Beach, Forecast
from app.schemas import ExposureConfidence


async def _seed(db_session):
    bat_yam = Beach(id="bat_yam", name="Bat Yam", lat=32.0133, lon=34.7432, shoreline_bearing=284.6)
    herzliya = Beach(id="herzliya", name="Herzliya", lat=32.1660, lon=34.7960, shoreline_bearing=301.1)
    db_session.add_all([bat_yam, herzliya])
    await db_session.commit()

    valid_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    issued_at = datetime.now(UTC)
    for beach in (bat_yam, herzliya):
        db_session.add(
            Forecast(
                beach_id=beach.id,
                issued_at=issued_at,
                valid_at=valid_at,
                wave_height=1.5,
                wave_direction=300.0,
                swell_wave_height=1.4,
                swell_wave_direction=300.0,
                fetched_at=issued_at,
            )
        )
    await db_session.commit()
    return bat_yam, herzliya, valid_at


async def test_beach_exposure_response_has_full_components_and_confidence(db_session):
    bat_yam, herzliya, _ = await _seed(db_session)

    out = await beach_exposure(herzliya.id, hours=6, session=db_session)
    assert len(out) >= 1
    row = out[0]

    assert row.components.offshore_raw is not None
    assert row.components.exposure_factor is not None
    assert row.confidence.offshore_raw == "measured_accurate"
    assert row.confidence.exposure == "unvalidated_heuristic"
    assert row.wave_height_range is not None
    assert row.wave_height_range[1] - row.wave_height_range[0] >= 0.49  # >= 2x the 0.25m floor
    assert "bearing" in row.exposure_basis


async def test_ranked_conditions_orders_herzliya_above_bat_yam(db_session):
    bat_yam, herzliya, valid_at = await _seed(db_session)

    ranked = await ranked_conditions(at=valid_at, session=db_session)
    ids_in_order = [r.beach_id for r in ranked]

    assert ids_in_order.index("herzliya") < ids_in_order.index("bat_yam")


def test_no_confidence_object_anywhere_marks_exposure_as_validated():
    """Acceptance check 5: grep the whole app/ tree for any construction of
    ExposureConfidence that overrides `exposure=` away from its default. hard rule 1 means
    no code path may ever mark the exposure layer as anything but unvalidated_heuristic."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    offending = []
    pattern = re.compile(r"ExposureConfidence\([^)]*exposure\s*=")
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offending.append(str(path))
    assert offending == [], f"exposure confidence overridden in: {offending}"

    # And the default itself is the right value -- belt and suspenders.
    assert ExposureConfidence().exposure == "unvalidated_heuristic"
