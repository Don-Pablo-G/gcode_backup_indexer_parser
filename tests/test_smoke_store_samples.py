"""Optional smoke tests against Project store samples (skip if missing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.locators.fanuc_all_fldr import locate_fanuc_all_fldr
from gcode_index.locators.fanuc_all_prog import locate_fanuc_all_prog
from gcode_index.locators.haas_pgm import locate_haas_pgm

STORE = Path("/cursor/stores/bc-8553f678-6c90-4da8-8c05-737a2b3271c2/internal/samples")
# Also try self symlink naming if present
STORE_ALT = Path("/cursor/stores/self/internal/samples")


def _sample(*parts: str) -> Path | None:
    for base in (STORE, STORE_ALT):
        p = base.joinpath(*parts)
        if p.is_file():
            return p
    return None


@pytest.mark.skipif(
    _sample("haas-pgm", "SL20.PGM") is None, reason="store SL20.PGM missing"
)
def test_smoke_haas_sl20():
    path = _sample("haas-pgm", "SL20.PGM")
    assert path is not None
    inst = locate_haas_pgm(path, source_path=path.name, machine_id="haas-sl-20")
    assert len(inst) == 476


@pytest.mark.skipif(
    _sample("fanuc-all-fldr", "ALL-FLDR_doosan-dnm6700.TXT") is None,
    reason="store ALL-FLDR missing",
)
def test_smoke_all_fldr_dnm6700():
    path = _sample("fanuc-all-fldr", "ALL-FLDR_doosan-dnm6700.TXT")
    assert path is not None
    inst = locate_fanuc_all_fldr(
        path, source_path=path.name, machine_id="doosan-dnm-6700"
    )
    assert len(inst) == 161


@pytest.mark.skipif(
    _sample("fanuc-all-prog", "ALL-PROG_doosan-dnm400.TXT") is None,
    reason="store ALL-PROG missing",
)
def test_smoke_all_prog_dnm400():
    path = _sample("fanuc-all-prog", "ALL-PROG_doosan-dnm400.TXT")
    assert path is not None
    inst = locate_fanuc_all_prog(
        path, source_path=path.name, machine_id="doosan-dnm-400"
    )
    assert len(inst) == 186
