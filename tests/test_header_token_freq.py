"""Unassigned O-line header token frequencies (scan-report teach list)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gcode_index.aliases import AliasMap
from gcode_index.folder_colour_aliases import FolderColourAliasMap, FolderColourRule
from gcode_index.header_token_freq import (
    HEADER_TOKEN_FREQ_FILENAME,
    MAX_DIGIT_CHARS_FOR_TEACH,
    MIN_HEADER_TOKEN_LEN,
    build_and_save_header_token_freq,
    collect_header_token_frequencies,
    digit_char_count,
    filter_unassigned_header_tokens,
    header_token_freq_path_for_target,
    is_excluded_header_token,
    is_program_number_echo,
    load_header_token_freq,
    token_has_alias,
    tokens_with_spellings,
)
from gcode_index.i18n import t
from gcode_index.models import ProgramInstance
from gcode_index.odbiorca_aliases import OdbiorcaAliasMap, OdbiorcaRule


def _inst(
    tmp: Path,
    *,
    body: str,
    program: str = "9001",
    name: str = "p.nc",
) -> ProgramInstance:
    nc = tmp / name
    nc.write_text(body, encoding="utf-8")
    return ProgramInstance(
        program_number=program,
        part_number=None,
        machine_id="unknown",
        backup_date=datetime.now(timezone.utc),
        date_source="mtime",
        source_path=name,
        source_type="loose_nc",
        scan_root=str(tmp),
    )


def test_digit_char_count_and_exclusions():
    assert digit_char_count("VF2S") == 1
    assert digit_char_count("00253232") == 8
    assert digit_char_count("umc750") == 3
    assert is_excluded_header_token("ab")  # too short
    assert len("ab") < MIN_HEADER_TOKEN_LEN
    assert is_excluded_header_token("00253232")  # >4 digits
    assert digit_char_count("00253232") > MAX_DIGIT_CHARS_FOR_TEACH
    assert not is_excluded_header_token("VF2S")
    assert not is_excluded_header_token("PROTO")
    assert not is_excluded_header_token("umc750")  # 3 digits — keep for machine teach


def test_program_number_echo():
    assert is_program_number_echo("9001", "9001")
    assert is_program_number_echo("09001", "O9001")
    assert is_program_number_echo("o9001", "9001")
    assert not is_program_number_echo("proto", "9001")
    assert not is_program_number_echo("1234", "9001")  # different program


def test_tokens_with_spellings_match_folder_tokens():
    pairs = tokens_with_spellings("VF2S PROTO")
    keys = [k for k, _ in pairs]
    assert keys == ["vf2s", "proto"]
    assert pairs[0][1] == "VF2S"
    # Digit-heavy part id splits; teaching filter drops the digit run later
    pairs2 = tokens_with_spellings("P-00253232 VA OP1")
    keys2 = [k for k, _ in pairs2]
    assert "p" in keys2
    assert "00253232" in keys2


def test_collect_frequencies_and_exclusions(tmp_path: Path):
    a = _inst(
        tmp_path,
        body="%\nO9001 (VF2S) (PROTO) (Pawel)\nG0\n%\n",
        program="9001",
        name="a.nc",
    )
    b = _inst(
        tmp_path,
        body="%\nO03232 (P-00253232 VA OP1)\nG0\n%\n",
        program="03232",
        name="b.nc",
    )
    c = _inst(
        tmp_path,
        body="%\nO9001 (VF2S)\nG0\n%\n",
        program="9001",
        name="c.nc",
    )
    entries = collect_header_token_frequencies([a, b, c])
    by_key = {e.key: e for e in entries}
    assert "vf2s" in by_key
    assert by_key["vf2s"].count == 2
    assert by_key["vf2s"].name == "VF2S"
    assert "proto" in by_key
    assert "pawel" in by_key
    # Part-number digit run excluded; short "p"/"va"/"op1" may drop on min length
    assert "00253232" not in by_key
    assert "9001" not in by_key
    assert "03232" not in by_key


def test_filter_unassigned_and_cache_roundtrip(tmp_path: Path):
    a = _inst(
        tmp_path,
        body="%\nO1 (VF2S) (PROTO)\nG0\n%\n",
        program="1",
        name="x.nc",
    )
    entries = collect_header_token_frequencies([a])
    aliases = AliasMap(
        {"vf2s": {"machine_id": "haas-vf-2", "label": "VF-2SS"}}
    )
    colour = FolderColourAliasMap(
        [FolderColourRule(alias="PROTO", colour="prototype", exact=True)]
    )
    unassigned = filter_unassigned_header_tokens(
        entries, aliases=aliases, colour_map=colour, odbiorca_map=OdbiorcaAliasMap([])
    )
    keys = {e.key for e in unassigned}
    assert "vf2s" not in keys  # machine alias
    assert "proto" not in keys  # role alias
    assert token_has_alias("VF2S", aliases=aliases)

    built = build_and_save_header_token_freq(
        tmp_path, [a], run_id="run-1", full_scan=True
    )
    path = header_token_freq_path_for_target(tmp_path)
    assert path.name == HEADER_TOKEN_FREQ_FILENAME
    assert path.is_file()
    loaded = load_header_token_freq(path)
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert {e.key for e in loaded.tokens} == {e.key for e in built}


def test_odbiorca_counts_as_assigned():
    odb = OdbiorcaAliasMap(
        [OdbiorcaRule(alias="Pawel", odbiorca_id="pawel", exact=True)]
    )
    assert token_has_alias("Pawel", odbiorca_map=odb)
    assert not token_has_alias("Other", odbiorca_map=odb)


def test_header_tokens_i18n_pl_en():
    assert "Nieprzypisane" in t("pl", "header_tokens_button")
    assert "Unassigned" in t("en", "header_tokens_button")
    assert "header_token_freq.json" in t("pl", "header_tokens_intro")
    assert "Folder names" in t("en", "header_tokens_intro") or "folder" in t(
        "en", "header_tokens_intro"
    ).casefold()
