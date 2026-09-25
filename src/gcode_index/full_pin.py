"""Hashed PIN gate for Full / Pełny mode.

The hash lives in ``gcode-index.ini`` under ``[security] full_pin_hash``
(next to the exe). Format::

    pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>

No plaintext PIN is stored. Empty / missing hash means "not set yet" —
the GUI forces create-on-first-unlock (no weak factory default).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Optional

PIN_SCHEME = "pbkdf2_sha256"
PIN_ITERATIONS = 200_000
PIN_SALT_BYTES = 16
PIN_DIGEST_BYTES = 32
PIN_MIN_LEN = 4
PIN_MAX_LEN = 12


def normalize_pin(raw: Optional[str]) -> str:
    """Strip whitespace; PIN is digit-only for shop-floor typing."""
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def validate_pin(raw: Optional[str]) -> Optional[str]:
    """Return normalized PIN, or ``None`` if length / digits invalid."""
    pin = normalize_pin(raw)
    if len(pin) < PIN_MIN_LEN or len(pin) > PIN_MAX_LEN:
        return None
    return pin


def hash_pin(pin: str, *, iterations: int = PIN_ITERATIONS) -> str:
    """Return a storable hash record for a validated PIN string."""
    cleaned = validate_pin(pin)
    if cleaned is None:
        raise ValueError("invalid pin")
    salt = secrets.token_bytes(PIN_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        cleaned.encode("utf-8"),
        salt,
        int(iterations),
        dklen=PIN_DIGEST_BYTES,
    )
    return (
        f"{PIN_SCHEME}${int(iterations)}${salt.hex()}${digest.hex()}"
    )


def verify_pin(pin: str, stored: Optional[str]) -> bool:
    """Constant-time check of ``pin`` against a stored hash record."""
    cleaned = validate_pin(pin)
    if cleaned is None or not stored:
        return False
    parts = stored.strip().split("$")
    if len(parts) != 4 or parts[0] != PIN_SCHEME:
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except (ValueError, TypeError):
        return False
    if iterations < 10_000 or not salt or not expected:
        return False
    got = hashlib.pbkdf2_hmac(
        "sha256",
        cleaned.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(got, expected)


def pin_is_set(stored: Optional[str]) -> bool:
    raw = (stored or "").strip()
    return bool(raw) and raw.startswith(f"{PIN_SCHEME}$")


def load_pin_hash_from_ini(path: Path | str) -> str:
    """Read ``[security] full_pin_hash`` without requiring a full InstanceConfig."""
    from configparser import ConfigParser

    p = Path(path)
    if not p.is_file():
        return ""
    parser = ConfigParser(interpolation=None)
    try:
        parser.read(p, encoding="utf-8")
    except OSError:
        return ""
    if not parser.has_section("security"):
        return ""
    return parser.get("security", "full_pin_hash", fallback="").strip()
