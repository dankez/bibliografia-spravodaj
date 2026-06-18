# Spravodaj SSS Bibliografia

Verzia 1.0

Digitálny bibliografický a research portál pre časopis Spravodaj Slovenskej speleologickej spoločnosti. Cieľom projektu nie je iba zobraziť PDF súbory, ale vytvoriť použiteľnú znalostnú vrstvu nad článkami: bibliografiu, fulltext, citácie, mapové/plánové odkazy, exporty a podklady pre neskoršiu tvorbu súhrnných AI článkov o jaskyniach, oblastiach a histórii objavovania.

## Pre koho je projekt

Projekt je určený pre:

- čitateľov Spravodaja SSS, ktorí chcú rýchlo nájsť článok, autora, jaskyňu alebo tému,
- správcov bibliografie, ktorí potrebujú overiteľný export v štýle pôvodnej Lalkovičovej bibliografie,
- autorov odborných a sumarizačných článkov, ktorí potrebujú pracovať s celou históriou textov, citácií a PDF strán,
- vývojára alebo správcu portálu, ktorý potrebuje obnoviť dáta, spustiť web a rozumieť pravidlám spracovania.

Po prečítaní tohto README by mal správca vedieť spustiť web, obnoviť exporty, rebuildnúť research databázu, pochopiť mapovú detekciu a správne pracovať s odkazmi na PDF strany.

## Stav verzie 1.0

Aktuálny dataset obsahuje:

- 3802 bibliografických záznamov,
- roky 1970 až 2026,
- 3665 článkov s online PDF odkazom,
- 3645 článkov s extrahovaným fulltextom,
- 10594 research chunkov,
- 1339 rozpoznaných entít,
- 449 chronologických research timeline výstupov,
- 164 prísne potvrdených článkov s mapou alebo plánom naprieč archívom.

Research manifest uvádza približne 25,8 milióna znakov a 3,95 milióna slov v spracovanom fulltexte. SQLite research databáza sa generuje lokálne a nie je commitovaná, pretože má viac ako 100 MB.

## Čo portál poskytuje používateľovi

Webová aplikácia je statický Astro portál s lokálnym vyhľadávaním v prehliadači. Používateľ dostáva:

- rýchle vyhľadávanie cez MiniSearch v názve, autoroch, anotácii, roku, čísle, tagoch a ďalších bibliografických poliach,
- voliteľné hľadanie vo fulltexte,
- filtre podľa roka, čísla a článkov s mapou/plánom,
- detailnú stránku každého článku,
- permanentnú stránku článku v tvare `/clanky/<id>/`,
- tlačidlo na otvorenie PDF v novej karte bez automatického načítavania PDF vieweru,
- PDF odkaz otvorený na správnej fyzickej strane článku,
- citácie ISO 690, APA a MLA,
- JSON-LD typ ScholarlyArticle,
- taxonomické tagy, jaskyne, skupiny a ďalšie entity,
- obálku čísla, ak existuje odvodený obrázok pri PDF na webe SSS,
- odkazy na Danko exporty vo formáte HTML, Markdown a PDF,
- svetlú academic tému a tmavý režim ladený do sivej, sivohnedej speleo palety.

Mapa ako samostatná webová funkcia bola vo verzii 1 odstránená. Mapy a plány sa detegujú ako vlastnosť článkov, ale web nezobrazuje mapový podklad.

## Hlavná architektúra

Projekt má štyri vrstvy:

1. Bibliografická vrstva

   Obsahuje články, autorov, názvy, roky, čísla, strany, anotácie, PDF URL, tagy, jaskyne, skupiny a doplnené metadáta. Je to základ portálu aj exportov.

2. Fulltextová vrstva

   PDF súbory sa nespracúvajú cez platené AI tokeny. Najprv sa lokálne sťahujú alebo cacheujú a text sa extrahuje cez nástroje typu `pdftotext`. Výstupom je článkový fulltext vhodný na vyhľadávanie a ďalšie spracovanie.

3. Research znalostná vrstva

   Fulltext sa čistí, rozdeľuje na retrieval chunky, prepája s citáciami, entitami, PDF stranami a timeline výstupmi. Táto vrstva je určená na neskoršiu tvorbu sumarizačných AI článkov, napríklad "história objavovania konkrétnej jaskyne".

4. Web a exportná vrstva

   Astro web generuje statický portál. Exportér vyrába čitateľné bibliografické exporty v Danko formáte: TXT, Markdown, HTML a PDF.

## Dátový model článku

Typický článok nesie tieto informácie:

- interné ID,
- autori,
- názov,
- rok,
- ročník,
- číslo,
- tlačené strany v časopise,
- online PDF URL,
- vypočítanú alebo uloženú PDF stranu,
- anotáciu,
- tagy,
- jaskyne,
- skupiny,
- Wikidata alebo iné entity, ak sú známe,
- príznaky ako fotografia, tabuľka, bibliografia, merania, súradnice, rez alebo mapa/plán,
- pre mapy/plány aj fyzické PDF strany, na ktorých sa nachádzajú.

Dôležité je rozlišovať tlačenú stranu článku a fyzickú stranu PDF súboru. Tlačená strana je bibliografický údaj. Fyzická PDF strana je technický údaj pre otvorenie dokumentu v prehliadači.

## Pravidlo PDF strán

PDF čísla často obsahujú obálku, ktorá nie je súčasťou tlačeného číslovania časopisu. Preto nestačí použiť bibliografickú stranu priamo ako `#page`.

Vo verzii 1 platí:

- bibliografické pole `pages` zostáva tlačené číslovanie časopisu,
- `pdf_page_start` a začiatok z poľa `pages` sa pri článkových odkazoch berú ako tlačená strana,
- web, exportér a research citation helper pridávajú ku každému článkovému PDF odkazu globálny offset `+2`,
- napríklad tlačená strana 57 sa linkuje ako PDF fyzická strana 59,
- `map_plan_pages` sa berú ako fyzické PDF strany z detekcie a neposúvajú sa druhýkrát.

Toto pravidlo je zásadné pre všetky ročníky, nielen pre nové čísla. Podrobnejší runbook pre kontrolu a údržbu je v [pravidlách PDF odkazov](docs/PDF_PAGE_LINKS.md).

## Fulltextová pipeline

Fulltextová pipeline je navrhnutá tak, aby šetrila platené AI tokeny.

Základný postup:

1. z online PDF URL sa zistí príslušné číslo časopisu,
2. PDF sa lokálne cacheuje,
3. text sa extrahuje cez lokálne nástroje,
4. článok sa oreže podľa rozsahu strán a susedných titulov,
5. vznikne článkový fulltextový JSONL,
6. research builder vytvorí SQLite FTS databázu, JSONL chunky, entity a timeline výstupy.

AI sa používa iba tam, kde má pridanú hodnotu: štruktúrované dopĺňanie problematických metadát, voliteľné obohatenie znalostí a potvrdenie mapových/plánových objektov po lokálnom prefiltri.

## Research databáza

Research databáza je offline pracovná databáza pre budúce AI články a sumarizácie. Obsahuje:

- články,
- fulltextové chunky,
- FTS index,
- citácie,
- entity,
- väzby článok-entita,
- timeline výstupy,
- PDF URL s presnými stranami,
- JSON-LD údaje,
- informácie o vizuálnych prvkoch.

SQLite databáza sa neukladá do GitHubu, pretože je veľká a rebuildovateľná. Prenosné výstupy ako JSONL chunky, timeline JSON a manifest môžu byť súčasťou repozitára.

Typické použitie:

```bash
python3 scripts/build_research_knowledge_db.py --force
python3 scripts/build_research_knowledge_db.py --query-only --query "Demänovské jaskyne" --top 10
```

## Detekcia máp a plánov

Detekcia máp a plánov je vo verzii 1 prísna. Cieľ je radšej zachytiť menej kvalitných nálezov ako zamiešať fotografie, logá alebo bežné ilustrácie.

Pipeline kombinuje:

- ignorovanie prvých dvoch a posledných štyroch strán čísla, pretože ide typicky o obálku a obálkové časti,
- lokálny prefilter obrazových objektov v PDF,
- analýzu caption textov pod objektmi,
- kľúčové slová ako mapa, mapka, plán, pôdorys, profil, rez, prierez, náčrt, meral, mapoval, kreslil, zameral,
- OCR pre objekty bez caption textu,
- vizuálne heuristiky pre mapové objekty: svetlé/biele dominantné pozadie, tmavé línie, textové značky, dvojfarebnosť,
- ochranu proti čiernobielym fotografiám,
- voliteľné potvrdenie lokálnym vision modelom v Ollama.

Testovaná a použitá lokálna AI vrstva je `minicpm-v4.6`. Používa sa až po prefiltri, nie na slepé spracovanie všetkých strán.

Pre manuálny ground truth test čísla 2026/1 boli mapy overené na fyzických PDF stranách 17, 59, 64 a 91. Používateľská kontrola potvrdila, že kliknuté odkazy v aktuálnom testovacom rozsahu viedli na články s mapou jaskyne.

## Exporty bibliografie

Exportér vytvára Danko formát, teda modernizovaný bibliografický výstup podobný pôvodnej bibliografii do roku 2009, ale s online funkcionalitou.

Exporty obsahujú:

- obsah,
- zoznam článkov,
- menný register,
- lokalitný register,
- vecný register,
- súpis plánov jaskýň,
- názvový register jaskýň,
- online PDF odkazy schované pod ikonou alebo krátkym labelom,
- zvýraznenie ročníka a čísla,
- čitateľnejšie rozlíšenie názvu, autora a strán,
- biele pozadie vhodné pre tlač.

Typický príkaz:

```bash
python3 scripts/export_lalkovic_format.py --basename spravodaj_sss_danko --pdf
```

Výstupy:

- TXT pre jednoduchú kontrolu,
- Markdown pre textové a Git použitie,
- HTML pre prehliadač,
- PDF pre tlač a zdieľanie.

## Webová aplikácia

Web je postavený na Astro, Tailwind/Vite integrácii a MiniSearch. Je statický, takže nepotrebuje serverovú databázu v produkcii.

Základné príkazy:

```bash
cd web
npm install
npm run dev
npm run build
```

Počas vývoja beží lokálny server štandardne na adrese:

```text
http://localhost:4321/
```

Produkčný build vytvorí statický výstup do ignorovaného build adresára. Tento výstup sa dá nasadiť na statický hosting.

## Lokálne závislosti

Odporúčané prostredie:

- Python 3.11 alebo novší,
- Node.js 22.12 alebo novší,
- npm,
- Astro závislosti z webového balíka,
- Poppler nástroje, hlavne `pdftotext` a podľa potreby `pdfimages`,
- Tesseract OCR pre slovenský a český text pri OCR detekcii,
- wkhtmltopdf pre PDF export bibliografie,
- Ollama iba pre lokálnu vision validáciu máp/plánov,
- model `minicpm-v4.6` pre aktuálnu lokálnu vision validáciu.

Bez Ollamy je stále možné robiť bibliografiu, fulltext, exporty aj web. Vision validácia je voliteľná časť mapovej pipeline.

## Typický pracovný postup správcu

1. Aktualizovať alebo doplniť PDF URL mapu zo SSS webu.
2. Doplniť nové články z PDF obsahu alebo z bibliografického zdroja.
3. Opraviť problematické metadáta: rok, číslo, názov, autori, strany.
4. Spustiť fulltextovú extrakciu.
5. Rebuildnúť research databázu.
6. Pre nové čísla spustiť prísnu detekciu máp/plánov.
7. Aplikovať potvrdené mapové nálezy do článkových JSON dát.
8. Regenerovať Danko exporty.
9. Skopírovať alebo publikovať exporty do verejnej časti webu.
10. Spustiť web build.
11. Overiť konkrétne PDF odkazy na problematických článkoch.
12. Commitnúť a pushnúť verziu.

## Testovanie a overenie

Python skripty majú testy v pytest štýle.

```bash
python3 -m pytest tests
```

Web build:

```bash
cd web
npm run build
```

Odporúčaná manuálna kontrola po dátovej zmene:

- vyhľadať článok z najnovšieho čísla,
- otvoriť PDF cez tlačidlo v detaile,
- overiť, že fyzická PDF strana sedí s tlačenou stranou v päte časopisu,
- skontrolovať aspoň jeden exportovaný Markdown/HTML odkaz,
- pri mapových článkoch overiť, že ide o mapu/plán, nie fotografiu.

## GitHub a bezpečnostná politika repozitára

Do GitHubu patria:

- zdrojové skripty,
- webová aplikácia,
- malé a stredné JSON/JSONL výstupy potrebné na reprodukovateľnosť,
- verejné exporty,
- dokumentácia,
- testy.

Do GitHubu nepatria:

- tokeny a `.env` súbory,
- GitHub tokeny,
- node_modules,
- build výstupy,
- lokálna PDF cache,
- renderované stránky PDF pre AI mapovú detekciu,
- veľká SQLite research databáza,
- dočasné alebo predchádzajúce fulltextové zálohy.

Tieto súbory sú ignorované v `.gitignore`. Ak sa pridá nový lokálny artefakt alebo token, musí sa najprv doplniť ignore pravidlo a až potom robiť `git add`.

## Čo znamená verzia 1.0

Verzia 1.0 znamená prvý ucelený stav projektu:

- bibliografické dáta sú zjednotené do jedného datasetu,
- web používa academic tému ako default,
- PDF sa neotvára automaticky, iba cez tlačidlo,
- permanentné stránky článkov majú správnu URL schému,
- exporty sú v Danko formáte,
- fulltextová research vrstva existuje,
- mapy/plány sa detegujú prísnou lokálnou pipeline,
- všetky článkové PDF odkazy používajú správny fyzický offset strán,
- projekt je pripravený na ďalšie rozširovanie o AI sumarizačné články.

## Ďalší rozvoj

Najbližšie vhodné smerovanie:

- priebežne manuálne auditovať potvrdené mapy a plány v starších ročníkoch,
- doplniť viac AI znalostných obohatení fulltextu cez lacnejší lokálny alebo dávkový režim,
- vytvoriť samostatnú funkciu na generovanie tematických článkov z research databázy,
- doplniť redakčný workflow pre komunitné errata,
- pridať export jednej jaskyne alebo jednej témy ako podklad pre odborný článok.
