"""Watch safety rescan clock anchor (watch_safety_at HH:MM)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from gcode_index import schedule as schedule_mod
from gcode_index.indexer_settings import (
    IndexerSettings,
    load_indexer_settings,
    save_indexer_settings,
)
from gcode_index.instance_ini import InstanceConfig, load_instance_ini, save_instance_ini
from gcode_index.schedule import (
    format_watch_safety_label,
    is_schedule_due,
    is_watch_safety_due,
    next_watch_safety_at,
    normalize_watch_safety_at,
    parse_watch_safety_at,
    seconds_until_watch_safety,
)

# Fixed UTC+2 stand-in for Europe/Warsaw summer (CEST). Avoids ZoneInfo/tzdata and
# time.tzset(), neither of which is reliable on Windows CI runners.
_LOCAL = timezone(timedelta(hours=2))


def _freeze_local_tz(monkeypatch) -> timezone:
    """Make schedule._as_local use a fixed offset (Windows CI has no tzdata/tzset)."""
    monkeypatch.setattr(
        schedule_mod,
        "_as_local",
        lambda dt: schedule_mod._as_utc(dt).astimezone(_LOCAL),
    )
    return _LOCAL


def test_normalize_watch_safety_at():
    assert normalize_watch_safety_at("") == ""
    assert normalize_watch_safety_at(None) == ""
    assert normalize_watch_safety_at("0:00") == "00:00"
    assert normalize_watch_safety_at("00:00") == "00:00"
    assert normalize_watch_safety_at("6:30") == "06:30"
    assert normalize_watch_safety_at("23:59") == "23:59"
    assert normalize_watch_safety_at("24:00") == ""
    assert normalize_watch_safety_at("12:60") == ""
    assert normalize_watch_safety_at("noon") == ""
    assert parse_watch_safety_at("7:05") == (7, 5)


def test_format_watch_safety_label():
    assert format_watch_safety_label("off") == "off"
    assert format_watch_safety_label("24h") == "24h"
    assert format_watch_safety_label("24h", "00:00") == "24h@00:00"
    assert format_watch_safety_label("1h", "06:00") == "1h@06:00"
    assert format_watch_safety_label("1h", "bad") == "1h"


def test_blank_at_matches_interval_from_last_run():
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)
    assert is_watch_safety_due("1h", last, "", now=now) is True
    assert is_watch_safety_due("1h", last, "", now=now) == is_schedule_due(
        "1h", last, now=now
    )
    assert is_watch_safety_due("1h", now - timedelta(minutes=10), "", now=now) is False
    nxt_blank = next_watch_safety_at("1h", last, "", now=now)
    assert nxt_blank is not None


def test_24h_at_midnight_next_local_midnight(monkeypatch):
    # Freeze local TZ so wall-clock assertions are stable in CI (incl. Windows).
    local = _freeze_local_tz(monkeypatch)
    # Afternoon local — next slot is tonight's midnight (start of next calendar day).
    now_local = datetime(2026, 9, 29, 15, 30, tzinfo=local)
    now = now_local.astimezone(timezone.utc)

    nxt = next_watch_safety_at("24h", None, "00:00", now=now)
    assert nxt is not None
    nxt_local = nxt.astimezone(local)
    assert (nxt_local.hour, nxt_local.minute) == (0, 0)
    assert nxt_local.date() == datetime(2026, 9, 30).date()
    assert is_watch_safety_due("24h", None, "00:00", now=now) is False

    # Exactly at midnight with no last_run → due.
    midnight = datetime(2026, 9, 30, 0, 0, tzinfo=local).astimezone(timezone.utc)
    assert is_watch_safety_due("24h", None, "00:00", now=midnight) is True

    # After a midnight run, next is tomorrow midnight — not last_run+24h from a noon stamp.
    ran_midnight = midnight
    noon = datetime(2026, 9, 30, 12, 0, tzinfo=local).astimezone(timezone.utc)
    # Midday manual updates last_run to noon; clock grid still targets next midnight.
    nxt2 = next_watch_safety_at("24h", noon, "00:00", now=noon)
    assert nxt2 is not None
    nxt2_local = nxt2.astimezone(local)
    assert (nxt2_local.hour, nxt2_local.minute) == (0, 0)
    assert nxt2_local.date() == datetime(2026, 10, 1).date()
    assert is_watch_safety_due("24h", noon, "00:00", now=noon) is False

    # Still due for tonight's midnight if last_run was yesterday morning (overdue).
    yesterday_morning = datetime(2026, 9, 29, 8, 0, tzinfo=local).astimezone(
        timezone.utc
    )
    assert is_watch_safety_due("24h", yesterday_morning, "00:00", now=noon) is True

    # After completing midnight slot, not due until next day.
    assert is_watch_safety_due("24h", ran_midnight, "00:00", now=noon) is False
    rem = seconds_until_watch_safety("24h", ran_midnight, "00:00", now=noon)
    assert rem is not None and rem > 0


def test_12h_at_0600_grid(monkeypatch):
    local = _freeze_local_tz(monkeypatch)
    # 10:00 → next is 18:00
    now = datetime(2026, 9, 29, 10, 0, tzinfo=local).astimezone(timezone.utc)
    nxt = next_watch_safety_at("12h", None, "06:00", now=now)
    assert nxt is not None
    assert nxt.astimezone(local).hour == 18

    # After 18:00 run, next is tomorrow 06:00
    ran = datetime(2026, 9, 29, 18, 0, tzinfo=local).astimezone(timezone.utc)
    evening = datetime(2026, 9, 29, 18, 30, tzinfo=local).astimezone(timezone.utc)
    nxt2 = next_watch_safety_at("12h", ran, "06:00", now=evening)
    assert nxt2 is not None
    n2 = nxt2.astimezone(local)
    assert (n2.hour, n2.minute) == (6, 0)
    assert n2.date() == datetime(2026, 9, 30).date()


def test_6h_at_0000_quarter_day(monkeypatch):
    local = _freeze_local_tz(monkeypatch)
    now = datetime(2026, 9, 29, 14, 0, tzinfo=local).astimezone(timezone.utc)
    nxt = next_watch_safety_at("6h", None, "00:00", now=now)
    assert nxt is not None
    assert nxt.astimezone(local).hour == 18


def test_instance_ini_missing_watch_safety_at_is_blank(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    path.write_text(
        "[folders]\nbackup = /bak\ntarget = /db\n\n"
        "[scan]\nwatch_coalesce_s = 45\nwatch_safety = 24h\n"
        "watch_safety_last_run = 2026-09-25T00:00:00+00:00\n",
        encoding="utf-8",
    )
    loaded = load_instance_ini(path)
    assert loaded.watch_safety == "24h"
    assert loaded.watch_safety_at == ""


def test_instance_ini_roundtrip_watch_safety_at(tmp_path: Path):
    path = tmp_path / "gcode-index.ini"
    cfg = InstanceConfig(
        backup="/bak",
        target="/db",
        watch_safety="24h",
        watch_safety_at="00:00",
        watch_safety_last_run="2026-09-25T00:00:00+00:00",
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "watch_safety_at = 00:00" in text
    loaded = load_instance_ini(path)
    assert loaded.watch_safety_at == "00:00"

    cfg2 = InstanceConfig(backup="/bak", target="/db", watch_safety="1h", watch_safety_at="")
    save_instance_ini(path, config=cfg2)
    loaded2 = load_instance_ini(path)
    assert loaded2.watch_safety_at == ""


def test_indexer_settings_watch_safety_at_roundtrip(tmp_path: Path):
    path = tmp_path / "indexer_settings.yaml"
    save_indexer_settings(
        path,
        IndexerSettings(watch_safety="24h", watch_safety_at="00:00"),
    )
    text = path.read_text(encoding="utf-8")
    assert "watch_safety_at" in text
    loaded = load_indexer_settings(path)
    assert loaded is not None
    assert loaded.watch_safety_at == "00:00"

    path.write_text("watch_safety: 1h\nwatch_folders: yes\n", encoding="utf-8")
    loaded2 = load_indexer_settings(path)
    assert loaded2 is not None
    assert loaded2.watch_safety_at == ""
