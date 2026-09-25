"""Tests for Full / Pełny mode PIN hashing and INI persistence."""

from __future__ import annotations

from pathlib import Path

from gcode_index.full_pin import (
    hash_pin,
    pin_is_set,
    validate_pin,
    verify_pin,
)
from gcode_index.instance_ini import (
    INSTANCE_INI_FILENAME,
    InstanceConfig,
    load_instance_ini,
    save_instance_ini,
)


def test_validate_pin_digits_and_length():
    assert validate_pin("1234") == "1234"
    assert validate_pin(" 12 34 ") == "1234"
    assert validate_pin("12") is None
    assert validate_pin("abcdefgh") is None
    assert validate_pin("1234567890123") is None


def test_hash_and_verify_roundtrip():
    stored = hash_pin("4821")
    assert pin_is_set(stored)
    assert stored.startswith("pbkdf2_sha256$")
    assert "4821" not in stored
    assert verify_pin("4821", stored)
    assert not verify_pin("0000", stored)
    assert not verify_pin("4821", "")
    assert not verify_pin("4821", "not-a-hash")


def test_hash_uses_unique_salt():
    a = hash_pin("4821")
    b = hash_pin("4821")
    assert a != b
    assert verify_pin("4821", a)
    assert verify_pin("4821", b)


def test_instance_ini_preserves_pin_hash(tmp_path: Path):
    path = tmp_path / INSTANCE_INI_FILENAME
    hashed = hash_pin("7391")
    cfg = InstanceConfig(
        backup="/bak",
        target="/db",
        language="pl",
        ui_mode="simple",
        full_pin_hash=hashed,
    )
    save_instance_ini(path, config=cfg)
    text = path.read_text(encoding="utf-8")
    assert "[security]" in text
    assert "full_pin_hash" in text
    assert "7391" not in text

    loaded = load_instance_ini(path)
    assert loaded.full_pin_hash == hashed
    assert verify_pin("7391", loaded.full_pin_hash)

    # Rewrite without wiping security when hash passed through config
    save_instance_ini(
        path,
        config=loaded,
        ui_mode="full",
        backup="/bak2",
    )
    again = load_instance_ini(path)
    assert again.ui_mode == "full"
    assert again.backup == "/bak2"
    assert again.full_pin_hash == hashed
