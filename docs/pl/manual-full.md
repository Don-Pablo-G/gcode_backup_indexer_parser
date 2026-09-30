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
- Obserwować foldery z min. przerwą i opcjonalnym skanem bezpieczeństwa, gdy GUI jest otwarte
- Mapować dziwne nazwy folderów na maszyny i edytować **lokalne aliasy**
- Korzystać z filtrów zaawansowanych, widoków, porównania, raportu / jakości skanu, duplikatów
- Opcjonalnie zapisać Excel po skanie
- Używać Windows **autostart** / **zasobnik**

Układ indeksatora ma dwa główne segmenty nawigacji (duży pasek u góry):

| Zakładka | Zawartość |
|----------|-----------|
| **Praca** | Szukanie / filtry / **tabela wyników** \| **pełny podgląd po prawej** — czysta powierzchnia pracy. Jedna linia ścieżek + **Foldery…** do Indeksu. Główne CTA: **Wydobądź**. |
| **Indeks** | Foldery kopii/bazy/wydobycia, zielone/żółte (krążki jak Flaga), **Uruchom skan** (po prawej), drzwi **Mapowanie…** / **Skan i obserwacja…** / **Raporty…** |

Klient hali (`can_index=no`) zostaje na jednej powierzchni wyszukiwania — bez zakładek Praca/Indeks.

W oknie podglądu użyj **W podglądzie**, żeby znaleźć tekst w treści G-code (następny/poprzedni + podświetlenie). Przycisk **Wydobądź do…** w wierszu akcji podglądu zapisuje oglądany program do wybranego folderu (te same zasady co menu kontekstowe wyników).

---

## Mapowanie ścieżek (klient)

Gdy indeks powstał na serwerze z dyskiem **C:**, a ten komputer widzi ten sam udział jako **Z:** (albo masz kilka udziałów), otwórz **Foldery** (**Zmień…** na pasku Indeks lub rozwinięcie folderów) i w sekcji **Mapowanie ścieżek (klient)** dodaj jedną lub więcej reguł (**Dodaj…**):

- **Prefiks w indeksie** = `C:\…` (jak w bazie / `scan_root`)
- **Prefiks lokalny** = `Z:\…` (jak u Ciebie)

Kilka reguł jest dozwolonych — **najdłuższy pasujący prefiks wygrywa**. Działa dla głównej kopii oraz folderów zielonych/żółtych na tym samym prefiksie. Szukanie działa bez mapowania; **Wydobądź** / podgląd używają mapy. Zapis: `gcode-index.ini` → `[path_remap]`.

Indeksator i klient hali mają **to samo miejsce**: obok ustawiania folderów / wydobycia. **Mapowanie…** to tylko nauka paczki (nazwy, drzewo, katalogi) — bez mapowania ścieżek.

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

**Status** (czy był na maszynie?) zapisuje się z korzeni skanu (`backup` / `extra`) — aliasy folderów nie zmieniają tego pola w bazie:

| Odznaka | Znaczenie | Źródło |
|---------|-----------|--------|
| 🟢 | Z maszyny (`backup`) | Główna kopia (**z backupu**) lub zielony catch / zaufany folder (**zaufany folder**); ten sam zielony krążek — tip pokazuje który |
| 🟡 | Status nieznany (`extra`) | Inne poddrzewa (żółte dodatki itd.) |

**Kolumna Flaga = status + różne kolory funkcji.** Zawsze jeden krążek zielony **lub** żółty (status), chyba że rola z **może zastąpić kolor statusu** go zastąpi (prototyp domyślnie włączony → jeden niebieski). Potem jeden krążek na każdy **inny** kolor funkcji z ról wiersza (np. programy systemowe pomarańcz obok zielonego). Ten sam kolor nigdy się nie dubluje. Kolor czcionki wiersza podąża za **głównym** krążkiem (status lub nadpisanie). Prawdziwe wielokolorowe krążki są rysowane jako obraz (nie kilka znaków tekstu).

**`folder_colour_aliases.yaml` jest obowiązkowy** obok `gcode_index.sqlite` dla prawdziwych kolorów Flagi na każdym kliencie (hala lub indeksator). Otwarcie bazy bez tego pliku używa domyślnych kolorów z tej wersji oprogramowania i pokazuje ostrzeżenie. **`folder_tree_map.yaml`** jest potrzebny, gdy tip Flagi ma pokazywać powody ścieżek z Mapuj drzewo.

**Role i aliasy…** (indeksator) edytuje `folder_colour_aliases.yaml` obok bazy — ten sam układ co **Maszyny i aliasy**. Status / Flaga nie są edytowane w tym oknie; przycisk **Status i Flaga…** otwiera tę instrukcję (status, Flaga; legenda też w Praca):

1. **Lewa** — lista ról (dodaj / edytuj / usuń). Startowo: **prototyp** (niebieski, nadpisanie **włączone**), **osobisty** (czerwony), **programy systemowe** (pomarańczowy), **przyrząd** (fioletowy). Wbudowanych nie usuniesz. Żółty/zielony to wyłącznie status — żółty **nigdy** nie oznacza przyrządu. Stare seedy (produkcja / WIP / test) zostają jako własne role, jeśli były w pliku. Pod listą: pasek **Wykluczenia nazw** (pisownie → nie indeksuj).
2. **Prawa** — meta wybranej roli (`id`, etykiety PL+EN, wybór koloru / paleta, odznaka, znaczenie, **może zastąpić kolor statusu**) oraz zagnieżdżone **Aliasy folderów** tylko dla **tej** roli. Najgłębszy segment wygrywa. Aliasy ustawiają tylko role (nie nadpisują provenance). Wiele ról na folderze ustawisz w mapie drzewa.

Gdy pasująca rola ma włączone **może zastąpić kolor statusu**: Flaga gubi zielony/żółty i pokazuje krążek tej roli; kolor wiersza = kolor roli. Priorytet przy kilku nadpisaniach: **najpierw prototyp**, potem stała kolejność. Pozostałe (bez nadpisania) funkcje nadal widać jako **dodatkowe kolorowe krążki Flagi**, gdy ich barwa różni się od statusu. Kolumna tekstowa **Rola** jest opcjonalna (domyślnie ukryta; pokaż przez **Kolumny**); podpowiedź Flagi wymienia każdą funkcję z powodem alias / ścieżka / nagłówek / O9.

**Mapuj drzewo…** (indeksator) edytuje `folder_tree_map.yaml` obok bazy: leniwe drzewo z kopii + zielonych/żółtych korzeni. Per węzeł: maszyna (opcjonalnie), **wiele ról**, wyklucz lub wyczyść. ★ = reguła jawna, · = dziedziczona. **Najdłuższy prefiks ścieżki wygrywa** nad aliasami nazw (tagi ścieżki **zastępują** unię ról z nazw). **Prawy klik** na folder → *Alias nazwy „…” wszędzie* → maszyna albo rola (alias nazwy; **ta sama reguła co maszyny** — dopasowanie na granicach tokenów — dokładne pełne / dokładny token (lub kolejne tokeny), potem fuzzy tylko w jednym tokenie (podciąg ≥4 / prefiks ≥3 z krótkim residuum; np. VF2≈VF2S, nie pat→pattyn); **po aktualizacji zrób reindeks**; role z aliasów nazw się kumulują). Statusu z menu nie zmienisz. Reindeks stosuje zapisane reguły.

Osobne filtry **Status** i **Rola** (filtr roli łapie dowolny tag). Duplikaty oznaczają konflikty ról (i statusu). Po aktualizacji **przeskanuj**, żeby wypełnić `role`.

---

## Mapowanie folderów i aliasy

1. **Nazwy folderów…** — hub wiązania nazw: lista z kopii i dodatkowych korzeni (od najczęstszych), **chipy** maszyna / funkcja / odbiorca gdy przypisane. **Prawy klik** (lub podwójny) → nowy odbiorca/maszyna/funkcja z tą nazwą albo alias do istniejącego (etykieta i alias wstępnie z pisowni folderu). Katalogi Odbiorcy / Maszyny / Role służą do utrzymania list. Zapis: `aliases.local.yaml` / `folder_colour_aliases` / `odbiorcy.yaml`.
2. **Mapuj drzewo…** — leniwe drzewo ścieżek: maszyna + odbiorca + wiele ról + wyklucz (`folder_tree_map.yaml`; najgłębsza ścieżka wygrywa). Prawy klik na folder → alias nazwy wszędzie (maszyna / rola / odbiorca).
3. **Maszyny i aliasy…** — lista maszyn; edycja aliasów folderów, etykiety, sterowania. Pisownie z katalogu wbudowanego są tylko do odczytu (oznaczenie `[bundled]` — nie wpisuj tego znacznika do aliasu lokalnego; przy zapisie jest usuwany). Aliasy lokalne da się usunąć nawet gdy w tekście nadal jest `[bundled]`. Zapis: `aliases.local.yaml`. Aliasy folderów działają też na `(…)` **w linii numeru programu (O#####)** przy włączonym **Maszyna z nagłówka**, gdy wiersz jest nadal MACHINE UNKNOWN.
4. **Role i aliasy…** — ten sam wzorzec: wybierz rolę → meta + zagnieżdżone aliasy; **Wykluczenia nazw** pod listą. Te aliasy działają też na komentarze `(…)` **w linii O** gdy włączone **Role z nagłówka** (kumulacja po ścieżce/drzewie; przed O9).
5. **Odbiorcy i aliasy…** — ten sam wzorzec: wybierz odbiorcę → etykiety + zagnieżdżone aliasy; jeden odbiorca na program (jak maszyna). Aliasy nazw działają też na komentarze `(…)` **w linii O** gdy ścieżka/folder nie ustawiły odbiorcy (przełącznik **Odbiorca z nagłówka**; reindeks uzupełnia).

Dopasowanie nagłówka (to samo dla odbiorcy / roli / maszyny): komentarze w nawiasach **tylko w tej samej linii co numer programu** (`O#####`) — nie stare wieloliniowe okno nagłówka, nie kolejne linie, nie ciało programu. Sklejone zrzuty: seek do `byte_start`, potem linia O. Tylko aliasy (nie etykiety katalogu); min. długość igły 3. **Reguła:** granice tokenów (dokładne pełne / token lub kolejne tokeny, potem fuzzy tylko w jednym tokenie — podciąg ≥4 / prefiks ≥3 z krótkim residuum; VF2≈VF2S, nie pat→pattyn). **Po aktualizacji zrób reindeks.** **Maszyna z nagłówka** uzupełnia tylko gdy wiersz jest nadal **MACHINE UNKNOWN** — mapa folderów / alias nazwy / maszyna z drzewa zawsze wygrywają. Status 🟢/🟡 nigdy nie pochodzi z nagłówka.

**Głębokość skanu nagłówka (linie)** w **Skan i obserwacja → Opcje skanu** poszerza tylko listę **nieprzypisanych tokenów nagłówka** (domyślnie **1** = linia O; stop przed następnym `%`). **Nie** zmienia auto-dopasowania odbiorcy / ról / maszyny. Klucz: `[scan] header_scan_depth` w `gcode-index.ini` (1–20; brak → 1). Tylko ini indeksatora — nie pack yaml.

---

## Indeksuj / skanuj

Kolejność na **Indeks** (od góry): **1 · Foldery** (kopia / baza / wydobycie + dodatkowe) → **2 · Ustawienia** (Mapowanie / Skan i obserwacja / Raporty, gdy potrzeba) → **3 · Skan** z **Uruchom skan** po prawej.

1. Ustaw folder kopii + bazy (i dodatki), albo **Otwórz istniejącą bazę…**.
2. Zielony **Uruchom skan** (po prawej).
3. Głębsze ustawienia: **Mapowanie…** (nauka nazw + katalogi), **Skan i obserwacja…** (przyrostowo / Excel / O9 / obserwacja), **Raporty…**. Mapowanie ścieżek jest w **Folderach** (jak **Zmień…** na hali). Pulpit / zasobnik / język — w menu **Ustawienia**.
4. Pasek postępu + **Raport skanu** po zakończeniu. Z raportu (lub **Raporty…**): **Nieprzypisane tokeny nagłówka…** — częste tokeny z komentarzy w oknie od linii O (głębokość w **Opcjach skanu**, domyślnie **1** = tylko linia O; stop przed następnym `%`) bez aliasu maszyny / funkcji / odbiorcy; prawy klik jak w **Nazwy folderów**. Wykluczenia: numer programu oraz tokeny z więcej niż 4 cyframi. Cache: `header_token_freq.json` obok bazy; **pełny skan** odświeża listę (nauczone znikają). Auto-dopasowanie odbiorcy / ról / maszyny zostaje na linii O.

### Obserwacja folderów

Zaznacz **Obserwuj foldery** — nasłuchuje skonfigurowanych korzeni. Domyślnie **główny folder kopii jest wykluczony** z live Watch (zdarzenia / stamp-poll) — obserwowane są tylko zielone/żółte. Odznacz **Wyklucz folder kopii**, aby także obserwować drzewo kopii. Po zmianach w obserwowanych katalogach uruchamia się **przyrostowy** skan (debounce 3 s; stamp-poll 5 s).

Gdy obserwacja jest włączona:

- **Wyklucz folder kopii** (domyślnie **wł.**) — pomija `[folders] backup` w korzeniach Watch. Ręczny **Uruchom skan**, skan po zmianie Watch oraz opcjonalny **skan bezpieczeństwa** nadal indeksują kopię + dodatkowe przez normalny pipeline; tylko live nasłuch / poll pomija kopię, gdy opcja jest włączona.
- **Min. przerwa między skanami** (domyślnie **45 s**, min. 15 s) — po *starcie* skanu Watch kolejne sygnały zmian łączą się: co najwyżej jeden skan po wygaśnięciu przerwy.
- **Skan bezpieczeństwa** (opcjonalnie, domyślnie **wył.**) — wymuszony przyrostowy co N minut/godzin nawet bez zmian (pominięte zdarzenia / wolny UNC). To **nie** jest min. przerwa i nie nazywa się „Auto-indeks”. Opcjonalne **od HH:MM** (czas lokalny) kotwiczy interwał na zegarze — np. **24 godziny** + **00:00** = najbliższa lokalna północ, potem co 24 h. Pusty czas = dotychczasowe „od ostatniego skanu”. Udany skan aktualizuje `watch_safety_last_run`; przy ustawionym czasie następny termin nadal idzie z siatki zegara (ręczny skan w południe nie przesuwa północy na jutro w południe). Miękkie spięcie z przerwą (może ruszyć kilka minut po godzinie, gdy trwa quiet). Bezpieczeństwo nadal skanuje pełny zestaw (w tym kopię).

Klucze: `[scan] watch_exclude_backup` (domyślnie yes), `watch_coalesce_s`, `watch_safety`, `watch_safety_at` (opcjonalne `HH:MM`, brak → puste), `watch_safety_last_run`. Brakujący `watch_exclude_backup` → **yes**. Stary `[ui] schedule` migruje raz (krótkie sekundy → przerwa; minuty/godziny/dni → bezpieczeństwo).

Automatyczne skany Watch / coalesce / bezpieczeństwo aktualizują pasek statusu, ale **nie** przełączają nawigacji Praca | Indeks; tylko ręczny **Uruchom skan** skacze do Indeksu pod pasek postępu.

Klient hali (`can_index=no`) nie widzi Obserwuj. Automatyczne skany wymagają włączonej obserwacji (i biorą `gcode_index.lock`).

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

W menu głównym **Ustawienia** (wszystkie tryby — hala i indeksator):

- **Autostart przy logowaniu** (skrót albo Harmonogram zadań) — `[desktop]` w ini. Domyślnie **wyłączone** na nowych instalacjach.
- **Zamknij do zasobnika** / **Minimalizuj do zasobnika** — domyślnie **wyłączone**.
- **Język** — `pl` / `en` (przeniesione z paska; ten sam klucz `[ui] language`).
- Pasek tytułu, zasobnik systemowy i plik `.exe` używają tej samej ikony produktu (dołączonej do buildu).
- Gotowe ZIP z CI są **bez podpisu**. Podpis w sklepie: lokalnie po pobraniu (**Sign-WindowsGui.exe** / `scripts/sign-windows.ps1` + własny `.pfx`) — README EN **Local code signing**. Tworzenie certyfikatu i zaufanie na PC hali pozostają ręczne.

Istniejące wartości w ini zostają przy aktualizacji; tylko brakujące klucze biorą nowe domyślne „wyłączone”.
- GUI jest **jednoinstancyjne** (w tym z zasobnika).

---

## Szukanie i wydobycie

Jak na kliencie hali, plus:

- **Uwzględniaj nieprzypisane** / **Include unassigned** (domyślnie **ON**) — przy aktywnym filtrze maszyn zostawia w wynikach **MACHINE UNKNOWN** / `unmapped:…`. Wyłączenie pokazuje ostrzeżenie. Zapis: `[scan] include_unknown` w `gcode-index.ini`. Na kliencie hali i przy blokadzie zawsze **ON** (kontrolka wyłączona). Przełącznik w **Filtry** / **Filters** na pasku wyszukiwania.
- **Tylko zielone** / **Only green** — tylko wiersze z zielonym krążkiem Flag (kopia/zaufany); ukrywa żółte i nadpisanie prototypem. AND z innymi filtrami. Zapis: `[filters] only_green` (domyślnie wyłączone). Nazwane **widoki** też zapisują `only_green`. Przełącznik w **Filtry**.
- **Ukryj duplikaty** / **Hide duplicates** — jeden wiersz na tę samą sumę kontrolną ciała programu (`program_sha256`, globalnie między maszynami). Zachowany = zielony Flag, potem najnowsza data (puste SHA zawsze zostają). Po **Tylko najnowsze**, przed **Tylko zielone**. Zapis: `[filters] hide_duplicates` (domyślnie wyłączone; też w widokach). **Duplikaty…** w Raportach bez zmian — do podglądu grup. Przełącznik w **Filtry**.
- **Filtry** / **Filters** — wyskakujące okno na pasku: Tylko najnowsze, Ukryj duplikaty, Tylko zielone, Uwzględniaj nieprzypisane, Odświeżaj wyniki. Przycisk pokazuje liczbę aktywnych (nietypowych) przełączników. Otwarcie okna **nie** jest zapisywane (same checkboxy tak).
- **Więcej filtrów** — rozwijany panel pod paskiem wyszukiwania (▾ / ▴; stan w `[session] more_filters`, domyślnie zamknięty). Grupy: **Klasyfikacja** (typ źródła, sterowanie, status, rola, odbiorca), **Widoki** (`views.yaml` obok bazy), **Zakresy** (rozmiar / data pliku). Także na kliencie hali. Ukrycie panelu nie czyści wartości; **Wyczyść filtry** czyści pasek i zaawansowane.
- Legenda kolorów wyników: status 🟢/🟡 oraz **Nadpisania** / **Overrides** tylko dla ról z `can_override_main_state_colour` (np. Prototyp). Pozostałe role — na dyskach Flagi / tipie, nie w legendzie.
- **Jakość indeksu…** — UNKNOWN, brak odbiorcy, programy systemowe (O9000–O9099), konflikty kolorów; klik → filtr wyników
- **Porównaj…**, **Duplikaty…** (dokładne grupy po SHA ciała programu `program_sha256` — wycinek klejonego dumpa może zgadzać się z luźnym `.nc`; odznaki kolorów przy członkach; **Konflikt kolorów**, gdy to samo ciało ma ≥2 kolory — filtr „Tylko konflikt kolorów”; po aktualizacji **przeskanuj** ponownie)
- Prawy przycisk → **Wydobądź do…** — wybór folderu (ostatnie foldery w ini). Wydobycie sprawdza SHA całego pliku (`content_sha256`) + rozmiar ze skanu.

---

## Historia skanów

**Historia skanów…** (tylko indeksator) — ostatnie przebiegi z `scan_history.json` obok bazy: kiedy, czas, programy, pliki **dodane / zmienione / usunięte / bez zmian**. Przydatne przy diagnostyce skoków sieci.

---

## Nazwy i rozmieszczenie (dobre praktyki)

Jak nazywasz foldery i gdzie kładziesz drzewa, decyduje o tym, czy Flaga, maszyny, role, odbiorcy, zielony/żółty, tokeny nagłówka, Obserwuj i aliasy zostają wiarygodne. Pełny przewodnik: **Pomoc → Nazwy i rozmieszczenie…** (także [`docs/pl/naming-and-placement.md`](naming-and-placement.md) w repozytorium).

### Kopia vs zielone vs żółte

| Miejsce | Flaga |
|---------|-------|
| Główne drzewo **kopii** | 🟢 Z maszyny — podpowiedź **z backupu** |
| **Zielone** dodatkowe (zaufany catch) | 🟢 ten sam krążek — podpowiedź **zaufany folder** |
| **Żółte** dodatkowe | 🟡 Status nieznany |

Aliasy nazw nigdy nie przepisują zielonego/żółtego — tylko pochodzenie z korzenia skanu. Zagnieżdżone korzenie: najgłębszy skonfigurowany wygrywa.

### Nazwy folderów (granice tokenów)

Aliasy trafiają w **tokeny** dzielone spacją / `_` / `-`. `pat` pasuje do `pat_backup`, nie do `pattyn`. Fuzzy tylko **wewnątrz** jednego tokenu (np. `VF2`≈`VF2S`). Preferuj aliasy ≥3 znaki; unikaj krótkich igieł kolidujących między maszynami i odbiorcami.

### Uczenie maszyn / ról / odbiorców

**Nazwy folderów…** na powtarzające się pisownie, **Mapuj drzewo…** na jednorazowe nadpisania ścieżki, katalogi na utrzymanie, **Nieprzypisane tokeny nagłówka…** (raport skanu) na częste pisownie w linii O. Te same igły aliasów działają na foldery i komentarze `(…)` w linii O.

### Linia O vs głębokość listy uczenia

Auto-dopasowanie (maszyna / rola / odbiorca z nagłówka) używa komentarzy w nawiasach **tylko w linii numeru O**. **Głębokość skanu nagłówka** poszerza tylko listę uczenia (domyślnie 1 = linia O); nie poszerza auto-dopasowania. Lista uczenia pomija numery programów i tokeny z **więcej niż 4 cyframi**.

### Numery programów i O9

Programy żyją w liniach `O#####`. Opcja **O9 → programy systemowe** (domyślnie wł.) taguje **O9000–O9099** rolą `system_programs` — bez zmiany statusu, maszyny ani odbiorcy.

### Obserwuj

Domyślnie: **Wyklucz folder kopii** wł. — żywe Obserwuj obejmuje zielone/żółte. Ręczny Uruchom skan i bezpieczeństwo nadal skanują kopię + dodatkowe. Opcjonalny interwał bezpieczeństwa może użyć **o HH:MM** (zegar lokalny). Jeden PC trzyma blokadę obserwacji.

### Pakiet obok bazy

Klienci hali potrzebują całego folderu bazy: zwłaszcza `folder_colour_aliases.yaml` (obowiązkowy dla kolorów Flagi), plus mapa drzewa / aliasy / odbiorcy / dodatkowe według uczenia. Nigdy nie wkładaj `can_index` do pakietu współdzielonego.

### Krótko: rób / nie rób

**Rób:** jasna kopia vs zielone vs żółte; nazwy przyjazne tokenom; ucz przez Nazwy / Mapuj / tokeny nagłówka; tagi `(…)` w linii O; pełny pakiet obok bazy; zostaw kopię poza żywym Obserwuj, chyba że naprawdę potrzeba.  
**Nie rób:** licz na rozlewanie fuzzy prefiksu; ucz długich ciągów cyfr jako aliasów; oczekuj auto-przypisania z komentarzy poza linią O; wysyłaj samo sqlite; uruchamiaj Obserwuj na dwóch PC indeksatora.

---

## Higiena bazy na co dzień

Praktyczna rutyna, żeby **budować i utrzymywać** zdrowy indeks. Każdy udany skan przechodzi skonfigurowane drzewa (tylko odczyt), przypisuje maszynę / role / odbiorcę / status Flagi, potem **usuwa i zapisuje od nowa** `gcode_index.sqlite` w folderze bazy. **Nie ma** osobnego kroku VACUUM — rozmiar podąża za liczbą programów, nie za historią skanów. Historia jest w ograniczonym `scan_history.json` (~40 przebiegów).

### Przyrostowy vs Pełny

| Używaj **Przyrostowo** (domyślnie; zostaw zaznaczone) | Używaj **Pełny** (odznacz Przyrostowo) |
|------------------------------------------------------|----------------------------------------|
| Codzienne nowe kopie / nowe foldery pod znanymi korzeniami | Po edycji mapy maszyn lub aliasów maszyn, które mają przeassignować **stare** pliki |
| Obserwuj / przerwa / bezpieczeństwo (zawsze wymuszają przyrostowy) | Po **usunięciu** aliasów kolorów funkcji (wyczyść stare role) |
| Szybkie dogonienie, gdy większość plików bez zmian | Po wyłączeniu **O9 → programy systemowe** (albo czyszczeniu starych tagów O9) |
| Pierwszy skan po dodaniu korzenia (nowe pliki i tak nie trafią w cache) | Po dużej reorganizacji drzewa, której cache nie ufasz |
| | Raz po aktualizacji, gdy potrzebujesz świeżego `program_sha256` / higieny duplikatów na starych wierszach |

**Przyrostowy** nadal obchodzi całe drzewo, ale **reuse’uje** sparsowane wiersze, gdy **rozmiar + mtime** zgadzają się z poprzednią bazą; pełnie parsowane są tylko nowe/zmienione pliki. **Pełny** ponownie parsuje każdy indeksowalny plik i przebudowuje inferencję maszyn z dzisiejszych map/aliasów.

Zasada: **Przyrostowy utrzymuje katalog na bieżąco z dyskiem. Pełny przebudowuje przypisania z dzisiejszych map dla każdego pliku.**

### Codziennie (PC indeksatora)

1. Trzymaj **jeden** indeksator na udziale (`gcode_index.lock` / Obserwuj). Komputery hali: `can_index=no`.
2. Preferuj **Obserwuj foldery** i/lub skromny **Auto-indeks**, żeby nowe dumpy wchodziły do bazy bez pilnowania (oba biegną przyrostowo).
3. Zanim oczekujesz wierszy Haas NGC: potwierdź, że ZIP-y UMC / ST-20Y zostały **rozpakowane** pod folderem daty/maszyny (skaner **ignoruje** `.zip`).
4. Zerknij na pasek statusu Indeksu (Obserwuj / przerwa / bezpieczeństwo) i ewentualną liczbę **brakujących źródeł** po wyszukiwaniu.

### Co tydzień (lub po intensywnym tygodniu kopii)

1. **Raporty → Jakość indeksu…** — przejdź MACHINE UNKNOWN, brak odbiorcy, konflikty kolorów.
2. Zerknij na **Historia skanów…** — dodane / zmienione / usunięte powinny wyglądać rozsądnie (skoki → sieć lub ścieżki).
3. Gdy UNKNOWN rośnie: popraw mapy/aliasy w **Mapowanie…**, potem jeden skan **pełny**.
4. Opcjonalnie wyczyść stare pliki w folderze **wydobycia** (pakietu bazy nie ruszaj).

### Po zmianach konfiguracji / YAML

| Zmiana | Następny krok |
|--------|---------------|
| Tylko nowe pliki / nowy podfolder pod istniejącym korzeniem | Przyrostowy (Obserwuj / bezpieczeństwo / ręcznie) |
| Mapa folderów maszyn lub aliasy maszyn dla **już zindeksowanych** ścieżek | Pełny reskan |
| Usunięte reguły kolorów funkcji (albo chcesz role od zera) | Pełny reskan |
| Dodane reguły kolorów / drzewa / O9, które nadal pasują | Przyrostowy zwykle wystarczy |
| Katalog odbiorców / przełącznik z nagłówka | Przyrostowy zwykle wystarczy (odbiorca na post-pass; z nagłówka tylko gdy nadal puste) |
| Przełączniki roli/maszyny z nagłówka lub nowe aliasy | Przyrostowy zwykle wystarczy przy **dodawaniu** (role się kumulują; maszyna tylko UNKNOWN → znana). **Pełny**, gdy wyłączono przełącznik lub usunięto aliasy i trzeba wyczyścić stare wartości z nagłówka |
| Nowy korzeń zielony/żółty | Dodaj korzeń → skan (przyrostowy OK do odkrycia) |
| Przeniesiony pakiet na inny PC / udział | Potwierdź skopiowanie całego folderu; **Przygotuj indeksator…** na PC nasłuchującym; remap ścieżek |

### Pakiet obok bazy (kopiuj cały folder)

Traktuj **folder bazy** jako jeden zestaw. Udostępniaj **cały folder**, nie sam sqlite.

| Plik | Po co |
|------|-------|
| `gcode_index.sqlite` | Wiersze programów (status, role, ścieżki, hashe) |
| `folder_colour_aliases.yaml` | **Obowiązkowy** dla prawdziwych kolorów Flagi na każdym kliencie |
| `folder_tree_map.yaml` | Nadpisania Mapuj drzewo; powody ścieżek w tipie Flagi |
| `aliases.local.yaml`, `machine_folders.yaml` | Nauka maszyn na następny skan |
| `odbiorcy.yaml` | Katalog odbiorców |
| `extra_scan_roots.yaml` | Korzenie zielone/żółte |
| `indexer_settings.yaml` | Wspólne domyślne skanu / obserwacji / przerwy / bezpieczeństwa (**nie** wymusza `can_index`) |

Opcjonalnie: `scan_history.json`, `ui_settings.yaml`, `views.yaml`, `gcode_index.xlsx`.

**Per PC (nie w pakiecie):** `gcode-index.ini` obok exe — `can_index`, ścieżki bezwzględne, mapowanie ścieżek, język, blokady hali.

### Czego nie robić

- **Nie** kopiuj samego `gcode_index.sqlite` na PC hali i nie oczekuj poprawnych kolorów Flagi.
- **Nie** wkładaj `can_index=yes` do współdzielonego pakietu ani nie promuj każdego PC do indeksatora.
- **Nie** włączaj Obserwuj na dwóch PC indeksatorów przeciw tej samej bazie.
- **Nie** oczekuj, że skaner otworzy Haas `.zip` — najpierw rozpakuj.
- **Nie** edytuj oryginałów kopii, żeby „naprawić” indeks; wydobycie zapisuje gdzie indziej; źródła pozostają tylko do odczytu.
- **Nie** zakładaj, że Przyrostowy przeassignuje maszyny po edycji map — użyj Pełnego.
- **Nie** usuwaj plików pomocniczych „żeby zwolnić dysk”; to psuje Flagę / naukę na następny skan. Czyść raczej **wydobycie**.
- **Nie** polegaj na rytuałach vacuum/compact — aplikacja i tak przepisuje sqlite przy każdym skanie.
- **Nie** zostawiaj pustej ścieżki wydobycia na współdzielonym folderze bazy, jeśli operatorzy zrzucają tam wiele extractów — użyj osobnego folderu wydobycia.

Usunięte/przeniesione źródła znikają przy **następnym** skanie; do tego czasu wiersz ma odznakę **brak źródła**.

## Blokada operatora

Komputery na hali: `settings_locked = yes` w ini **albo** pusty plik `operator.lock` / `can_index.lock` obok ini. Wtedy `can_index` jest wymuszane na **no**.

## Odświeżanie wyników (klienci po skanie przyrostowym)

Zaznacz **Odświeżaj wyniki**, aby **ponowić bieżące wyszukiwanie**, gdy zmieni się `gcode_index.sqlite` (mtime, domyślnie ~20 s). Przydatne na hali z bazą na **udziale sieciowym**, gdy indeksator robi Obserwuj / bezpieczeństwo przyrostowy: nowe wiersze pojawiają się bez czyszczenia filtrów i bez ponownego otwierania pliku. Zapis: `search_auto_refresh` / `search_auto_refresh_s` w ini. Bez tego operator klika Szukaj ponownie po skanie.

## Ustawienia instalacji

**Ustawienia wracają po restarcie:** `gcode-index.ini` obok exe pamięta foldery, zieleń/żółć, **`can_index`**, język, desktop, geometrię, mapowanie ścieżek, **ostatnie filtry** oraz widok Praca/Indeks. Obok bazy: `indexer_settings.yaml` — **wspólne domyślne** skanu / obserwacji / przerwy / bezpieczeństwa (pakiet sklepu; **nie** wymusza `can_index`). Indeksator zapisuje ten plik przy zmianie tych przełączników.

**Przygotuj indeksator…** (Narzędzia / Indeks): potwierdź ścieżkę kopii i wydobycia oraz mapowanie, zastosuj domyślne z pakietu, ustaw `can_index=yes`, opcjonalnie włącz obserwację. Klienci hali zostają na `can_index=no` (+ opcjonalnie `operator.lock`).  

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
