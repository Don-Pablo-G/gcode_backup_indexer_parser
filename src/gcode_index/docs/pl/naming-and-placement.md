# Nazwy i rozmieszczenie — dobre praktyki

**Dla kogo:** osoby na PC indeksatora, które układają drzewo kopii, katalogi zielone/żółte, aliasy i nagłówki tak, żeby Flaga, maszyny, role, odbiorcy, Obserwuj i listy uczenia działały dobrze.  
**Zdolność:** większość ustawień jest na PC indeksatora (`can_index=yes`). Na hali wystarczy **pakiet obok bazy**.  
**Odzwierciedla zachowanie do 0.2.120** (na bazie 0.2.119).

W GUI: **Pomoc → Nazwy i rozmieszczenie…** otwiera ten przewodnik. Te same tematy są też rozdziałem w **instrukcji indeksatora**.

---

## 1. Drzewo kopii vs zielone vs żółte

| Miejsce | Znaczenie | Flaga / status |
|---------|-----------|----------------|
| **Główny folder kopii** | Drzewo kopii CNC (zrzuty Haas, foldery dat, maszyn, …) | 🟢 **Z maszyny** — podpowiedź: **z backupu** |
| **Zielone dodatkowe** (zaufane / „z maszyny”) | Foldery „catch” na luźne `.nc`, które mają liczyć się jak kopia z maszyny przed pełnym backupem | 🟢 ten sam zielony krążek — podpowiedź: **zaufany folder** |
| **Żółte dodatkowe** | Inne drzewa (robocze, WIP, nieznane pochodzenie) | 🟡 **Status nieznany** |

**Praktycznie:**

- Prawdziwą kopię z maszyn trzymaj pod **Kopią**. To oznacza „z maszyny” dla operatorów.
- **Zielone** tylko dla folderów, którym ufasz jako kopie/catch z maszyny. Nie maluj na zielono każdego udziału.
- **Żółte** na wszystko, co ma być wyszukiwalne, ale **nie** ma wyglądać jak potwierdzony przebieg na maszynie.
- Zagnieżdżone korzenie: **najgłębszy** skonfigurowany korzeń zawierający plik jest właścicielem (kolor dziecka wygrywa; bez podwójnych wierszy).
- **Aliasy nazw folderów nigdy nie zmieniają** zielonego/żółtego — tylko pochodzenie (`scan_root`). Role (osobiste, prototyp, programy systemowe, …) to osobne krążki Flagi.

---

## 2. Nazwy folderów — granice tokenów

Aliasy dopasowują **tokeny**, nie zlepek prefiksów. Tokeny dzieli **spacja**, `_` i `-` (oraz podobne separatoy).

| Folder / komentarz | Alias `pat` | Trafienie? |
|--------------------|-------------|------------|
| `pat` | osobiste | Tak |
| `pat_backup` / `pat-backup` / `foo pat bar` | osobiste | Tak (token `pat`) |
| `pattyn` | osobiste | **Nie** (jeden token; bez „rozlewania” fuzzy) |
| `VF2S` | `VF2` | Tak (fuzzy **wewnątrz** jednego tokenu, krótki resztkowy) |

**Rób:**

- Nazywaj foldery tak, by pisownia maszyny / roli / odbiorcy była **osobnym** tokenem: `2026-03-15_VF2S_backup`, `Acme_Sp_parts`, `PROTO OP1`.
- Preferuj aliasy co najmniej **3** znaki; unikaj 1–2 liter, które kolidują w całej firmie.
- Po zmianie aliasów **przeindeksuj** (pełny skan, gdy stare wiersze mają dostać nowe przypisania).

**Nie rób:**

- Nie licz na stare fuzzy „prefiks całego zlepku” (`pat` → `pattyn`). To rozlewanie zostało usunięte.
- Nie używaj tego samego krótkiego aliasu dla dwóch maszyn albo maszyny i odbiorcy.
- Nie oczekuj, że **etykiety** katalogu (nazwy wyświetlane) trafią w ścieżki — igłami są tylko **aliasy**.

---

## 3. Uczenie ról, maszyn i odbiorców

Uczysz raz; te same igły działają na **nazwy folderów** i na komentarze `(…)` w **linii O**.

| Gdzie | Co zapisuje | Najlepsze do |
|-------|-------------|--------------|
| **Nazwy folderów…** | Lista częstości → utwórz lub podepnij alias | Powtarzające się nazwy w drzewie |
| **Mapuj drzewo…** | Maszyna / wiele ról / odbiorca / wyklucz dla konkretnej ścieżki | Jedna dziwna ścieżka nadpisująca aliasy nazw |
| **Maszyny / Role / Odbiorcy i aliasy…** | Utrzymanie katalogów | Etykiety, barwy, ręczne dopisywanie pisowni |
| **Nieprzypisane tokeny nagłówka…** (raport skanu) | Te same sidecary aliasów z tokenów linii O | Częste pisownie w nagłówku jeszcze bez wiązania |

**Pierwszeństwo (w skrócie):**

1. Reguły ścieżki w mapie drzewa (najdłuższy prefiks) zastępują unię ról z nazw dla tej ścieżki.
2. Aliasy nazw kumulują role; maszyna / odbiorca uzupełniają, gdy nadal puste / UNKNOWN.
3. Aliasy z linii O uzupełniają luki (maszyna tylko przy UNKNOWN; odbiorca tylko gdy pusty; role się kumulują).
4. Opcja **O9000–O9099 → programy systemowe** dodaje tę rolę po numerze programu.

Prawy klik na folder w **Mapuj drzewo** → *Alias nazwy „…” wszędzie* uczy alias **globalny po nazwie** (nie status).

---

## 4. Komentarze w linii O (auto-dopasowanie vs lista uczenia)

**Auto-dopasowanie** (maszyna / rola / odbiorca z nagłówka) patrzy tylko na komentarze w nawiasach **w tej samej linii co numer programu**:

```text
O9001 (VF2S) (PROTO) (Pawel)
O03232 (P-00253232 VA OP1/OP2)
```

Komentarze w kolejnych liniach lub głębiej w treści są **ignorowane** przy auto-przypisaniu.

**Lista uczenia** (**Nieprzypisane tokeny nagłówka…**):

- Domyślnie to samo okno linii O (**Głębokość skanu nagłówka** = **1** w opcjach skanu).
- Głębokość poszerza **tylko** listę uczenia (1–20; stop przed następnym `%`). **Nie** poszerza auto-dopasowania.
- Wyklucza numery programów oraz tokeny z **więcej niż 4 cyframi** (szum rysunkowy / nr części).
- Po przypisaniu aliasów **pełny** reskan odświeża listę — nauczone tokeny znikają.

**Rób:** wstawiaj tagi maszyny / roli / odbiorcy w `(…)` w linii **O#####**.  
**Nie licz** na komentarze poza linią O przy Fladze / maszynie / odbiorcy.

---

## 5. Numery programów `O#####` i programy systemowe

- Zwykłe programy części mają numer w linii `O#####` (dopełnienie zerami bywa różne; szukanie traktuje `O03232` / `3232` tak samo).
- Opcjonalny przełącznik skanu **O9 → programy systemowe** (domyślnie **wł.**): numery **O9000–O9099** dostają rolę **`system_programs`** (pomarańcz) automatycznie. Poza tym zakresem (np. O9100) **nie ma** auto-tagu — użyj aliasu folderu lub nagłówka, jeśli nadal chcesz rolę.
- Tag O9 **nie zmienia** statusu zielony/żółty, maszyny ani odbiorcy.

---

## 6. Co obserwuje Obserwuj (i bezpieczeństwo)

Przy włączonym **Obserwuj foldery** (tylko indeksator):

| Ustawienie | Domyślnie | Skutek |
|------------|-----------|--------|
| **Wyklucz folder kopii** | **Wł.** | Live listen / stamp-poll obejmuje **tylko zielone/żółte** — nie główne drzewo kopii |
| Min. przerwa między skanami | 45 s | Scalanie serii zrzutów |
| Skan bezpieczeństwa | Wył. | Opcjonalny wymuszony przyrostowy co interwał; opcjonalnie **o HH:MM** (zegar lokalny) |

**Ważne:**

- Ręczny **Uruchom skan**, przyrostowy z Obserwuj i **bezpieczeństwo** nadal indeksują **kopię + dodatkowe** normalnym pipeline. Wykluczenie kopii dotyczy tylko **żywego** watch/poll korzenia kopii.
- Preferuj zielone/żółte catch na near-live zrzuty; zostaw kopię na harmonogram / ręczny / bezpieczeństwo, gdy drzewo jest ogromne lub UNC kapryśne.
- Jeden PC trzyma `gcode_index.lock`. Tło Obserwuj / przerwa / bezpieczeństwo **nie** skacze Praca → Indeks; tylko ręczny Uruchom skan.

---

## 7. Pakiet klienta — sidecary obok bazy

Kopiuj **cały folder bazy** na PC hali (albo wskaż udział). Obok `gcode_index.sqlite`:

| Plik | Po co |
|------|-------|
| `folder_colour_aliases.yaml` | **Obowiązkowy** dla prawdziwych kolorów Flagi / ról nadpisujących |
| `folder_tree_map.yaml` | Powody ścieżki w podpowiedzi Flagi; tagi ścieżki |
| `aliases.local.yaml`, `machine_folders.yaml` | Uczenie maszyn na kolejny skan |
| `odbiorcy.yaml` | Katalog odbiorców |
| `extra_scan_roots.yaml` | Korzenie zielone/żółte |
| `indexer_settings.yaml` | Wspólne domyślne skan/obserwacja (**nigdy** `can_index`) |

**Per PC (nie w pakiecie):** `gcode-index.ini` obok exe — `can_index`, ścieżki bezwzględne, **mapowanie ścieżek** (UI w **Folderach** / **Zmień…**, nie w Mapowaniu), język, blokady.

Otwarcie samego `.sqlite` bez `folder_colour_aliases.yaml` daje kolory seed i ostrzeżenie.

---

## 8. Checklista rób / nie rób

**Rób**

- Trzymaj jeden jasny korzeń **kopii**; **zielone** oszczędnie na zaufane catch; **żółte** na resztę do wyszukiwania.
- Dziel sensowne nazwy spacją / `_` / `-`, żeby aliasy były całymi tokenami.
- Ucz powtarzające się pisownie w **Nazwy folderów…**; jednorazowe ścieżki w **Mapuj drzewo…**.
- Wstawiaj tagi do uczenia w `(…)` w **linii numeru O**.
- Trzymaj **pełny pakiet** obok bazy na każdym kliencie.
- Zostaw **Wyklucz folder kopii** włączone, chyba że naprawdę potrzebujesz żywego Obserwuj na całym drzewie kopii.
- Używaj bezpieczeństwa **HH:MM**, gdy chcesz doganiania „co noc o północy”.

**Nie rób**

- Nie oczekuj, że krótki alias wejdzie *w środku* dłuższego słowa (`pat` ≠ `pattyn`).
- Nie wkładaj numerów rysunków (długie ciągi cyfr) do aliasów uczenia — lista uczenia i tak chowa tokeny z **>4 cyframi**.
- Nie licz na komentarze **poniżej** linii O przy auto maszynie / roli / odbiorcy.
- Nie myl kolorów **ról** ze statusem zielony/żółty — role nigdy nie przepisują pochodzenia.
- Nie wysyłaj na halę samego pliku sqlite.
- Nie uruchamiaj Obserwuj na dwóch PC indeksatora przeciw tej samej bazie.
- Nie wkładaj `can_index=yes` do pakietu współdzielonego.

---

## Powiązana pomoc

- **Instrukcja indeksatora** — foldery, Mapowanie, Obserwuj, higiena bazy (pełny detal).
- **Instrukcja operatora** — odczyt / wydobycie; higiena pakietu na hali.
