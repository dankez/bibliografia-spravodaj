# Spravodaj SSS Bibliografia

Verzia 1.0

Digitálny bibliografický a research portál pre speleologické časopisy Spravodaj SSS, Aragonit a Slovenský kras. Cieľom projektu nie je iba zobraziť PDF súbory, ale vytvoriť použiteľnú znalostnú vrstvu nad článkami: bibliografiu, fulltext, citácie, mapové/plánové odkazy, exporty a podklady pre neskoršiu tvorbu súhrnných AI článkov o jaskyniach, oblastiach a histórii objavovania.

## Pre koho je projekt

Projekt je určený pre:

- čitateľov Spravodaja SSS, Aragonitu a Slovenského krasu, ktorí chcú rýchlo nájsť článok, autora, jaskyňu alebo tému,
- správcov bibliografie, ktorí potrebujú overiteľný export v štýle pôvodnej Lalkovičovej bibliografie,
- autorov odborných a sumarizačných článkov, ktorí potrebujú pracovať s celou históriou textov, citácií a PDF strán,
- vývojára alebo správcu portálu, ktorý potrebuje obnoviť dáta, spustiť web a rozumieť pravidlám spracovania.

Po prečítaní tohto README by mal správca vedieť spustiť web, obnoviť exporty, rebuildnúť research databázu, pochopiť mapovú detekciu a správne pracovať s odkazmi na PDF strany.

## Stav verzie 1.0

Aktuálny dataset obsahuje:

- 5911 bibliografických záznamov,
- roky 1958 až 2026,
- 3802 záznamov zo Spravodaja SSS,
- 845 záznamov z Aragonitu,
- 1264 záznamov zo Slovenského krasu,
- 5774 článkov s online PDF odkazom alebo lokálne spracovaným PDF zdrojom,
- 5700 článkov s extrahovaným fulltextom v research databáze,
- 25569 research chunkov,
- 2122 rozpoznaných entít,
- 909 chronologických research timeline výstupov,
- 672 článkov označených ako články s mapou alebo plánom naprieč archívom.

Research manifest uvádza približne 65,8 milióna znakov a 10,3 milióna slov v spracovanom fulltexte. SQLite research databáza sa generuje lokálne a nie je commitovaná, pretože má viac ako 300 MB.

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
- verejný SQLite export pre vlastné SQL analýzy,
- register jaskýň s detailom jaskyne a vertikálnou časovou osou článkov,
- tlačidlo "Našiel som chybu" pri článkoch a jednoduchý formulár na komunitné errata,
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
5. vznikne článkový fulltextový JSONL ako lokálny rebuildovateľný artefakt,
6. research builder vytvorí SQLite FTS databázu, JSONL chunky, entity a timeline výstupy,
7. webový fulltext export sa rozdelí podľa časopisu a roku do menších shardov.

AI sa používa iba tam, kde má pridanú hodnotu: štruktúrované dopĺňanie problematických metadát, voliteľné obohatenie znalostí a potvrdenie mapových/plánových objektov po lokálnom prefiltri.

Pri rescrape PDF zo stránky SSS treba počítať aj s prechodnými názvami časopisu a súborov v rokoch 1987-1992: `Spravodaj`, `Spravodajca`, `Jaskyniar` a krátke súbory `sp921.pdf`, `sp922.pdf`. Scraper ich má pokrývať ako čísla `1987_1-2`, `1988_1-2`, `1989_1`, `1989_2`, `1990_1`, `1991_1`, `1992_1` a `1992_2`.

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

SQLite databáza, článkový fulltextový JSONL, rešeršné chunky a rešeršné balíky sa neukladajú do GitHubu, pretože sú veľké a rebuildovateľné. Web používa iba menší manifest `web/public/data/fulltext_manifest.json` a delené fulltextové shardy v `web/public/data/fulltext/<journal>/<year>.json`.

SQLite schéma nedrží plný text duplicitne v tabuľke článkov. Text je uložený v chunk tabuľke `article_chunks`, zatiaľ čo `chunks_fts` je externý FTS5 index nad touto tabuľkou. Vďaka tomu databáza ostáva menšia a stále vie robiť fulltextové dotazy aj AI rešeršné balíky.

Typické použitie:

```bash
python3 scripts/extract_pdf_fulltext.py --sync-articles
python3 scripts/build_research_knowledge_db.py --force
python3 scripts/export_web_fulltext_index.py
python3 scripts/build_research_knowledge_db.py --query-only --query "Demänovské jaskyne" --top 10
python3 scripts/generate_research_brief.py "Domica" --text-mode chunks
python3 scripts/generate_research_brief.py "Domica" --text-mode full --max-total-chars 240000
```

`generate_research_brief.py` vytvorí AI-ready rešeršný balík v `data/research_briefs/`.
Balík obsahuje iba textové zdroje bez obrázkov: bibliografické údaje, citácie,
PDF odkazy, anotácie a buď vybrané fulltextové chunky, alebo plný text článkov
do nastaveného znakového rozpočtu. Hodí sa ako vstup pre neskoršie písanie
súhrnných článkov o jaskyni alebo lokalite.

Research databáza je multi-journal. Legacy Spravodaj bez explicitného
`journal_id` používa PDF offset `+2`; nové časopisy ako Aragonit a Slovenský kras
používajú fyzické PDF strany uložené pri importe.

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

Typický príkaz na regenerovanie verejných exportov:

```bash
python3 scripts/generate_public_exports.py
```

Výstupy:

- TXT pre jednoduchú kontrolu,
- Markdown pre textové a Git použitie,
- HTML pre prehliadač,
- PDF pre tlač a zdieľanie.

Wrapper vytvorí kombinovaný export pre všetky spracované časopisy aj samostatné exporty pre `Spravodaj SSS`, `Aragonit` a `Slovenský kras`. Rovnaké delenie platí pre HTML, Markdown, PDF aj SQLite export. Samostatný export každého časopisu čísluje články od `1`. Kombinovaný export má v zozname článkov samostatné sekcie podľa časopisov v poradí `Spravodaj SSS`, `Aragonit`, `Slovenský kras`; číslovanie v ňom pokračuje naprieč sekciami, aby registre odkazovali na jednoznačné čísla. Staré názvy `spravodaj_sss_danko.*` a `spravodaj_sss.sqlite` zostávajú ako kompatibilné aliasy na kombinovaný export.

## SQLite export

Verejný SQLite export je určený pre výskumníkov a správcov, ktorí chcú robiť vlastné SQL dotazy nad článkami, autormi, jaskyňami, tagmi, skupinami a mapami/plánmi.

Generovanie všetkých verejných SQLite databáz:

```bash
python3 scripts/generate_public_exports.py
```

Pracovné súbory `data/exports/*.sqlite` sú rebuildovateľné artefakty. Verejné SQLite súbory v `web/public/exports/` obsahujú kombinovaný export aj exporty po časopisoch; `spravodaj_sss.sqlite` zostáva kompatibilný alias na kombinovaný export. Aktuálna schéma obsahuje tabuľky `articles`, `authors`, `article_authors`, `caves`, `article_caves`, `tags`, `article_tags`, `groups`, `article_groups`, `map_plans` a `export_metadata`.

## Register jaskýň

Register jaskýň sa generuje z kurátorovaného poľa `caves`, nie z voľných lokalít alebo znalostných entít. Tým sa znižuje riziko, že sa do registra dostanú obce, pohoria alebo administratívne oblasti.

Generovanie:

```bash
python3 scripts/import_smopaj_cave_register.py
python3 scripts/build_cave_index.py
```

Výstupom je `web/src/data/caves.json`. Web z neho generuje:

- `/jaskyne/` ako register všetkých jaskýň,
- `/jaskyne/<slug>/` ako detail jaskyne,
- vertikálnu časovú os článkov zoradenú od najstaršieho po najnovší,
- oficiálne číslo jaskyne zo SMOPaJ registra, ak je názov jednoznačne spárovaný,
- odkazy na detail článku a PDF stranu so spoločným offsetom `+2`.

Duplicitné alebo pádové varianty názvov jaskýň sa zlučujú cez kurátorovaný súbor `data/cave_aliases.json`. Každá položka má kanonický názov a zoznam aliasov, napríklad `Jasovská jaskyňa` + `Jasovskej jaskyne` + `Jasovská jeskyně`. Pri generovaní registra sa články z aliasov presunú pod kanonický názov a na karte jaskyne sa zobrazí aj zoznam aliasov.

Nejednoznačné názvy sa nemajú zlučovať naslepo. Ak rovnaký názov označuje rôzne jaskyne v rôznych oblastiach, register ich rozdeľuje podľa oblasti, napríklad pri názve `Medvedia jaskyňa`. Podrobné pravidlá pre aliasy, delenie podľa oblasti a pripravovanú geomorfologickú vrstvu sú v [runbooku registra jaskýň a geomorfologického členenia](docs/REGISTER_JASKYN_A_GEOMORFOLOGIA.md).

Geomorfologické tagy sa načítavajú z `data/geomorphology_regions.json` a z oficiálneho SMOPaJ registra `data/smopaj_cave_register_2017.json`, ktorý sa generuje z textových extraktov v `data/source_text/`. Kurátorovaný súbor má prednosť pri problematických známych prípadoch, oficiálny register dopĺňa číslo jaskyne a geomorfologické zaradenie pri jednoznačnej zhode názvu alebo aliasu.

Pri aktuálnom generovaní má webový register 1105 kariet jaskýň/lokalít, 242 z nich má geomorfologický región a 232 má priradené oficiálne SMOPaJ číslo jaskyne. Viacnásobné názvy typu `Medvedia jaskyňa` sa nespájajú naslepo; zostávajú rozdelené podľa oblasti alebo bez oficiálneho čísla, kým nie je zhoda jednoznačná.

Pomocný admin režim je dostupný lokálne na:

```text
/jaskyne/?admin=1
```

Postup pri ďalších duplicitách:

1. Otvor `/jaskyne/?admin=1`.
2. Vyhľadaj podozrivý názov jaskyne.
3. Kliknutím označ duplicitné karty.
4. Podľa potreby uprav kanonický názov.
5. Skopíruj vygenerovaný JSON do `data/cave_aliases.json`.
6. Spusti `python3 scripts/build_cave_index.py` a následne rebuild webu.

## Komunitné errata

Každý článok má odkaz "Našiel som chybu". Formulár je dostupný aj samostatne na `/nahlasit-chybu/`. Statický web používa Cloudflare Pages Function v `web/functions/api/error-report.js`, ktorá po antispam kontrole vytvorí GitHub issue.

Runtime premenné pre hosting:

- `PUBLIC_TURNSTILE_SITE_KEY` pre frontend Turnstile widget,
- `TURNSTILE_SECRET_KEY` pre serverové overenie Turnstile,
- `GITHUB_TOKEN` s právom vytvárať issues v repozitári,
- `GITHUB_REPOSITORY` vo formáte `owner/repo`,
- voliteľne `GITHUB_ISSUE_LABELS` ako čiarkou oddelené existujúce labely,
- voliteľne `ERROR_REPORT_ALLOW_INSECURE=true` len pre lokálny test bez Turnstile.

Do repozitára sa neukladajú žiadne tokeny ani `.env` súbory. Ak Turnstile alebo GitHub premenné nie sú nastavené, backend vráti konfiguračnú chybu namiesto tichého prijatia hlásenia.

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

## Ďalšie časopisy a publikácie

Projekt má samostatnú discovery vrstvu pre ďalšie speleologické časopisy a publikácie. Táto vrstva zatiaľ nemení existujúcu bibliografiu článkov; vytvára iba manifest PDF zdrojov, ktorý sa dá skontrolovať pred importom článkov.

Podporované zdroje:

- `slovensky_kras` - Slovenský kras, prioritne SSJ, potom nová stránka SMOPaJ a starý archív SMOPaJ,
- `aragonit` - časopis Aragonit zo SSJ, iba celé čísla PDF,
- `ine_publikacie` - iné publikácie zo SSJ/SMOPaJ, bez Spravodaja a bez duplicitného Slovenského krasu.

Priorita odkazov pri duplicitách je:

1. `sss.sk`
2. `ssj.sk`
3. `smopaj.sk`
4. `archiv.smopaj.sk`

Vygenerovanie manifestu:

```bash
python3 scripts/journal_sources.py --output data/journal_sources_manifest.json
```

Rýchla kontrola len jedného zdroja:

```bash
python3 scripts/journal_sources.py --journal slovensky_kras --output /tmp/slovensky_kras_manifest.json
python3 scripts/journal_sources.py --journal aragonit --output /tmp/aragonit_manifest.json
```

Aktuálny manifest obsahuje 134 položiek: 78 pre Slovenský kras, 36 pre Aragonit a 20 iných publikácií. Slovenský kras je pokrytý od historických ročníkov zo starého archívu po ročník 61/2023 z novej stránky SMOPaJ. PDF súbory sa pri discovery nesťahujú; čítajú sa iba HTML stránky a odkazy.

Pre budúci import článkov sú pripravené polia `journal_id`, `journal_title`, `journal_short_title` a `pdf_page_offset`. Existujúci Spravodaj používa defaultný offset `+2`, Aragonit používa offset `+2` a Slovenský kras používa offset `0`, pokiaľ konkrétny import neurčí presnejšiu mapu tlačená strana -> fyzická PDF strana.

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
- delené webové fulltextové shardy podľa časopisu/roku,
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
- článkový fulltextový JSONL a rešeršné JSONL chunky,
- generované rešeršné balíky,
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

- doplniť geomorfologické členenie Slovenska ako kurátorovanú vrstvu pre register jaskýň,
- priebežne manuálne auditovať potvrdené mapy a plány v starších ročníkoch,
- doplniť viac AI znalostných obohatení fulltextu cez lacnejší lokálny alebo dávkový režim,
- vytvoriť samostatnú funkciu na generovanie tematických článkov z research databázy,
- doplniť redakčný workflow pre komunitné errata,
- pridať export jednej jaskyne alebo jednej témy ako podklad pre odborný článok.
