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

Na začiatku netreba pokryť celé Slovensko naraz. Praktickejšie je pridať
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
5. Alias pridať do aliasového súboru.
6. Nejednoznačnú jaskyňu zaradiť do oblasti alebo geomorfologického celku.
7. Spustiť generovanie registra.
8. Skontrolovať webový register a detailnú časovú os.
9. Pridať test pre nový problematický prípad.

## Dôležitá zásada

Automatika má pomáhať hľadať podozrivé prípady, nie sama rozhodovať o identite
jaskyne. Pri speleologických názvoch je veľa lokálnych opakovaní a pádových
tvarov. Bez oblasti môže byť správne riešenie opačné: raz treba názvy zlúčiť,
inokedy ich treba striktne rozdeliť.
