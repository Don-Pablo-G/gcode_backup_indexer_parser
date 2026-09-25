# Instrukcja operatora — tryb Prosty

**Dla kogo:** operatorzy na hali, którzy mają **znaleźć i wydobyć** program z istniejącej bazy.  
**Tryb:** **Prosty** (domyślny). Ten tryb **nie buduje** i **nie aktualizuje** bazy.

---

## Do czego służy program

Indeksator trzyma katalog programów CNC znalezionych w kopiach zapasowych: numer programu, numer części, maszyna, data oraz lokalizacja na dysku.  
W trybie Prostym **otwierasz ten katalog**, szukasz, podglądasz i **wydobywasz** plik programu dla innego narzędzia lub maszyny.

Plików kopii zapasowej nigdy nie zmieniasz. Wydobycie zawsze zapisuje do osobnego folderu.

---

## Pierwsze kroki

1. W razie potrzeby ustaw język (**Język** → `pl` lub `en`).
2. Pozostań w trybie **Prosty** (albo wróć do niego przez **Tryb**).
3. Kliknij zielony przycisk **Otwórz istniejącą bazę…** i wskaż `gcode_index.sqlite`.  
   Albo ustaw **folder z bazą** (folder, w którym leży ten plik) w sekcji Foldery.

Opcjonalne foldery:

| Folder | Znaczenie |
|--------|-----------|
| **Folder z bazą** | Tu jest `gcode_index.sqlite` (wymagany) |
| **Folder wydobycia** | Tu trafiają zapisane programy (puste = ten sam co folder bazy) |
| **Folder kopii** | Potrzebny tylko gdy wydobycie musi odtworzyć ścieżki względne z oryginalnego drzewa |

**Zmień…** edytuje foldery; **Gotowe** zwija pasek.

---

## Szukanie programu

1. Wpisz w polu **Tekst** — nr programu, nr części lub fragment ścieżki (np. `O03232`, `3232`, `P-00253232`). Wielkość liter nie ma znaczenia; `O03232` / `03232` / `3232` to ten sam numer O.
2. Opcjonalnie **Maszyny** — wielokrotny wybór (Ctrl/Shift+klik). Puste / wszystkie = każda maszyna.
3. Opcjonalnie **Data od / do** w formacie `DD.MM.RRRR`.
4. Zaznacz **Tylko najnowsze**, aby zostawić jeden wiersz na program + maszynę (najnowsza data).
5. Kliknij **nagłówek kolumny** w tabeli wyników, aby sortować rosnąco/malejąco (ponowny klik odwraca kierunek).

Wyniki są w tabeli. **Podgląd** po prawej pokazuje treść zaznaczonego programu.

---

## Wydobycie

1. Zaznacz jeden lub więcej wierszy (Ctrl/Shift+klik).
2. Kliknij zielony **Wydobądź zaznaczone…** albo kliknij dwukrotnie wiersz.  
   Prawy przycisk myszy: wydobycie / otwórz folder / kopiuj ścieżkę.
3. Wybierz miejsce zapisu (domyślnie folder wydobycia).

Jeśli plik źródłowy zmienił się od ostatniego indeksu, wydobycie może zostać odmówione — poproś osobę z trybem **Pełny** o ponowny skan.

---

## Flagi w wynikach

| Kolumna / kolor | Znaczenie |
|-----------------|-----------|
| **Zielona** flaga pochodzenia | Z głównej kopii / złapania z maszyny |
| **Żółta** | Z dodatkowego folderu (nie z kopii) |
| **MACHINE UNKNOWN** | Ścieżka nie pasowała do znanej nazwy maszyny ani aliasu |

Te wartości powstają przy budowie bazy (tryb Pełny). Prosty tylko je odczytuje.

---

## Przejście do trybu Pełny

**Tryb → Pełny**, gdy trzeba **indeksować / skanować**, mapować foldery, edytować aliasy albo włączyć auto-indeks.  
Zobacz **Instrukcję indeksatora (Pełny)** w menu Pomoc.

---

## Wskazówki

- Ustawienia tego komputera są w `gcode-index.ini` obok pliku exe.
- **Wyczyść filtry** zeruje pasek wyszukiwania.
- Gdy brak wyników: sprawdź, czy otwarto właściwą bazę i czy niedawno zrobiono skan w trybie Pełnym.
