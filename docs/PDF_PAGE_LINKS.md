# Pravidlá PDF odkazov

Tento dokument je pre správcu bibliografie, ktorý obnovuje exporty, web alebo research podklady. Po prečítaní má vedieť správne rozlíšiť bibliografickú stranu článku od fyzickej strany PDF a overiť, že odkazy otvárajú správne miesto v dokumente.

## Základné pravidlo

Bibliografia zobrazuje tlačenú stranu časopisu. PDF kotva v odkaze musí otvoriť fyzickú stranu PDF súboru.

Pre článkové odkazy platí globálne pravidlo:

```text
pdf anchor page = printed page + 2
```

Príklad:

```text
STRANY: s. 57
PDF: #page=59
```

Toto pravidlo platí pre všetky ročníky a všetky článkové PDF odkazy vo webe, exportoch aj research citáciách.

## Čo sa neposúva

Hodnota `pages` je bibliografický údaj a nemení sa. V reporte aj na webe musí používateľ stále vidieť tlačenú stranu článku, napríklad `s. 57`.

Strany máp a plánov uložené ako `map_plan_pages` sú už fyzické PDF strany z detekčnej pipeline. Tie sa druhýkrát neposúvajú.

## Kde sa pravidlo používa

Rovnaký offset musia používať tri výstupné vrstvy:

- webový zoznam článkov a detail článku,
- Danko HTML, Markdown a PDF exporty,
- research databáza a citácie v retrieval výstupoch.

Ak sa pridá nový exportér alebo nový typ odkazu na článok v PDF, musí používať rovnaké pravidlo. Výnimku možno spraviť len vtedy, keď je v dátach výslovne uložená fyzická PDF strana a je jasné, že sa už nemá počítať z tlačenej strany.

## Kontrola po zmene dát

Po každom importe článkov, oprave strán alebo regenerovaní exportov skontroluj aspoň jeden článok v reporte aj na detailnej webovej stránke:

1. zobrazená hodnota `STRANY` alebo `Strany` ostáva tlačená strana,
2. PDF URL obsahuje `#page` o 2 vyššie,
3. otvorený PDF dokument zobrazuje rovnakú tlačenú stranu v päte alebo hlavičke časopisu,
4. mapové odkazy stále vedú na detegovanú fyzickú stranu mapy alebo plánu.

Odporúčaná automatická kontrola:

```bash
python3 -m pytest tests/test_pdf_link_page_offsets.py tests/test_export_lalkovic_format.py
```

Odporúčaná manuálna kontrola známeho prípadu:

```text
3413. Oblastná skupina Orava
STRANY: s. 57
PDF kotva: #page=59
```

Ak sa tento príklad vráti na `#page=57`, pravidlo sa niekde obišlo alebo bolo znovu zavedené ročníkové vetvenie.
