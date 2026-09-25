"""UI language strings — Polish default, English optional."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

UI_SETTINGS_FILENAME = "ui_settings.yaml"
DEFAULT_LANG = "pl"
LANG_CHOICES = ("pl", "en")
DEFAULT_UI_MODE = "simple"
UI_MODE_CHOICES = ("simple", "full")

# Keys used by the GUI. Missing keys fall back to English, then the key itself.
STRINGS: dict[str, dict[str, str]] = {
    "pl": {
        "app_title": "Indeksator kopii G-code",
        "folders": "Foldery",
        "folders_step": "1 · Foldery",
        "folders_step_simple": "1 · Baza / foldery",
        "folders_summary_empty": "Ustaw folder kopii i folder bazy…",
        "folders_summary_empty_simple": "Otwórz bazę lub ustaw folder z bazą…",
        "folders_summary": "Kopia: {backup}    Baza: {target}    Wydobycie: {extract}",
        "folders_summary_simple": "Baza: {target}    Wydobycie: {extract}    Kopia: {backup}",
        "change_folders": "Zmień…",
        "folders_done": "Gotowe",
        "path_unset": "(brak)",
        "backup_folder": "Folder kopii zapasowych",
        "backup_folder_optional": "Folder kopii (opcjonalny — do wydobycia)",
        "target_folder": "Folder bazy (SQLite / mapy / aliasy)",
        "target_folder_simple": "Folder z bazą (SQLite)",
        "extract_folder": "Folder wydobycia (zapisane programy)",
        "extract_folder_hint": "Puste = ten sam co folder bazy",
        "browse": "Przeglądaj…",
        "extra_folders": "Dodatkowe foldery",
        "add_folder": "Dodaj folder…",
        "add_green_folder": "Dodaj zielony (z maszyny / .nc)…",
        "add_yellow_folder": "Dodaj żółty (poza kopią)…",
        "remove_selected": "Usuń zaznaczone",
        "extra_hint": (
            "Zielony = traktuj jak z maszyny (luźne .nc zanim znikną z backupu). "
            "Żółty = dodatkowy folder (nie z kopii)."
        ),
        "tag_green": "[G]",
        "tag_yellow": "[Y]",
        "schedule": "Auto-indeks",
        "schedule_off": "Wyłączony",
        "schedule_hourly": "Co godzinę",
        "schedule_daily": "Codziennie",
        "schedule_weekly": "Co tydzień",
        "schedule_next": "Następny: {when}",
        "schedule_idle": "Auto-indeks wyłączony",
        "schedule_running": "Auto-indeks…",
        "schedule_last": "Ostatni auto-indeks: {when}",
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
        "ui_mode": "Tryb",
        "mode_simple": "Prosty",
        "mode_full": "Pełny",
        "find_programs": "Szukaj programów — tekst · maszyny · data · źródło",
        "find_programs_simple": "Szukaj programów",
        "find_programs_step": "2 · Szukaj programów",
        "text": "Tekst",
        "newest_only": "Tylko najnowsze",
        "extract_selected": "Wydobądź zaznaczone…",
        "machines": "Maszyny",
        "machines_all": "Maszyny: wszystkie",
        "machines_n": "Maszyny: {n}",
        "machines_pick": "Wybierz maszyny",
        "more_filters": "Więcej filtrów ▾",
        "fewer_filters": "Mniej filtrów ▴",
        "all": "Wszystkie",
        "none": "Żadne",
        "multi_hint": "Ctrl/Shift+klik = wielokrotny wybór",
        "ok": "OK",
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
            "Ctrl/Shift+klik = wielokrotny wybór do wydobycia. "
            "Podgląd pokazuje treść zaznaczonego programu. "
            "Porównaj… wymaga dokładnie dwóch wierszy. "
            "Szukanie numeru: O03232 / 03232 / 3232 to ten sam program. "
            "Zapamiętane filtry zapisują ustawienia paska wyszukiwania. "
            "Przyrostowy skan pomija niezmienione pliki."
        ),
        "hint_simple": (
            "Tylko odczyt: otwórz istniejącą bazę (zielony przycisk), "
            "szukaj po numerze programu lub części, "
            "zaznacz wiersz → zielony Wydobądź (lub podwójne kliknięcie). "
            "Folder kopii potrzebny tylko gdy wydobycie wymaga ścieżek względnych. "
            "Indeksowanie / skan / auto-indeks — w trybie Pełny. "
            "Tylko najnowsze = jedna pozycja na program+maszynę."
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
        "status_pick": "Wybierz folder kopii i folder bazy.",
        "status_pick_simple": "Otwórz istniejącą bazę (zielony przycisk) lub ustaw folder z bazą.",
        "status_loaded_ini": "Wczytano ustawienia z {filename}",
        "flag_green": "zielona — kopia (była na maszynie)",
        "flag_yellow": "żółta — dodatkowa (nie jechała)",
        "all_paren": "(wszystkie)",
        "ctx_extract": "Wydobądź zaznaczone…",
        "ctx_compare": "Porównaj…",
        "ctx_open": "Otwórz folder",
        "ctx_copy": "Kopiuj ścieżkę",
        "scan_report_title": "Raport skanu",
        "duplicates_title": "Wyszukiwanie duplikatów",
        "compare_title": "Porównaj programy",
        "close": "Zamknij",
        "cancel": "Anuluj",
        "show_in_results": "Pokaż w wynikach",
        "menu_help": "Pomoc",
        "help_manual_simple": "Instrukcja operatora (Prosty)…",
        "help_manual_full": "Instrukcja indeksatora (Pełny)…",
        "help_about": "O programie…",
        "help_open_folder": "Otwórz folder dokumentacji…",
        "about_title": "O programie",
        "about_body": (
            "Indeksator kopii G-code\n"
            "Wersja {version}\n\n"
            "Prosty = wyszukiwanie i wydobycie z istniejącej bazy.\n"
            "Pełny = indeksowanie / skanowanie kopii CNC.\n\n"
            "Instrukcje: menu Pomoc."
        ),
    },
    "en": {
        "app_title": "G-code Backup Indexer",
        "folders": "Folders",
        "folders_step": "1 · Folders",
        "folders_step_simple": "1 · Database / folders",
        "folders_summary_empty": "Set backup and database folders…",
        "folders_summary_empty_simple": "Open a database or set the folder that holds it…",
        "folders_summary": "Backup: {backup}    DB: {target}    Extract: {extract}",
        "folders_summary_simple": "DB: {target}    Extract: {extract}    Backup: {backup}",
        "change_folders": "Change…",
        "folders_done": "Done",
        "path_unset": "(not set)",
        "backup_folder": "Backup folder",
        "backup_folder_optional": "Backup folder (optional — for extract)",
        "target_folder": "Database folder (SQLite / maps / aliases)",
        "target_folder_simple": "Database folder (SQLite)",
        "extract_folder": "Extract folder (saved programs)",
        "extract_folder_hint": "Blank = same as database folder",
        "browse": "Browse…",
        "extra_folders": "Additional folders",
        "add_folder": "Add folder…",
        "add_green_folder": "Add green (on-machine / .nc)…",
        "add_yellow_folder": "Add yellow (not from backup)…",
        "remove_selected": "Remove selected",
        "extra_hint": (
            "Green = treat as on-machine (loose .nc before backup misses them). "
            "Yellow = extra folder (not from backup)."
        ),
        "tag_green": "[G]",
        "tag_yellow": "[Y]",
        "schedule": "Auto-index",
        "schedule_off": "Off",
        "schedule_hourly": "Hourly",
        "schedule_daily": "Daily",
        "schedule_weekly": "Weekly",
        "schedule_next": "Next: {when}",
        "schedule_idle": "Auto-index off",
        "schedule_running": "Auto-indexing…",
        "schedule_last": "Last auto-index: {when}",
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
        "ui_mode": "Mode",
        "mode_simple": "Simple",
        "mode_full": "Full",
        "find_programs": "Find programs — text · machines (multi-select) · date · source",
        "find_programs_simple": "Find programs",
        "find_programs_step": "2 · Find programs",
        "text": "Text",
        "newest_only": "Newest only",
        "extract_selected": "Extract selected…",
        "machines": "Machines",
        "machines_all": "Machines: all",
        "machines_n": "Machines: {n}",
        "machines_pick": "Choose machines",
        "more_filters": "More filters ▾",
        "fewer_filters": "Fewer filters ▴",
        "all": "All",
        "none": "None",
        "multi_hint": "Ctrl/Shift+click for multi-select",
        "ok": "OK",
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
        "hint_simple": (
            "Retrieve only: open an existing database (green button), "
            "search by program or part number, "
            "select a row → green Extract (or double-click). "
            "Backup folder is needed only when extract uses relative source paths. "
            "Indexing / scan / auto-index live in Full mode. "
            "Newest only = one row per program+machine."
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
        "status_pick": "Pick a backup folder and a database folder.",
        "status_pick_simple": "Open an existing database (green button) or set the folder that holds it.",
        "status_loaded_ini": "Loaded settings from {filename}",
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
        "menu_help": "Help",
        "help_manual_simple": "Operator manual (Simple)…",
        "help_manual_full": "Indexer manual (Full)…",
        "help_about": "About…",
        "help_open_folder": "Open documentation folder…",
        "about_title": "About",
        "about_body": (
            "G-code Backup Indexer\n"
            "Version {version}\n\n"
            "Simple = search and extract from an existing database.\n"
            "Full = index / scan CNC backup trees.\n\n"
            "Manuals: Help menu."
        ),
    },
}


def normalize_lang(lang: Optional[str]) -> str:
    raw = (lang or DEFAULT_LANG).strip().casefold()
    if raw.startswith("en"):
        return "en"
    return "pl"


def normalize_ui_mode(mode: Optional[str]) -> str:
    raw = (mode or DEFAULT_UI_MODE).strip().casefold()
    if raw in ("full", "advanced", "expert", "pełny", "pelny"):
        return "full"
    if raw in ("simple", "basic", "prosty", "minimal", "easy"):
        return "simple"
    return DEFAULT_UI_MODE


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


def load_ui_settings(path: Path | str | None = None) -> dict[str, str]:
    """Return language / ui_mode / schedule settings with defaults."""
    out = {
        "language": DEFAULT_LANG,
        "ui_mode": DEFAULT_UI_MODE,
        "schedule": "off",
        "schedule_last_run": "",
    }
    if path is None:
        return out
    p = Path(path)
    if not p.is_file():
        return out
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            out["language"] = normalize_lang(str(data.get("language") or DEFAULT_LANG))
            out["ui_mode"] = normalize_ui_mode(str(data.get("ui_mode") or DEFAULT_UI_MODE))
            from gcode_index.schedule import normalize_schedule

            out["schedule"] = normalize_schedule(str(data.get("schedule") or "off"))
            out["schedule_last_run"] = str(data.get("schedule_last_run") or "").strip()
    except OSError:
        pass
    return out


def save_ui_settings(
    path: Path | str,
    *,
    language: Optional[str] = None,
    ui_mode: Optional[str] = None,
    schedule: Optional[str] = None,
    schedule_last_run: Optional[str] = None,
) -> Path:
    """Write UI settings, merging with any existing file values."""
    p = Path(path)
    existing = load_ui_settings(p if p.is_file() else None)
    from gcode_index.schedule import normalize_schedule

    lang = normalize_lang(language if language is not None else existing["language"])
    mode = normalize_ui_mode(ui_mode if ui_mode is not None else existing["ui_mode"])
    sched = normalize_schedule(
        schedule if schedule is not None else existing.get("schedule") or "off"
    )
    last = (
        schedule_last_run
        if schedule_last_run is not None
        else existing.get("schedule_last_run") or ""
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "language": lang,
        "ui_mode": mode,
        "schedule": sched,
        "schedule_last_run": last,
        "_comment": (
            "GUI settings for G-code Backup Indexer "
            "(language: pl default; ui_mode: simple|full; "
            "schedule: off|hourly|daily|weekly)."
        ),
    }
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return p


def load_ui_language(path: Path | str | None = None) -> str:
    return load_ui_settings(path)["language"]


def save_ui_language(path: Path | str, lang: str) -> Path:
    return save_ui_settings(path, language=lang)


def load_ui_mode(path: Path | str | None = None) -> str:
    return load_ui_settings(path)["ui_mode"]


def save_ui_mode(path: Path | str, mode: str) -> Path:
    return save_ui_settings(path, ui_mode=mode)
