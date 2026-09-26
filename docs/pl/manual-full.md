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
| **Folder bazy** (`target`) | `gcode_index.sqlite` + pliki pomocnicze (`machine_folders.yaml`, `folder_tree_map.yaml`, `folder_colour_aliases.yaml`, …) |
| **Folder wydobycia** | Domyślny zapis Wydobądź (puste = ten sam co folder bazy) |

Wybór folderów **nie zwija** sekcji — dokończ ścieżki, potem **Gotowe**.

### Dodatkowe katalogi

- **Zielone** — złapania z maszyny / luźne `.nc`. Flaga zielona.
- **Żółte** — dodatkowe drzewa nie z kopii. Flaga żółta = status nieznany.

Zapis: `extra_scan_roots.yaml` obok bazy (oraz `gcode-index.ini`).

**Zagnieżdżone katalogi:** **najgłębszy** skonfigurowany root (główna kopia lub zielony/żółty), który zawiera plik, go „posiada” — jego kolor i `scan_root`. Przykład: żółty rodzic + zielone dziecko → pliki w dziecku tylko **zielone** (bez duplikatu żółtego). Przy dodaniu rootu wewnątrz innego pojawia się krótka informacja, że dziecko nadpisuje kolor rodzica.

### Status + role folderów

**Status** (czy był na maszynie?) pochodzi tylko z korzeni skanu — nigdy z aliasów folderów:

| Odznaka | Znaczenie | Źródło |
|---------|-----------|--------|
| 🟢 | Na maszynie (`backup`) | Główna kopia, klejone dumpy, zielone catch |
| 🟡 | Status nieznany (`extra`) | Żółte foldery dodatkowe |

**Role folderów…** (indeksator) edytuje `folder_colour_aliases.yaml` obok bazy:

1. **Role** — dodaj / edytuj / usuń (`id`, etykiety PL+EN, wybór koloru / paleta, opcjonalny hex, odznaka, znaczenie). Startowo: **prototyp** (niebieski), **osobisty** (czerwony), **programy systemowe** (pomarańczowy), **przyrząd** (fioletowy). Wbudowanych nie usuniesz. Żółty/zielony to wyłącznie status — żółty **nigdy** nie oznacza przyrządu. Stare seedy (produkcja / WIP / test) zostają jako własne role, jeśli były w pliku.
2. **Aliasy folderów** — nazwa folderu → rola **albo wyklucz**. Najgłębszy segment wygrywa. Aliasy nigdy nie zmieniają statusu. Wiele ról na folderze ustawisz w mapie drzewa.

**Mapuj drzewo…** (indeksator) edytuje `folder_tree_map.yaml` obok bazy: leniwe drzewo z kopii + zielonych/żółtych korzeni. Per węzeł: maszyna (opcjonalnie), **wiele ról**, wyklucz lub wyczyść. ★ = reguła jawna, · = dziedziczona. **Najdłuższy prefiks ścieżki wygrywa** nad aliasami nazw (tagi ścieżki **zastępują** unię ról z nazw). **Prawy klik** na folder → *Alias nazwy „…” wszędzie* → maszyna albo rola (dokładna nazwa; role z aliasów nazw się kumulują). Statusu z menu nie zmienisz. Reindeks stosuje zapisane reguły.

Kolumna Flaga pokazuje **status + odznaki ról**. Osobne filtry **Status** i **Rola** (filtr roli łapie dowolny tag). Duplikaty oznaczają konflikty ról (i statusu). Po aktualizacji **przeskanuj**, żeby wypełnić `role`.

---

## Mapowanie folderów i aliasy

1. **Mapuj foldery…** — wykrywa `<data>/<maszyna>`, dopasowuje aliasy, listuje tylko niedopasowane.
2. **Mapuj drzewo…** — leniwe drzewo ścieżek: maszyna + wiele ról + wyklucz (`folder_tree_map.yaml`; najgłębsza ścieżka wygrywa).
3. Opcjonalnie zapisz jako **lokalne aliasy** (`aliases.local.yaml`).
4. **Maszyny i aliasy…** — lista maszyn; edycja aliasów folderów, etykiety, sterowania.

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

Jak na kliencie hali, plus:

- **Uwzględniaj nieprzypisane** / **Include unassigned** (domyślnie **ON**) — przy aktywnym filtrze maszyn zostawia w wynikach **MACHINE UNKNOWN** / `unmapped:…`. Wyłączenie pokazuje ostrzeżenie. Zapis: `[scan] include_unknown` w `gcode-index.ini`. Na kliencie hali i przy blokadzie zawsze **ON** (kontrolka wyłączona).
- **Więcej filtrów**, **Porównaj…**, **Duplikaty…** (dokładne grupy po SHA ciała programu `program_sha256` — wycinek klejonego dumpa może zgadzać się z luźnym `.nc`; odznaki kolorów przy członkach; **Konflikt kolorów**, gdy to samo ciało ma ≥2 kolory — filtr „Tylko konflikt kolorów”; po aktualizacji **przeskanuj** ponownie). Wydobycie sprawdza SHA całego pliku (`content_sha256`) + rozmiar ze skanu.

---

## Historia skanów

**Historia skanów…** (tylko indeksator) — ostatnie przebiegi z `scan_history.json` obok bazy: kiedy, czas, programy, pliki **dodane / zmienione / usunięte / bez zmian**. Przydatne przy diagnostyce skoków sieci.

## Blokada operatora

Komputery na hali: `settings_locked = yes` w ini **albo** pusty plik `operator.lock` / `can_index.lock` obok ini. Wtedy `can_index` jest wymuszane na **no**.

## Odświeżanie wyników (klienci po skanie przyrostowym)

Zaznacz **Odświeżaj wyniki**, aby **ponowić bieżące wyszukiwanie**, gdy zmieni się `gcode_index.sqlite` (mtime, domyślnie ~20 s). Przydatne na hali z bazą na **udziale sieciowym**, gdy indeksator robi Obserwuj / harmonogram przyrostowy: nowe wiersze pojawiają się bez czyszczenia filtrów i bez ponownego otwierania pliku. Zapis: `search_auto_refresh` / `search_auto_refresh_s` w ini. Bez tego operator klika Szukaj ponownie po skanie.

## Ustawienia instalacji

**Ustawienia wracają po restarcie:** `gcode-index.ini` obok exe pamięta foldery, zieleń/żółć, **`can_index`**, język, harmonogram, desktop, geometrię, przełączniki skanu, mapowanie ścieżek, **ostatnie filtry wyszukiwania** (tekst, maszyny, daty, status, role, …), sortowanie oraz widok Praca/Indeks.  

Pliki pomocnicze obok bazy (`machine_folders.yaml`, `folder_tree_map.yaml`, `folder_colour_aliases.yaml`, `aliases.local.yaml`, …) wczytują się z folderem bazy — przypisania drzewa/ról/maszyn nie giną po restarcie.  

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
