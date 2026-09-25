# Instrukcja indeksatora — tryb Pełny

**Dla kogo:** osoby, które **budują i utrzymują** bazę programów z drzew kopii CNC.  
**Tryb:** **Pełny**.

Operatorzy, którzy tylko szukają i wydobywają, powinni używać trybu **Prosty** i instrukcji operatora.

---

## Rola trybu Pełnego

Tryb Pełny pozwala:

- Skanować drzewa kopii i zapisywać / aktualizować `gcode_index.sqlite`
- Dodawać katalogi **zielone** (z maszyny) i **żółte** (dodatkowe)
- Uruchamiać **auto-indeks** według harmonogramu, gdy GUI jest otwarte
- Mapować dziwne nazwy folderów na maszyny i edytować **lokalne aliasy**
- Korzystać z filtrów zaawansowanych, presetów, porównania, raportu skanu, duplikatów
- Opcjonalnie zapisać Excel po skanie

---

## Foldery

| Folder | Znaczenie |
|--------|-----------|
| **Folder kopii** | Główne drzewo kopii CNC (`DATA\MASZYNA\…`) |
| **Folder bazy** (`target`) | `gcode_index.sqlite` + pliki pomocnicze (`machine_folders.yaml`, `aliases.local.yaml`, `ui_settings.yaml`, …) |
| **Folder wydobycia** | Domyślny zapis Wydobądź (puste = ten sam co folder bazy) |

### Dodatkowe katalogi

- **Zielony** — jak z maszyny / folder „łapacza” luźnych `.nc` (zanim znikną z backupu). Podfoldery są skanowane rekurencyjnie. Programy dostają **zieloną** flagę pochodzenia.
- **Żółty** — dodatkowe drzewa spoza kopii maszyny. Programy dostają flagę **żółtą**.

Katalogi zapisują się jako `extra_scan_roots.yaml` obok bazy (oraz w `gcode-index.ini`).

---

## Mapowanie folderów i aliasy

1. **Mapuj foldery…** — wykrywa foldery `<data>/<maszyna>`, automatycznie dopasowuje znane aliasy i pokazuje tylko niedopasowane do ręcznego przypisania. Mapa: `machine_folders.yaml` (ma pierwszeństwo przed aliasami).
2. Opcjonalnie: zapisz przypisania jako **lokalne aliasy** (`aliases.local.yaml`) na kolejne skany.
3. **Aliasy…** — lista maszyn po lewej; wybierz maszynę, aby edytować jej **aliasy folderów**, etykietę, sterowanie i layout. **Dodaj maszynę** / **Usuń maszynę** zarządzają maszynami lokalnymi. Aliasy z katalogu (`[bundled]`) są tylko do odczytu — dodaj lokalną pisownię, aby je nadpisać. Zapis: `aliases.local.yaml`.

### Przypisanie maszyny dla luźnych `.nc`

Przy indeksowaniu pojedynczych plików `.nc` / `.nc.copy` skaner przechodzi foldery nadrzędne **od najgłębszego**. Pierwsza nazwa pasująca do mapy folderów lub aliasu staje się **maszyną** dla tego pliku i wszystkiego w tym folderze. Brak dopasowania → **MACHINE UNKNOWN** (plik i tak jest indeksowany).

---

## Indeksuj / skanuj

1. Ustaw folder kopii + folder bazy (oraz dodatkowe, jeśli potrzeba).
2. Kliknij zielony **Indeksuj / skanuj**.
3. Opcje (drugi wiersz paska pod **Indeksuj**):
   - **Przyrostowo** — pomija niezmienione pliki (rozmiar + mtime); ponownie używa wcześniejszych wierszy
   - **Zapisz też Excel** — eksport skoroszytu obok bazy po skanie
   - **Obserwuj foldery** — patrz niżej
4. Pasek postępu pokazuje liczbę plików i ETA. Po zakończeniu otwiera się **raport skanu** (także przez **Raport skanu…** w tym samym wierszu).

### Auto-indeks

W trybie Pełnym ustaw **Auto-indeks** (po prawej w drugim wierszu paska) na co godzinę / codziennie / co tydzień. Gdy GUI jest otwarte, należne skany uruchamiają się same. Tryb Prosty ukrywa i wyłącza tę funkcję.

### Obserwuj foldery

W **drugim** wierszu paska trybu Pełnego zaznacz **Obserwuj foldery**, aby co kilka sekund sprawdzać drzewo kopii i katalogi dodatkowe (zielone/żółte). Gdy pojawią się nowe lub zmienione pliki indeksowalne, aplikacja czeka chwilę (debounce), potem uruchamia skan **przyrostowy** (bez pełnej przebudowy).

- Tylko w trybie **Pełnym**.
- Tworzy `gcode_index.lock` obok bazy — **jeden komputer** obserwuje / indeksuje. Inne instancje Pełne zobaczą „Obserwacja zablokowana”. Tryb Prosty nie bierze blokady.
- Zalecenie: jeden PC indeksujący z Obserwuj; pozostałe — Prosty na tej samej bazie.

---

## Szukanie i wydobycie

Ten sam pasek wyszukiwania co w trybie Prostym, plus:

- **Więcej filtrów** — typ źródła, sterowanie, flaga (zielona/żółta), programista, presety
- **Porównaj…** — różnice dwóch zaznaczonych wierszy
- **Duplikaty…** — grupy dokładnych i podobnych kopii
- **Otwórz folder** / **Kopiuj ścieżkę** do pliku źródłowego

**Wydobądź** zapisuje treść programu do folderu wydobycia (lub wskazanej ścieżki). Źródeł nigdy nie modyfikuje. Sprawdza SHA-256 + rozmiar z czasu skanu.

---

## Ustawienia instancji

`gcode-index.ini` obok exe pamięta foldery, zieleń/żółć, język, tryb, harmonogram i rozmiar okna. Ścieżkę można nadpisać zmienną `GCODE_INDEX_INI=…`.

---

## Kopie Haas NGC w ZIP

Skaner **nie otwiera** plików `.zip`. Najpierw rozpakuj kopię Haas NGC do folderu maszyny (np. `…/HaasBackup(…)/Memory/**/*.nc`), potem skanuj.

---

## Przejście do trybu Prosty

**Tryb → Prosty** ukrywa indeksowanie — operator tylko otwiera bazę, szuka i wydobywa. Zobacz **Instrukcję operatora (Prosty)**.
