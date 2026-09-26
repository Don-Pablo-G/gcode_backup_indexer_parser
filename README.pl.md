# G-code backup indexer / parser

Indeksuje **drzewa kopii zapasowych** maszyn CNC do przenośnego katalogu **SQLite** z **wystąpieniami programów** (nr programu, nr części, maszyna, data, lokalizacja źródła). Pełne parsowanie G-code jest **poza zakresem** — narzędzie wyciąga **nagłówki + lokalizacje**, żeby ludzie i inne programy mogły szukać i później wydobywać zakresy.

**Repozytorium:** https://github.com/Don-Pablo-G/gcode_backup_indexer_parser

**English README:** [README.md](README.md)

## Dokumentacja użytkownika

| Dokument | Dla kogo |
|----------|----------|
| [Instrukcja operatora](docs/pl/manual-simple.md) | Klient hali (`can_index=no`) — szukanie i wydobycie |
| [Instrukcja indeksatora](docs/pl/manual-full.md) | PC indeksatora (`can_index=yes`) — budowa i utrzymanie bazy |
| Same manuals in English | [docs/en/](docs/en/) |

W aplikacji GUI: menu **Pomoc** otwiera te same instrukcje (operator vs indeksator wg `can_index` tej instalacji). Nazwy plików `manual-simple` / `manual-full` są legacy — **nie ma** przełącznika Prosty/Pełny.

## Wymagania

- Python **3.11+** (testowane na 3.12)
- Windows, Linux lub macOS
- GUI Windows używa **tkinter** (dołączony do oficjalnego instalatora python.org)

## Instalacja

```bat
REM Windows (cmd) — z katalogu repozytorium
python -m pip install -e ".[dev]"
```

```bash
# Linux / macOS / Git Bash
python3 -m pip install -e ".[dev]"
```

| Polecenie | Rola |
|-----------|------|
| `gcode-index` | CLI: `scan` / `search` / `extract` |
| `gcode-index-gui` | GUI tkinter |

## Zdolności GUI (`can_index` w ini)

| `can_index` | Kto | Co widać |
|-------------|-----|----------|
| **no** (domyślnie / hala) | Operator | Tylko odczyt — otwórz bazę, szukaj, **Uwzględniaj nieprzypisane** (zablokowane ON), podgląd (+ szukanie w podglądzie), **Wydobądź**. Opcjonalnie mapowanie ścieżek i **Odświeżaj wyniki**. |
| **yes** (PC indeksatora) | Indeksator | Zakładki **Praca** / **Indeks**; skan; **Role folderów…** (prototyp/osobisty/system/przyrząd); obserwacja Auto\|Poll; … |

Blokada wdrożenia: `settings_locked=yes` albo pusty `operator.lock` / `can_index.lock` obok ini wymusza odczyt. Legacy `[ui] mode=simple|full` nadal się wczytuje (`simple`→`no`, `full`→`yes`). Wszystkie klucze: `gcode-index.ini.example`.

Foldery: **kopia** · **baza** (`target`) · **wydobycie** (`extract`, puste = jak baza).

### Po skanie przyrostowym

Indeksator (Watch / auto-indeks) nadpisuje współdzielony `gcode_index.sqlite`. Na hali zaznacz **Odświeżaj wyniki** — bieżące wyszukiwanie uruchamia się ponownie po zmianie mtime bazy (~20 s), bez czyszczenia filtrów.

## Windows — gotowy `.exe`

Actions → workflow **Windows GUI build** → pobierz artefakt `gcode-index-gui-windows-<ver>-bN.zip` → uruchom `gcode-index-gui.exe` z rozpakowanego folderu.

Szczegóły instalacji, formatów i CLI: angielski [README.md](README.md).
