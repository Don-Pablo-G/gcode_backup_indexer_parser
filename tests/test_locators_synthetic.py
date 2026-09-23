from __future__ import annotations

from pathlib import Path

import pytest

from gcode_index.locators.fanuc_all_fldr import locate_fanuc_all_fldr
from gcode_index.locators.fanuc_all_prog import locate_fanuc_all_prog
from gcode_index.locators.haas_pgm import locate_haas_pgm
from gcode_index.locators.whole_file_nc import locate_whole_file_nc

FIX = Path(__file__).parent / "fixtures" / "synthetic"


def test_haas_pgm_synthetic():
    path = FIX / "tiny.pgm"
    inst = locate_haas_pgm(
        path, source_path="tiny.pgm", machine_id="haas-sl-20"
    )
    assert len(inst) == 2
    assert inst[0].program_number == "00001"
    assert inst[0].part_number == "PART-A"
    assert inst[0].source_type == "haas_pgm_glued"
    assert inst[0].line_start == 3
    assert inst[0].line_end == 5  # inclusive through M30; next O is line 6
    assert inst[1].program_number == "00002"
    assert inst[1].part_number == "PART-B"
    # CRLF byte math: each line ends with \r\n
    assert inst[0].byte_start is not None
    assert inst[0].byte_end == inst[1].byte_start
    # Do not split on M30: first instance includes M30 line
    raw = path.read_bytes()
    chunk = raw[inst[0].byte_start : inst[0].byte_end]
    assert b"M30" in chunk
    assert b"O00002" not in chunk


def test_fanuc_all_fldr_synthetic():
    path = FIX / "ALL-FLDR.TXT"
    inst = locate_fanuc_all_fldr(
        path, source_path="ALL-FLDR.TXT", machine_id="doosan-dnm-6700"
    )
    assert len(inst) == 3
    assert inst[0].header_kind == "angle"
    assert inst[0].program_number == "09814"
    assert inst[0].part_number == "ANGLE-PART"
    assert inst[0].folder_path == "/MTB1/"
    assert inst[1].program_number == "9814"
    assert inst[1].folder_path == "/MTB1/"
    assert inst[2].program_number == "0002"
    assert inst[2].folder_path == "/USER/PATH1/"
    # end at next header / folder / % — not only M30
    assert inst[0].line_end < inst[1].line_start


def test_fanuc_all_prog_synthetic():
    path = FIX / "ALL-PROG.TXT"
    inst = locate_fanuc_all_prog(
        path, source_path="ALL-PROG.TXT", machine_id="doosan-dnm-400"
    )
    assert len(inst) == 4
    nums = [i.program_number for i in inst]
    assert nums == ["0001", "0801", "3992", "P-BARE"]
    assert inst[1].part_number == "A"  # first paren
    assert all(i.folder_path is None for i in inst)


def test_haas_ngc_whole_file_prefers_o_header():
    path = FIX / "haas_ngc_umc.nc"
    inst = locate_whole_file_nc(
        path,
        source_path="Memory/P-00253232 VA.nc",
        source_type="haas_ngc_nc",
        machine_id="haas-umc750",
        parser_id="haas_ngc_nc",
    )
    assert inst.program_number == "03232"
    assert inst.part_number == "P-00253232 VA OP1/OP2"
    assert inst.header_kind == "o_word"
    assert inst.source_type == "haas_ngc_nc"
    assert inst.line_start is None  # whole-file location


def test_haas_ngc_st20y_no_percent_frame():
    """ST-20Y sample has no % framing; trailing spaces on header OK."""
    path = FIX / "haas_ngc_st20y.nc"
    inst = locate_whole_file_nc(
        path,
        source_path="Memory/9278.NC",
        source_type="haas_ngc_nc",
        machine_id="haas-st-20y",
        parser_id="haas_ngc_nc",
    )
    assert inst.program_number == "09278"
    assert inst.part_number == "P-00059278"
    assert inst.header_kind == "o_word"


def test_whole_file_nc_falls_back_to_filename_stem():
    path = FIX / "O1234.nc"
    # File has O1234 with no paren; still o_word
    inst = locate_whole_file_nc(
        path,
        source_path="O1234.nc",
        source_type="loose_nc",
        machine_id="loose",
    )
    assert inst.program_number == "1234"
    assert inst.header_kind == "o_word"
