# Instrukcja operatora — klient hali (`can_index=no`)

**Dla kogo:** operatorzy na hali, którzy mają **znaleźć i wydobyć** program z istniejącej bazy.  
**Zdolność:** w `gcode-index.ini` obok exe ustaw `can_index = no` (komputery na hali). Ta instalacja **nie buduje** i **nie aktualizuje** bazy.

Uwaga: starsze instalacje z `[ui] mode=simple` mapują się na `can_index=no`.

---

## Do czego służy program

Indeksator trzyma katalog programów CNC znalezionych w kopiach zapasowych: numer programu, numer części, maszyna, data oraz lokalizacja na dysku.  
Na kliencie hali **otwierasz ten katalog**, szukasz, podglądasz i **wydobywasz** plik programu dla innego narzędzia lub maszyny.

Plików kopii zapasowej nigdy nie zmieniasz. Wydobycie zawsze zapisuje do osobnego folderu.

---

## Pierwsze kroki

1. W razie potrzeby ustaw język (**Język** → `pl` lub `en`).
2. Sprawdź, że na tym PC w `gcode-index.ini` jest `can_index = no` (domyślnie dla kopii halowych).
3. Kliknij zielony przycisk **Otwórz istniejącą bazę…** i wskaż `gcode_index.sqlite`.

Opcjonalnie: w **Zmień…** ustaw **folder wydobycia** (puste = ten sam folder co otwarta baza). Na kliencie hali **nie ma** pól folderu kopii ani folderu bazy — katalog wybierasz przez **Otwórz istniejącą bazę…**.

---

## Szukanie programu

1. Wpisz w polu **Tekst** — nr programu, nr części lub fragment ścieżki (np. `O03232`, `3232`, `P-00253232`). Wielkość liter nie ma znaczenia; `O03232` / `03232` / `3232` to ten sam numer O.
2. Opcjonalnie **Maszyny** — wielokrotny wybór (Ctrl/Shift+klik). Puste / wszystkie = każda maszyna.
3. Opcjonalnie **Data od / do** w formacie `DD.MM.RRRR` (albo mały kalendarz przez **▾** obok pola).
4. Zaznacz **Tylko najnowsze**, aby zostawić jeden wiersz na program + maszynę (najnowsza data).
5. Kliknij **nagłówek kolumny** w tabeli wyników, aby sortować rosnąco/malejąco (ponowny klik odwraca kierunek).

Wyniki są w tabeli. **Podgląd** jest na stałe **po prawej** (pełna wysokość, rozciągany) — nie pod tabelą.

---

## Wydobycie

1. Zaznacz jeden lub więcej wierszy (Ctrl/Shift+klik).
2. Kliknij zielony **Wydobądź zaznaczone…** albo kliknij dwukrotnie wiersz.  
   Prawy przycisk myszy: wydobycie / otwórz folder / kopiuj ścieżkę.
3. Wybierz miejsce zapisu (domyślnie folder wydobycia).

Jeśli plik źródłowy **nie istnieje** na dysku (kolumna **Źródło = BRAK**) albo zmienił się od ostatniego indeksu, wydobycie jest **odmówione** z jasnym komunikatem — poproś osobę na **PC indeksatora** (`can_index=yes`) o ponowny skan (albo sprawdź mapowanie ścieżek).

---

## Flagi w wynikach

| Kolumna / kolor | Znaczenie |
|-----------------|-----------|
| **Zielona** flaga pochodzenia | Z głównej kopii / złapania z maszyny |
| **Żółta** | Z dodatkowego folderu (nie z kopii) |
| **Źródło = BRAK** (czerwony wiersz) | Plik źródłowy zniknął z dysku od ostatniego skanu — jest w bazie, ale wydobycie / podgląd się nie uda |
| **MACHINE UNKNOWN** | Ścieżka nie pasowała do znanej nazwy maszyny ani aliasu |

Te wartości powstają przy budowie bazy na indeksatorze. Klient hali tylko je odczytuje.

---

## Indeksowanie na innym PC

W GUI **nie ma** przełącznika Tryb. Komputery na hali mają `can_index=no`; PC indeksatora ma `can_index=yes` we własnym `gcode-index.ini`.  
Zobacz **Instrukcję indeksatora** w menu Pomoc.

## Mapowanie ścieżek (klient)

Gdy indeks powstał na serwerze z dyskiem **C:**, a ten komputer widzi ten sam udział jako **Z:**, ustaw w **Zmień…** sekcję **Mapowanie ścieżek (klient)**:

- **Prefiks w indeksie** = `C:\…` (jak w bazie / `scan_root`)
- **Prefiks lokalny** = `Z:\…` (jak u Ciebie)

Działa dla głównej kopii oraz folderów zielonych/żółtych na tym samym prefiksie. Szukanie działa bez mapowania; **Wydobądź** / podgląd używają mapy. Zapis: `gcode-index.ini` → `[path_remap]`.

---

## Odświeżanie wyników

Opcjonalnie: **Odświeżaj wyniki** — tabela aktualizuje się, gdy indeksator zapisze nową bazę (udział sieciowy). Bez ponownego wpisywania szukania.

## Blokada operatora

Gdy jest `operator.lock` (lub `settings_locked=yes`), PC zostaje w trybie odczytu nawet po edycji `can_index=yes` w ini.

## Wskazówki

- Ustawienia tego komputera są w `gcode-index.ini` obok pliku exe.
- **Wyczyść filtry** zeruje pasek wyszukiwania.
- Gdy brak wyników: sprawdź, czy otwarto właściwą bazę i czy niedawno zrobiono skan na indeksatorze.
- Wszystkie klucze opisane (zakomentowane) są w `gcode-index.ini.example`.
