# Instrukcja indeksatora (`can_index=yes`)

**Dla kogo:** osoby, które **budują i utrzymują** bazę programów z drzew kopii CNC.  
**Zdolność:** w `gcode-index.ini` obok exe ustaw `can_index = yes` (PC indeksatora).

Operatorzy na hali powinni mieć `can_index = no` i instrukcję operatora.

Uwaga: starsze instalacje z `[ui] mode=full` mapują się na `can_index=yes`.

---

## Rola indeksatora

Przy `can_index=yes` GUI może:

- Skanować drzewa kopii i zapisywać / aktualizować `gcode_index.sqlite`
- Dodawać katalogi **zielone** (z maszyny) i **żółte** (dodatkowe)
- Uruchamiać **auto-indeks** według harmonogramu, gdy GUI jest otwarte
- Mapować dziwne nazwy folderów na maszyny i edytować **lokalne aliasy**
- Korzystać z filtrów zaawansowanych, presetów, porównania, raportu skanu, duplikatów
- Opcjonalnie zapisać Excel po skanie
- Używać Windows **autostart** / **zasobnik**

Układ indeksatora ma dwa główne segmenty nawigacji (duży pasek u góry):

| Zakładka | Zawartość |
|----------|-----------|
| **Praca** | Szukanie / filtry / **tabela wyników** \| **pełny podgląd po prawej** — czysta powierzchnia pracy. Jedna linia ścieżek + **Foldery…** do Indeksu. Główne CTA: **Wydobądź**. |
| **Indeks** | Foldery kopii/bazy/wydobycia, zielone/żółte, mapowanie ścieżek, **Indeksuj/skanuj**, mapa, maszyny i aliasy, przyrostowo, obserwacja, harmonogram, historia, autostart/zasobnik, raport/duplikaty/Excel |

Klient hali (`can_index=no`) zostaje na jednej powierzchni wyszukiwania — bez zakładek Praca/Indeks.

W panelu podglądu użyj **W podglądzie**, żeby znaleźć tekst w treści G-code (następny/poprzedni + podświetlenie).

---

## Mapowanie ścieżek (klient)

Gdy indeks powstał na serwerze z dyskiem **C:**, a ten komputer widzi ten sam udział jako **Z:**, ustaw w **Zmień…** sekcję **Mapowanie ścieżek (klient)**:

- **Prefiks w indeksie** = `C:\…` (jak w bazie / `scan_root`)
- **Prefiks lokalny** = `Z:\…` (jak u Ciebie)

Działa dla głównej kopii oraz folderów zielonych/żółtych na tym samym prefiksie. Szukanie działa bez mapowania; **Wydobądź** / podgląd używają mapy. Zapis: `gcode-index.ini` → `[path_remap]`.

## Foldery

| Folder | Znaczenie |
|--------|-----------|
| **Folder kopii** | Główne drzewo kopii CNC (`DATA\MASZYNA\…`) |
| **Folder bazy** (`target`) | `gcode_index.sqlite` + pliki pomocnicze |
| **Folder wydobycia** | Domyślny zapis Wydobądź (puste = ten sam co folder bazy) |

Wybór folderów **nie zwija** sekcji — dokończ ścieżki, potem **Gotowe**.

### Dodatkowe katalogi

- **Zielone** — złapania z maszyny / luźne `.nc`. Flaga zielona.
- **Żółte** — dodatkowe drzewa nie z kopii. Flaga żółta.

Zapis: `extra_scan_roots.yaml` obok bazy (oraz `gcode-index.ini`).

---

## Mapowanie folderów i aliasy

1. **Mapuj foldery…** — wykrywa `<data>/<maszyna>`, dopasowuje aliasy, listuje tylko niedopasowane.
2. Opcjonalnie zapisz jako **lokalne aliasy** (`aliases.local.yaml`).
3. **Maszyny i aliasy…** — lista maszyn; edycja aliasów folderów, etykiety, sterowania.

---

## Indeksuj / skanuj

1. Ustaw folder kopii + bazy (i dodatki), albo **Otwórz istniejącą bazę…**.
2. Zielony **Indeksuj / skanuj**.
3. Opcje: **Przyrostowo**, **Zapisz też Excel**, **Obserwuj foldery**.
4. Pasek postępu + **Raport skanu** po zakończeniu.

### Auto-indeks

Ilość + jednostka (sekundy / minuty / godziny / dni). Klient hali (`can_index=no`) tego nie uruchamia. Live **odliczanie** do następnego uruchomienia.

### Obserwacja folderów

Zaznacz **Obserwuj foldery** — po zmianach w kopii / zielonych/żółtych katalogach uruchamia się **przyrostowy** skan (po krótkim debounce).

Obok checkboxa wybierz **metodę** (przełącznik segmentowy):

| Metoda | Zachowanie |
|--------|------------|
| **Auto** (`watch_mode=hybrid`) | Zdarzenia OS na dyskach lokalnych; stamp-**poll** na udziałach sieciowych / UNC (`Z:\…`, `\\serwer\udział`) |
| **Tylko poll** (`watch_mode=poll`) | Stamp-poll wszędzie (bezpieczny fallback / poprzednie zachowanie) |

Pasek statusu pokazuje metodę per katalog (np. `D:\CNC=events · Z:\Share=poll`). Wybór zapisuje się w `gcode-index.ini` → `[scan] watch_mode`.

- Tylko przy `can_index=yes`.
- Blokada `gcode_index.lock` obok bazy — **jeden PC** obserwuje.
- Zalecenie: jeden PC indeksujący z Obserwuj; pozostałe — `can_index=no` na tej samej bazie.
- Pasek **Obserwacja** pokazuje poll / pliki / ostatni skan / metodę per root / posiadacza blokady.

### Autostart i zasobnik (Windows)

- **Autostart przy logowaniu** (skrót albo Harmonogram zadań) — `[desktop]` w ini.
- **Zamknij do zasobnika** / **Minimalizuj do zasobnika**.
- GUI jest **jednoinstancyjne** (w tym z zasobnika).

---

## Szukanie i wydobycie

Jak na kliencie hali, plus **Więcej filtrów**, **Porównaj…**, **Duplikaty…**. Wydobycie sprawdza SHA-256 + rozmiar ze skanu.

---

## Historia skanów

**Historia skanów…** (tylko indeksator) — ostatnie przebiegi z `scan_history.json` obok bazy: kiedy, czas, programy, pliki **dodane / zmienione / usunięte / bez zmian**. Przydatne przy diagnostyce skoków sieci.

## Blokada operatora

Komputery na hali: `settings_locked = yes` w ini **albo** pusty plik `operator.lock` / `can_index.lock` obok ini. Wtedy `can_index` jest wymuszane na **no**.

## Odświeżanie wyników

Zaznacz **Odświeżaj wyniki**, aby ponowić bieżące wyszukiwanie, gdy zmieni się `gcode_index.sqlite` (mtime, domyślnie ~20 s). Zapis: `search_auto_refresh` w ini.

## Ustawienia instalacji

`gcode-index.ini` obok exe pamięta foldery, zieleń/żółć, **`can_index`**, język, harmonogram, desktop i geometrię.  
Wszystkie klucze są opisane w `gcode-index.ini.example`.

Wdrożenie:

- Komputery na hali → `can_index = no`
- PC indeksatora → `can_index = yes`

---

## Kopie Haas NGC w ZIP

Skaner **nie** otwiera `.zip`. Najpierw rozpakuj do folderu maszyny, potem skanuj.

---

## Klienci hali

Nie ma przełącznika **Tryb** w GUI. Na PC operatora ustaw `can_index = no`. Zobacz **Instrukcję operatora (odczyt)**.
