# G-code backup indexer / parser

Indeksuje **drzewa kopii zapasowych** maszyn CNC do przenośnego katalogu **SQLite** z **wystąpieniami programów** (nr programu, nr części, maszyna, data, lokalizacja źródła). Pełne parsowanie G-code jest **poza zakresem** — narzędzie wyciąga **nagłówki + lokalizacje**, żeby ludzie i inne programy mogły szukać i później wydobywać zakresy.

**Repozytorium:** https://github.com/Don-Pablo-G/gcode_backup_indexer_parser

**English README:** [README.md](README.md)

## Dokumentacja użytkownika

| Dokument | Dla kogo |
|----------|----------|
| [Instrukcja operatora (Prosty)](docs/pl/manual-simple.md) | Szukanie i wydobycie z gotowej bazy |
| [Instrukcja indeksatora (Pełny)](docs/pl/manual-full.md) | Budowa i utrzymanie bazy |
| Same manuals in English | [docs/en/](docs/en/) |

W aplikacji GUI: menu **Pomoc** (otwiera te same instrukcje w oknie).

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

## Tryby GUI

| Tryb | Kto | Co widać |
|------|-----|----------|
| **Prosty** (domyślny) | Operator | Tylko odczyt — otwórz bazę, szukaj, podgląd, **Wydobądź** |
| **Pełny** | Indeksator | Skan, zieleń/żółć, zakładki **Praca/Indeks**, harmonogram, **obserwacja folderów** (+ pasek statusu), Windows **autostart** / **zasobnik**, mapa/aliasy, filtry zaawansowane, … |

Foldery: **kopia** · **baza** (`target`) · **wydobycie** (`extract`, puste = jak baza).

## Windows — gotowy `.exe`

Actions → workflow **Windows GUI build** → pobierz artefakt `gcode-index-gui-windows-<ver>-bN.zip` → uruchom `gcode-index-gui.exe` z rozpakowanego folderu.

Szczegóły instalacji, formatów i CLI: angielski [README.md](README.md).
