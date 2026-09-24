"""UI language strings — Polish default, English optional."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

UI_SETTINGS_FILENAME = "ui_settings.yaml"
DEFAULT_LANG = "pl"
LANG_CHOICES = ("pl", "en")

# Keys used by the GUI. Missing keys fall back to English, then the key itself.
STRINGS: dict[str, dict[str, str]] = {
    "pl": {
        "app_title": "Indeksator kopii G-code",
        "folders": "Foldery",
        "backup_folder": "Folder kopii zapasowych",
        "target_folder": "Folder docelowy (baza / ekstrakty)",
        "browse": "Przeglądaj…",
        "extra_folders": "Dodatkowe foldery (żółta flaga — nie z kopii maszyny)",
        "add_folder": "Dodaj folder…",
        "remove_selected": "Usuń zaznaczone",
        "extra_hint": "Główna kopia = zielona (była na maszynie). Dodatkowa = żółta (nie z kopii).",
        "run_scan": "Indeksuj / skanuj",
        "map_folders": "Mapuj foldery…",
        "aliases": "Aliasy…",
        "open_db": "Otwórz istniejącą bazę…",
        "scan_report": "Raport skanu…",
        "duplicates": "Duplikaty…",
        "clear_filters": "Wyczyść filtry",
        "also_excel": "Zapisz też Excel",
        "incremental": "Przyrostowo (pomiń niezmienione pliki)",
        "language": "Język",
        "lang_pl": "Polski",
        "lang_en": "English",
        "find_programs": "Szukaj programów — tekst · maszyny · data · źródło",
        "text": "Tekst",
        "newest_only": "Tylko najnowsze",
        "extract_selected": "Ekstrahuj zaznaczone…",
        "machines": "Maszyny",
        "all": "Wszystkie",
        "none": "Żadne",
        "multi_hint": "Ctrl/Shift+klik\n= wielokrotny wybór",
        "date_from": "Data od",
        "date_to_sep": " do ",
        "date_format": "DD.MM.RRRR",
        "source_type": "Typ źródła",
        "control": "Sterowanie",
        "flag": "Flaga",
        "programmer": "Programista",
        "compare": "Porównaj…",
        "open_folder": "Otwórz folder",
        "copy_path": "Kopiuj ścieżkę",
        "preset": "Zapamiętany filtr",
        "load": "Wczytaj",
        "save_current": "Zapisz bieżący…",
        "delete": "Usuń",
        "preset_hint": "Zapisane jako {filename} obok bazy",
        "hint": (
            "Zielona flaga = z głównej kopii (była na maszynie). "
            "Żółta = z dodatkowego folderu. "
            "Programista = następna linia (LP1)/(MS1) gdy obecna. "
            "Tylko najnowsze = jedna pozycja na program+maszynę. "
            "Ctrl/Shift+klik = wielokrotny wybór do ekstrakcji. "
            "Podgląd pokazuje treść zaznaczonego programu. "
            "Porównaj… wymaga dokładnie dwóch wierszy. "
            "Szukanie numeru: O03232 / 03232 / 3232 to ten sam program. "
            "Zapamiętane filtry zapisują ustawienia paska wyszukiwania. "
            "Przyrostowy skan pomija niezmienione pliki."
        ),
        "col_flag": "Flaga",
        "col_program": "Nr programu",
        "col_part": "Nr części",
        "col_programmer": "Prog.",
        "col_machine": "Maszyna",
        "col_date": "Data",
        "col_type": "Typ źródła",
        "col_control": "Sterowanie",
        "col_path": "Ścieżka źródła",
        "col_location": "Lokalizacja w pliku",
        "preview": "Podgląd",
        "preview_idle": "Podgląd — wybierz wiersz wyniku",
        "status_pick": "Wybierz folder kopii i folder docelowy dla bazy.",
        "flag_green": "zielona — kopia (była na maszynie)",
        "flag_yellow": "żółta — dodatkowa (nie jechała)",
        "all_paren": "(wszystkie)",
        "ctx_extract": "Ekstrahuj zaznaczone…",
        "ctx_compare": "Porównaj…",
        "ctx_open": "Otwórz folder",
        "ctx_copy": "Kopiuj ścieżkę",
        "scan_report_title": "Raport skanu",
        "duplicates_title": "Wyszukiwanie duplikatów",
        "compare_title": "Porównaj programy",
        "close": "Zamknij",
        "cancel": "Anuluj",
        "show_in_results": "Pokaż w wynikach",
    },
    "en": {
        "app_title": "G-code Backup Indexer",
        "folders": "Folders",
        "backup_folder": "Backup folder",
        "target_folder": "Target folder (DB / extracts)",
        "browse": "Browse…",
        "extra_folders": "Extra folders (yellow flag — not from machine backup)",
        "add_folder": "Add folder…",
        "remove_selected": "Remove selected",
        "extra_hint": "Main backup = green (ran on machine). Extra = yellow (not in backup).",
        "run_scan": "Run index / scan",
        "map_folders": "Map folders…",
        "aliases": "Aliases…",
        "open_db": "Open existing DB…",
        "scan_report": "Scan report…",
        "duplicates": "Duplicates…",
        "clear_filters": "Clear filters",
        "also_excel": "Also write Excel",
        "incremental": "Incremental (skip unchanged files)",
        "language": "Language",
        "lang_pl": "Polski",
        "lang_en": "English",
        "find_programs": "Find programs — text · machines (multi-select) · date · source",
        "text": "Text",
        "newest_only": "Newest only",
        "extract_selected": "Extract selected…",
        "machines": "Machines",
        "all": "All",
        "none": "None",
        "multi_hint": "Ctrl/Shift+click\nfor multi-select",
        "date_from": "Date from",
        "date_to_sep": " to ",
        "date_format": "DD.MM.YYYY",
        "source_type": "Source type",
        "control": "Control",
        "flag": "Flag",
        "programmer": "Programmer",
        "compare": "Compare…",
        "open_folder": "Open folder",
        "copy_path": "Copy path",
        "preset": "Preset",
        "load": "Load",
        "save_current": "Save current…",
        "delete": "Delete",
        "preset_hint": "Stored as {filename} next to the DB",
        "hint": (
            "Green flag = from main backup (ran on machine). "
            "Yellow = from an extra folder (not in backup). "
            "Programmer = next-line (LP1)/(MS1) when present. "
            "Newest only keeps the latest date per program+machine. "
            "Ctrl/Shift+click rows to multi-select for batch extract. "
            "Preview shows the selected program body. "
            "Compare… needs exactly two selected rows. "
            "Program search: O03232 / 03232 / 3232 match the same O-number. "
            "Presets save/restore the find-bar filters. "
            "Incremental scan skips unchanged files."
        ),
        "col_flag": "Flag",
        "col_program": "Program #",
        "col_part": "Part number",
        "col_programmer": "Prog.",
        "col_machine": "Machine",
        "col_date": "Date",
        "col_type": "Source type",
        "col_control": "Control",
        "col_path": "Source path",
        "col_location": "In-file location",
        "preview": "Preview",
        "preview_idle": "Preview — select a result row",
        "status_pick": "Pick a backup folder and a target folder for the database.",
        "flag_green": "green — backup (ran)",
        "flag_yellow": "yellow — extra (not run)",
        "all_paren": "(all)",
        "ctx_extract": "Extract selected…",
        "ctx_compare": "Compare…",
        "ctx_open": "Open folder",
        "ctx_copy": "Copy path",
        "scan_report_title": "Scan report",
        "duplicates_title": "Duplicate / near-duplicate finder",
        "compare_title": "Compare programs",
        "close": "Close",
        "cancel": "Cancel",
        "show_in_results": "Show in results",
    },
}


def normalize_lang(lang: Optional[str]) -> str:
    raw = (lang or DEFAULT_LANG).strip().casefold()
    if raw.startswith("en"):
        return "en"
    return "pl"


def t(lang: str, key: str, **kwargs: Any) -> str:
    code = normalize_lang(lang)
    text = STRINGS.get(code, {}).get(key)
    if text is None:
        text = STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def ui_settings_path_for_target(target: Path | str) -> Path:
    return Path(target) / UI_SETTINGS_FILENAME


def load_ui_language(path: Path | str | None = None) -> str:
    if path is None:
        return DEFAULT_LANG
    p = Path(path)
    if not p.is_file():
        return DEFAULT_LANG
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            return normalize_lang(str(data.get("language") or DEFAULT_LANG))
    except OSError:
        pass
    return DEFAULT_LANG


def save_ui_language(path: Path | str, lang: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "language": normalize_lang(lang),
        "_comment": "GUI language for G-code Backup Indexer (pl default, en optional).",
    }
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return p
