# Register jaskýň a geomorfologická vrstva

Tento dokument opisuje aktuálnu logiku registra jaskýň a cieľ ďalšieho kroku:
doplniť k jaskyniam spoľahlivé geomorfologické zaradenie Slovenska. Je určený
pre správcu dát, ktorý opravuje duplicitné jaskyne, pádové varianty názvov a
nejasné lokality.

## Základné pravidlo

Register jaskýň nesmie byť iba voľný textový index. Jedna položka registra má
predstavovať konkrétnu jaskyňu alebo konkrétnu pomenovanú lokalitu. Preto sa
pri spracovaní rozlišujú tri rôzne prípady:

- pádové alebo jazykové varianty toho istého názvu,
- rovnaký názov pre rôzne jaskyne v rôznych oblastiach,
- články, kde sa jaskyňa spomína iba okrajovo alebo ako súčasť širšieho textu.

Pádové a jazykové varianty sa zlučujú. Rovnaké názvy rôznych jaskýň sa nezlučujú;
rozdeľujú sa podľa lokality alebo geomorfologickej oblasti.

## Aktuálny stav

Register sa generuje zo súboru článkov a z kurátorovaného aliasového súboru.
Výstupom je JSON pre webový register a detailné stránky jaskýň s časovou osou.

Aktuálne funguje:

- zlučovanie ručných aliasov cez kanonický názov,
- základná inferencia jaskýň z názvu a anotácie článku,
- import oficiálneho registra jaskýň SMOPaJ s číslom jaskyne a geomorfologickou jednotkou,
- ochrana proti všeobecným slovám typu výskum, prieskum, ochrana alebo návštevnosť,
- deduplikácia rovnakých článkov v časovej osi,
- zobrazenie časopisu pri každom článku,
- rozdelenie vybraných nejednoznačných jaskýň podľa oblasti,
- vyhľadávanie v registri podľa názvu, aliasu a oblasti.

Príklad zlučovania aliasov:

```json
{
  "canonical": "Jasovská jaskyňa",
  "aliases": ["Jasovskej jaskyne", "Jasovská jeskyně"]
}
```

Príklad nejednoznačného názvu:

```text
Medvedia jaskyňa
```

Tento názov nemôže byť jedna položka pre celé Slovensko. V dátach sa vyskytuje
Medvedia jaskyňa v Slovenskom raji, v Jánskej doline, v Malej Fatre, v Čiernej
hore, v Poľsku a aj odvodené názvy ako Demänovská medvedia jaskyňa alebo
Vestenická Medvedia jaskyňa. Tieto položky musia zostať oddelené.

## Kedy zlučovať

Zlučovať sa má iba vtedy, keď ide o tú istú jaskyňu:

- pád názvu: `Jasovská jaskyňa` a `Jasovskej jaskyne`,
- český alebo starší pravopis: `Jasovská jeskyně`,
- drobná typografická odchýlka,
- rovnaká jaskyňa uvedená s dodatkom, ktorý nemení identitu.

Zlučovanie sa zapisuje do aliasového súboru. Cieľ je, aby web zobrazoval jednu
kanonickú kartu a pri nej zoznam známych aliasov.

## Kedy deliť

Deliť sa má vtedy, keď rovnaký alebo veľmi podobný názov pomenúva rôzne jaskyne:

- rovnaký názov v odlišnom pohorí alebo krasovej oblasti,
- všeobecný názov typu Medvedia, Líščia, Priepasťová, Javorová,
- názov bez oblasti, ak články jasne ukazujú viac lokalít,
- názov, ktorý sa v jednom článku viaže na Slovenský raj a v inom na Nízke Tatry.

V takom prípade sa k položke pridá oblasť. Na webe sa potom názov zobrazuje ako
samostatná karta s doplňujúcou oblasťou, napríklad:

```text
Medvedia jaskyňa
Slovenský raj / Stratenská hornatina
```

## Prečo nestačí voľný fulltext

Fulltext vie nájsť všetky výskyty slova, ale nevie sám rozhodnúť, či ide o
hlavnú lokalitu článku. Ak sa článok o jednej jaskyni zmieni o inej jaskyni iba
v porovnaní, voľný fulltext by ju nesprávne pridal do časovej osi.

Pre register jaskýň preto platí prísnejšie pravidlo:

- článok patrí k jaskyni, ak názov alebo anotácia priamo obsahuje danú jaskyňu,
- pri kurátorovaných záznamoch môže byť článok označený ako overený,
- voľné slová z oblasti, pohoria alebo okresu sa nepovažujú automaticky za
  jaskyňu.

## Geomorfologické členenie Slovenska

Geomorfologická vrstva má pridať štandardizované regionálne tagy. Hodnota tejto
vrstvy je vyššia než voľný text typu "oblasť", pretože umožní:

- rozlíšiť rovnaké názvy jaskýň podľa geomorfologického celku,
- filtrovať články podľa oblastí ako Slovenský raj, Nízke Tatry, Slovenský kras
  alebo Malá Fatra,
- vytvoriť časové osi nielen pre jaskyne, ale aj pre krasové celky,
- presnejšie pripravovať AI rešeršné balíky,
- znížiť počet chybných zlúčení v registri.

Plánovaný minimálny model:

```json
{
  "local_area": "Stratenská hornatina",
  "geomorph_unit": "Slovenský raj",
  "geomorph_subprovince": "Vnútorné Západné Karpaty",
  "confidence": "curated",
  "source": "curated-from-article-context"
}
```

Prvá implementácia používa kurátorovaný JSON súbor s dvoma typmi pravidiel:

- `areas` mapuje existujúce disambiguation oblasti z registra, napríklad
  `Jánska dolina / Nízke Tatry`,
- `caves` mapuje konkrétne kanonické názvy jaskýň, napríklad `Domica` alebo
  `Jasovská jaskyňa`.

Pri generovaní registra má prednosť pravidlo podľa oblasti. Ak jaskyňa nemá
disambiguation oblasť, použije sa pravidlo podľa kanonického názvu. Výsledok sa
uloží do poľa `region` v dátach registra a web ho zobrazuje ako geomorfologický
tag.

Okrem kurátorovaného súboru sa používa oficiálny SMOPaJ register. V repozitári
sú uložené textové extrakty z týchto PDF zdrojov:

- `data/source_text/smopaj_zoznam_jaskyn_2017.txt` - Zoznam jaskýň k 31.12.2017 podľa geomorfologických jednotiek,
- `data/source_text/smopaj_register_jaskyn.txt` - abecedný register jaskýň s číslom jaskyne,
- `data/source_text/smopaj_geomorfologicke_celky.txt` - prehľad podľa geomorfologických celkov.

Z nich sa generuje `data/smopaj_cave_register_2017.json`:

```bash
python3 scripts/import_smopaj_cave_register.py
python3 scripts/export_smopaj_public_register.py
python3 scripts/build_cave_index.py
```

Dôležité rozlíšenie: v zdrojovom zozname sa vyskytuje poradové `Číslo jaskyne`
aj interné `r. č.`. Mená z abecedného registra sa párujú podľa `Číslo jaskyne`,
nie podľa `r. č.`, inak vznikajú falošné aliasy.

Oficiálny register sa používa len pri jednoznačnej zhode názvu alebo aliasu.
Ak rovnaký názov mapuje na viac čísiel jaskyne, napríklad `Medvedia jaskyňa`,
skript mu automaticky nepriradí jedno oficiálne číslo. Také prípady sa ďalej
delia podľa oblasti alebo riešia kurátorsky.

Verejná časť webu používa samostatný zmenšený index
`web/public/data/smopaj_cave_register_2017_search.json`. Generuje ho
`scripts/export_smopaj_public_register.py` z rovnakého oficiálneho JSONu a
obsahuje všetkých 7329 položiek so základnými poliami: číslo jaskyne, r. č.,
oficiálny názov, aliasy a geomorfologické členenie. Formulár
`/nahlasit-chybu/` tento index načíta iba pri type opravy
`Číslo jaskyne / SMOPaJ`, aby používateľ mohol vyhľadať správnu položku a
navrhnúť číslo aj pre zatiaľ nespárovanú kartu.

Verejný návrh nikdy nemení dáta priamo. Backend vytvorí GitHub issue s typom
`smopaj_number`; správca po kontrole doplní potvrdenú väzbu do
`data/smopaj_cave_match_overrides.json` a spustí `scripts/build_cave_index.py`.

Kurátorované oficiálne zhody sú v `data/smopaj_cave_match_overrides.json`.
Sú určené pre prípady, kde je identita overená z názvu, anotácie, oblasti alebo
oficiálneho zoznamu, ale automatická zhoda by bola príliš riziková. Položka môže
byť viazaná:

- na `cave_slug`, napríklad pádový variant `drienovskej-jaskyne`,
- na `cave_name`, ak sa má párovať podľa názvu,
- na kombináciu `cave_name` + `cave_area`, ak rovnaký názov označuje viac jaskýň.

Každé `cave_number` z override súboru sa pri generovaní validuje proti
`data/smopaj_cave_register_2017.json`. Neexistujúce číslo generovanie zastaví.
Tým sa dá použiť AI alebo manuálne párovanie bez toho, aby sa do webu ticho
dostali neplatné čísla.

AI-asistované zhody sú oddelené v `data/smopaj_cave_ai_matches.json`.
Generuje ich skript `scripts/ai_match_smopaj_caves.py`. Tento súbor sa pri
generovaní registra pripája až za ručne kurátorované override, takže manuálne
potvrdené zhody majú vždy prednosť. AI výstup obsahuje aj `deferred` položky,
kde model alebo kontext nevedel bezpečne vybrať jednu jaskyňu.

Odporúčaný postup pre ďalšie dávky:

```bash
python3 scripts/ai_match_smopaj_caves.py --backend heuristic --limit 100 --dry-run
python3 scripts/ai_match_smopaj_caves.py --backend codex --codex-model gpt-5.5 --fulltext-context --resume --min-confidence 0.86 --output data/smopaj_cave_ai_matches.json --slug <slug>
python3 scripts/build_cave_index.py
python3 scripts/export_smopaj_public_register.py
```

Heuristický výstup slúži iba na predvýber. Do produkčného súboru sa zapisujú
iba vysoko isté Codex/GPT zhody alebo ručne potvrdené override. Generické
titulkové fragmenty typu `Nová jaskyňa`, `12 km jaskyne`,
`Analýza nálezov zo ...` a podobné nenázvy sa filtrujú už pri generovaní
`web/src/data/caves.json`, aby sa nedostali do registra ako samostatné lokality.

Najproduktívnejší workflow je zoradiť nezaradené karty podľa kandidátneho skóre
voči SMOPaJ zoznamu a cez Codex overovať iba silné názvové/pádové varianty.
Chronologické spracovanie celej fronty rýchlo narazí na zahraničné, skupinové
alebo všeobecné položky, ktoré treba skôr odkladať ako párovať.

Ak schema režim Codex CLI padá na app-server alebo sandbox inicializácii, dá sa
použiť úzky recovery helper pre konkrétne slugs:

```bash
python3 scripts/confirm_smopaj_matches_direct.py --slug <slug>
python3 scripts/build_cave_index.py
```

Helper používa rovnaký kandidátny shortlist, Codex/GPT-5.5 rozhodnutie a
validáciu `cave_number` proti SMOPaJ kandidátom. Nie je určený na slepé
spracovanie celého registra, ale na malé overené dávky, kde treba obísť
nestabilné dlhé volanie.

Lokálny model `gemma4:e2b-it-qat` je použiteľný na hrubý shortlist, ale pri
testovaní vracal protirečivé rozhodnutia pre kurátorské párovanie. Na zápis do
produkčného registra sa preto používa iba Codex/GPT-5.5 alebo ručné potvrdenie.
Pri dlhých dávkach používaj `--resume`; skript po každej spracovanej karte
zapíše checkpoint do výstupného JSON súboru.

Kurátorské pravidlo Domica: `Domica`, `Baradla`, `Baradla Cave`,
`Jaskyňa Baradla`, `Jaskynný systém Domica-Baradla` a bibliografická karta
`Domica - Kľúčová dierka` sa v časovej osi zlučujú pod oficiálnu SMOPaJ jaskyňu
`Domica` (`3483.1`). `Kľúčová dierka` je v tomto kontexte lokalita výskumu alebo
objavu v Domici, nie samostatná strážovská jaskyňa s rovnakým názvom.

Na začiatku netreba pokryť celé Slovensko ručne. Praktickejšie je dopĺňať
kurátorované mapovanie pre lokality, ktoré už spôsobujú chyby v registri:

- Medvedia jaskyňa,
- Demänovské jaskyne a Demänovská dolina,
- Stratenská jaskyňa, Psie diery a Slovenský raj,
- Jasovská jaskyňa a Slovenský kras,
- Domica a Slovenský kras,
- Belianska dolina a Veľká Fatra,
- Malá Fatra a Vrátna dolina.

## Pravidlo dôveryhodnosti

Geomorfologické zaradenie má mať pôvod. Odporúčané úrovne:

- `curated` - ručne overené správcom,
- `article-context` - odvodené z názvu alebo anotácie článku,
- `ai-suggested` - navrhnuté AI a čaká na kontrolu,
- `unknown` - oblasť nie je známa.

Do produkčného registra sa má ako rozhodujúce používať iba `curated` alebo
jasné `article-context`. AI návrhy sú vhodné na pracovný zoznam, nie na slepé
automatické zlučovanie.

## Odporúčaný pracovný postup

1. Nájsť podozrivý názov v registri.
2. Otvoriť detail jaskyne a skontrolovať časovú os.
3. Pri každom nejasnom článku overiť názov, anotáciu a PDF stránku.
4. Rozhodnúť, či ide o alias tej istej jaskyne alebo o inú jaskyňu.
5. Jednoduchý alias pridať do `data/cave_aliases.json`.
6. Overenú oficiálnu zhodu, ktorú automatika nevie bezpečne vybrať, pridať do
   `data/smopaj_cave_match_overrides.json`.
7. Nejednoznačnú jaskyňu zaradiť do oblasti alebo geomorfologického celku.
8. Spustiť generovanie registra.
9. Skontrolovať webový register a detailnú časovú os.
10. Pridať test pre nový problematický prípad.

## Dôležitá zásada

Automatika má pomáhať hľadať podozrivé prípady, nie sama rozhodovať o identite
jaskyne. Pri speleologických názvoch je veľa lokálnych opakovaní a pádových
tvarov. Bez oblasti môže byť správne riešenie opačné: raz treba názvy zlúčiť,
inokedy ich treba striktne rozdeliť.
