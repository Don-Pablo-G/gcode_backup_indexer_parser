"""Watch coalesce quiet + legacy Auto-index schedule migration."""

from __future__ import annotations

from gcode_index.schedule import (
    DEFAULT_WATCH_COALESCE_S,
    MAX_WATCH_COALESCE_S,
    MIN_WATCH_COALESCE_S,
    SCHEDULE_OFF,
    clamp_watch_coalesce_s,
    migrate_legacy_schedule,
    normalize_watch_safety,
)


def test_clamp_watch_coalesce_s():
    assert clamp_watch_coalesce_s(45) == 45
    assert clamp_watch_coalesce_s(1) == MIN_WATCH_COALESCE_S
    assert clamp_watch_coalesce_s(9999) == MAX_WATCH_COALESCE_S
    assert clamp_watch_coalesce_s("30") == 30
    assert clamp_watch_coalesce_s("nope") == DEFAULT_WATCH_COALESCE_S
    assert clamp_watch_coalesce_s(None) == DEFAULT_WATCH_COALESCE_S


def test_normalize_watch_safety_no_seconds():
    assert normalize_watch_safety("off") == SCHEDULE_OFF
    assert normalize_watch_safety("15m") == "15m"
    assert normalize_watch_safety("1h") == "1h"
    assert normalize_watch_safety("1d") == "1d"
    # Seconds fold up to minutes for safety storage
    assert normalize_watch_safety("90s") == "2m"


def test_migrate_legacy_schedule_off():
    coalesce, safety = migrate_legacy_schedule("off")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == SCHEDULE_OFF


def test_migrate_legacy_schedule_seconds_to_coalesce():
    coalesce, safety = migrate_legacy_schedule("30s")
    assert coalesce == 30
    assert safety == SCHEDULE_OFF
    coalesce, safety = migrate_legacy_schedule("60s")
    assert coalesce == 60
    assert safety == SCHEDULE_OFF
    # Below floor clamps
    coalesce, safety = migrate_legacy_schedule("10s")
    assert coalesce == MIN_WATCH_COALESCE_S
    assert safety == SCHEDULE_OFF


def test_migrate_legacy_schedule_minutes_hours_days_to_safety():
    coalesce, safety = migrate_legacy_schedule("15m")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == "15m"
    coalesce, safety = migrate_legacy_schedule("1h")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == "1h"
    coalesce, safety = migrate_legacy_schedule("daily")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == "1d"
    coalesce, safety = migrate_legacy_schedule("weekly")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == "7d"


def test_migrate_legacy_schedule_hourly_preset():
    coalesce, safety = migrate_legacy_schedule("hourly")
    assert coalesce == DEFAULT_WATCH_COALESCE_S
    assert safety == "1h"
