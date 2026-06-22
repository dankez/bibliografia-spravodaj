import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_cave_index


def test_build_cave_index_groups_articles_and_sorts_timeline():
    articles = [
        {
            "id": 2,
            "title": "Neskorší výskum",
            "year": 1980,
            "issue": "1",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Pokračovanie výskumu v jaskyni Domica.",
            "pdf_url": "https://example.test/1980.pdf",
            "pdf_page_start": 20,
            "caves": ["Domica"],
            "has_map_plan": True,
            "map_plan_pages": [22],
        },
        {
            "id": 1,
            "title": "Prvý výskum",
            "year": 1970,
            "issue": "2",
            "pages": "10-12",
            "authors": ["Kováč, P."],
            "abstract": "Začiatok výskumu v jaskyni Domica a v Jasovskej jaskyni.",
            "pdf_url": "https://example.test/1970.pdf",
            "pdf_page_start": 10,
            "journal_id": "slovensky_kras",
            "journal_title": "Slovenský kras",
            "journal_short_title": "Slovenský kras",
            "caves": ["Domica", "Jasovská jaskyňa"],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    domica = next(item for item in caves if item["name"] == "Domica")
    assert domica["slug"] == "domica"
    assert domica["article_count"] == 2
    assert domica["map_plan_count"] == 1
    assert domica["first_year"] == 1970
    assert domica["last_year"] == 1980
    assert domica["authors_count"] == 2
    assert [item["id"] for item in domica["articles"]] == [1, 2]
    assert domica["articles"][0]["journal_short_title"] == "Slovenský kras"
    assert domica["articles"][0]["pdf_link"] == "https://example.test/1970.pdf#page=12"

    jasov = next(item for item in caves if item["name"] == "Jasovská jaskyňa")
    assert jasov["article_count"] == 1


def test_build_cave_index_merges_curated_cave_aliases():
    articles = [
        {
            "id": 1,
            "title": "Výskum Jasovskej jaskyne",
            "year": 1964,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa z Jasovskej jaskyne.",
            "caves": ["Jasovská jaskyňa"],
        },
        {
            "id": 2,
            "title": "Meranie v Jasovskej jaskyni",
            "year": 2018,
            "issue": "2",
            "pages": "20",
            "authors": ["Kováč, P."],
            "abstract": "Meranie realizované v Jasovskej jaskyni.",
            "caves": ["Jasovskej jaskyne"],
        },
        {
            "id": 3,
            "title": "Jasovská jeskyně",
            "year": 1968,
            "issue": "3",
            "pages": "30",
            "authors": ["Svoboda, K."],
            "abstract": "Česká zpráva o Jasovské jeskyni.",
            "caves": ["Jasovská jeskyně"],
        },
    ]
    aliases = [
        {
            "canonical": "Jasovská jaskyňa",
            "aliases": ["Jasovskej jaskyne", "Jasovská jeskyně"],
        }
    ]

    caves = build_cave_index.build_cave_index(articles, aliases)

    assert [item["name"] for item in caves] == ["Jasovská jaskyňa"]
    jasov = caves[0]
    assert jasov["slug"] == "jasovska-jaskyna"
    assert set(jasov["aliases"]) == {"Jasovská jeskyně", "Jasovskej jaskyne"}
    assert jasov["article_count"] == 3
    assert jasov["first_year"] == 1964
    assert jasov["last_year"] == 2018
    assert [item["id"] for item in jasov["articles"]] == [1, 3, 2]


def test_build_cave_index_infers_cave_names_from_spravodaj_title_and_abstract():
    articles = [
        {
            "id": 49,
            "title": "Jaskyňa Vlčie diery v Stratenskej hornatine",
            "year": 1970,
            "issue": "3-4",
            "pages": "42-46",
            "authors": ["Hochmuth, Z."],
            "abstract": "Poloha a opis jaskyne, ktorú preskúmali účastníci jaskyniarskeho týždňa SSS.",
            "caves": [],
        },
        {
            "id": 259,
            "title": "Nové objavy v jaskyni Bobačka v Muránskom krase",
            "year": 1976,
            "issue": "3",
            "pages": "13-16",
            "authors": ["Novák, J."],
            "abstract": "Informácia o výsledkoch prieskumu jaskyne po poklese vodnej hladiny.",
            "caves": [],
        },
        {
            "id": 27,
            "title": "Návštevnosť slovenských jaskýň za 1. polrok 1970",
            "year": 1970,
            "issue": "2",
            "pages": "47",
            "authors": ["Anonymus"],
            "abstract": "Tabuľka.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    assert next(item for item in caves if item["name"] == "Jaskyňa Vlčie diery")
    assert next(item for item in caves if item["name"] == "Jaskyňa Bobačka")
    assert all(item["name"] != "slovenských jaskýň" for item in caves)


def test_build_cave_index_filters_generic_cave_card_phrases():
    articles = [
        {
            "id": 1,
            "title": "Nová jaskyňa",
            "year": 1990,
            "issue": "1",
            "pages": "1",
            "authors": ["Novák, J."],
            "abstract": "Krátka správa o novej jaskyni bez uvedenia vlastného názvu.",
            "caves": ["Nová jaskyňa"],
        },
        {
            "id": 2,
            "title": "Praktická starostlivosť o jaskyne",
            "year": 1991,
            "issue": "1",
            "pages": "2",
            "authors": ["Novák, J."],
            "abstract": "Metodické poznámky k starostlivosti o jaskyne.",
            "caves": ["Praktická starostlivosť o jaskyne"],
        },
        {
            "id": 3,
            "title": "Výskum jaskyne Domica",
            "year": 1992,
            "issue": "1",
            "pages": "3",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Domica.",
            "caves": ["Domica"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Domica" in names
    assert "Nová jaskyňa" not in names
    assert "Praktická starostlivosť o jaskyne" not in names


def test_build_cave_index_filters_numeric_context_fragments():
    articles = [
        {
            "id": 1,
            "title": "12 km jaskyne",
            "year": 1990,
            "issue": "1",
            "pages": "1",
            "authors": ["Novák, J."],
            "abstract": "Správa uvádza dĺžku systému, nie názov jaskyne.",
            "caves": ["12 km jaskyne"],
        },
        {
            "id": 2,
            "title": "30 rokov prieskumu",
            "year": 1991,
            "issue": "1",
            "pages": "2",
            "authors": ["Novák, J."],
            "abstract": "Výročný text k dlhodobému prieskumu jaskyne.",
            "caves": ["30 rokov prieskumu"],
        },
        {
            "id": 3,
            "title": "Výskum jaskyne Domica",
            "year": 1992,
            "issue": "1",
            "pages": "3",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Domica.",
            "caves": ["Domica"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Domica" in names
    assert "12 km jaskyne" not in names
    assert "30 rokov prieskumu" not in names


def test_build_cave_index_filters_title_fragments_that_are_not_cave_names():
    articles = [
        {
            "id": 1,
            "title": "Analýza nálezov zo Žihľavovej jaskyne",
            "year": 1990,
            "issue": "1",
            "pages": "1",
            "authors": ["Novák, J."],
            "abstract": "Archeologické nálezy zo Žihľavovej jaskyne.",
            "caves": ["Analýza nálezov zo Žihľavovej jaskyne"],
        },
        {
            "id": 2,
            "title": "Dojmy z návštevy jaskyne",
            "year": 1991,
            "issue": "1",
            "pages": "2",
            "authors": ["Novák, J."],
            "abstract": "Cestopisný text bez názvu konkrétnej jaskyne.",
            "caves": ["Dojmy z návštevy jaskyne"],
        },
        {
            "id": 3,
            "title": "Dračia jaskyňa",
            "year": 1992,
            "issue": "1",
            "pages": "3",
            "authors": ["Novák, J."],
            "abstract": "Správa o Dračej jaskyni.",
            "caves": ["Dračia jaskyňa"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Dračia jaskyňa" in names
    assert "Analýza nálezov zo Žihľavovej jaskyne" not in names
    assert "Dojmy z návštevy jaskyne" not in names


def test_build_cave_index_filters_common_loose_extraction_false_positives():
    articles = [
        {
            "id": 1,
            "title": "Nakreslite si jaskyňu axonometricky",
            "year": 1981,
            "issue": "4",
            "pages": "44",
            "authors": ["Novák, J."],
            "abstract": "Program axonometrického znázornenia jaskyne pre dokumentáciu.",
            "caves": [],
        },
        {
            "id": 2,
            "title": "Objavili nám novú jaskyňu",
            "year": 1989,
            "issue": "1",
            "pages": "60",
            "authors": ["Novák, J."],
            "abstract": "Mýlna informácia ďalekopisu o objave jaskyne bez uvedenia vlastného názvu.",
            "caves": [],
        },
        {
            "id": 3,
            "title": "Rekonštrukcia uzáveru jaskyne Zlá diera",
            "year": 1996,
            "issue": "3",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Oprava uzáveru jaskyne a technické poznámky k zabezpečeniu vchodu.",
            "caves": [],
        },
        {
            "id": 4,
            "title": "Oneskorený príbeh objavu jaskyne Šoldovo vo Važeckom krase",
            "year": 2024,
            "issue": "4",
            "pages": "80",
            "authors": ["Novák, J."],
            "abstract": "Oneskorený príbeh objavu jaskyne Šoldovo.",
            "caves": [],
        },
        {
            "id": 5,
            "title": "Jama Baredine",
            "year": 2007,
            "issue": "3",
            "pages": "55",
            "authors": ["Novák, J."],
            "abstract": "Návšteva sprístupnenej jaskyne v Chorvátsku.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Jaskyňa Zlá diera" in names
    assert "Jaskyňa Šoldovo" in names
    assert "Baredine" in names
    assert "Nakreslite si jaskyňu" not in names
    assert "Program axonometrického znázornenia jaskyne" not in names
    assert "Objavili nám novú jaskyňu" not in names
    assert "Mylná informácia ďalekopisu o objave jaskyne" not in names
    assert "Rekonštrukcia uzáveru jaskyne Zlá diera" not in names
    assert "Oprava uzáveru jaskyne" not in names
    assert "Oneskorený príbeh objavu jaskyne" not in names
    assert "Návšteva sprístupnenej jaskyne" not in names


def test_build_cave_index_keeps_verified_plural_or_group_cave_names():
    articles = [
        {
            "id": 1,
            "title": "Jaskyne na Stodôlke v Demänovskej doline",
            "year": 1995,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyniach na Stodôlke.",
            "caves": ["Jaskyne na Stodôlke"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "K problematike Dračích jaskýň Demänovskej doliny",
            "year": 2004,
            "issue": "2",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Výskum Dračích jaskýň.",
            "caves": ["Dračie jaskyne"],
            "caves_verified": True,
        },
        {
            "id": 3,
            "title": "Kryštály kalcitu v Kalcitových jaskyniach 1 a 2",
            "year": 2008,
            "issue": "3",
            "pages": "30",
            "authors": ["Novák, J."],
            "abstract": "Výskum Kalcitových jaskýň 1 a 2 na Poludnici.",
            "caves": ["Kalcitové jaskyne 1 a 2"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Jaskyne na Stodôlke" in names
    assert "Dračie jaskyne" in names
    assert "Kalcitové jaskyne 1 a 2" in names


def test_build_cave_index_filters_report_titles_and_workflow_fragments():
    articles = [
        {
            "id": 1,
            "title": "Krátka správa o Tichej jaskyni",
            "year": 2011,
            "issue": "4",
            "pages": "34",
            "authors": ["Novák, J."],
            "abstract": "Krátka správa, nie štandardizovaný názov karty.",
            "caves": [],
        },
        {
            "id": 2,
            "title": "Výskum jaskyne",
            "year": 1997,
            "issue": "1",
            "pages": "40",
            "authors": ["Novák, J."],
            "abstract": "Zpráva o výkopových prácach v jaskyni.",
            "caves": [],
        },
        {
            "id": 3,
            "title": "Zameranie jaskyne",
            "year": 2002,
            "issue": "4",
            "pages": "37",
            "authors": ["Novák, J."],
            "abstract": "Výsledky mapovacieho kurzu.",
            "caves": [],
        },
        {
            "id": 4,
            "title": "Vyhlásenie súťaže o umelecké stvárnenie jaskyne",
            "year": 2009,
            "issue": "1",
            "pages": "78",
            "authors": ["Redakcia"],
            "abstract": "Administratívna správa bez mena konkrétnej jaskyne.",
            "caves": [],
        },
        {
            "id": 5,
            "title": "Text zachytáva spomienky spájajúce jaskyne",
            "year": 2010,
            "issue": "4",
            "pages": "41",
            "authors": ["Novák, J."],
            "abstract": "Text zachytáva spomienky spájajúce jaskyne a vojnové udalosti.",
            "caves": [],
        },
        {
            "id": 6,
            "title": "Pôdorysná mapa Mamutej jaskyne",
            "year": 1973,
            "issue": "4",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Pôdorysná mapa nie je samostatný názov slovenskej jaskyne.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Krátka správa o Tichej jaskyni" not in names
    assert "Výskum jaskyne" not in names
    assert "Zameranie jaskyne" not in names
    assert "Vyhlásenie súťaže o umelecké stvárnenie jaskyne" not in names
    assert "Text zachytáva spomienky spájajúce jaskyne" not in names
    assert "Pôdorysná mapa Mamutej jaskyne" not in names


def test_build_cave_index_keeps_real_cave_and_filters_neighboring_descriptive_fragment():
    articles = [
        {
            "id": 1,
            "title": "Jaskyňa Kamenné mlieko v Belianskych Tatrách",
            "year": 1982,
            "issue": "1",
            "pages": "12",
            "authors": ["Novák, J."],
            "abstract": "Speleologický prieskum a charakter jaskyne v závere doliny Medzisteny.",
            "caves": [],
        },
        {
            "id": 2,
            "title": "Jaskyňa Plačúca skala",
            "year": 1996,
            "issue": "2",
            "pages": "15",
            "authors": ["Novák, J."],
            "abstract": "Krátka riečna jaskyňa ukončená prietokovým vodným sifónom.",
            "caves": [],
        },
        {
            "id": 3,
            "title": "Vystrojovanie jaskyne Veľké Prepadlé",
            "year": 2006,
            "issue": "2",
            "pages": "40",
            "authors": ["Novák, J."],
            "abstract": "Osadenie rebríkov v jaskyni koncom sezóny.",
            "caves": [],
        },
        {
            "id": 4,
            "title": "Rudolf Gajda a jaskyne na Slovensku",
            "year": 2007,
            "issue": "1",
            "pages": "93",
            "authors": ["Novák, J."],
            "abstract": "Charakter záujmu R. Gajdu o jaskyne Slovenského krasu.",
            "caves": [],
        },
        {
            "id": 5,
            "title": "Súčasťou Novohradského geoparku budú aj jaskyne",
            "year": 2008,
            "issue": "1",
            "pages": "70",
            "authors": ["Novák, J."],
            "abstract": "Príspevok informuje, že súčasťou geoparku budú aj jaskyne.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Jaskyňa Kamenné mlieko" in names
    assert "Jaskyňa Plačúca skala" in names
    assert "Jaskyňa Veľké Prepadlé" in names
    assert "Speleologický prieskum" not in names
    assert "Krátka riečna jaskyňa" not in names
    assert "Vystrojovanie jaskyne" not in names
    assert "Rudolf Gajda" not in names
    assert "Gajdu o jaskyne" not in names
    assert "Jaskyňa Slovenského krasu" not in names
    assert "Súčasťou Novohradského geoparku budú aj jaskyne" not in names
    assert "Novohradského geoparku budú aj jaskyne" not in names


def test_build_cave_index_uses_article_pdf_page_offset_when_present():
    articles = [
        {
            "id": 1,
            "title": "Projekt ochrany jaskyne",
            "year": 2024,
            "issue": "2",
            "pages": "100",
            "authors": ["Novák, J."],
            "abstract": "Projekt ochrany Demänovskej jaskyne.",
            "pdf_url": "https://example.test/aragonit.pdf",
            "pdf_page_start": 54,
            "pdf_page_offset": 0,
            "caves": ["Demänovské jaskyne"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Spravodaj článok",
            "year": 2026,
            "issue": "1",
            "pages": "57",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Domica.",
            "pdf_url": "https://example.test/spravodaj.pdf",
            "pdf_page_start": 57,
            "caves": ["Domica"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    demanovske = next(item for item in caves if item["name"] == "Demänovské jaskyne")
    domica = next(item for item in caves if item["name"] == "Domica")
    assert demanovske["articles"][0]["pdf_link"] == "https://example.test/aragonit.pdf#page=54"
    assert domica["articles"][0]["pdf_link"] == "https://example.test/spravodaj.pdf#page=59"


def test_build_cave_index_requires_direct_cave_phrase_not_loose_stem_match():
    articles = [
        {
            "id": 1,
            "title": "Stratenská jaskyňa",
            "year": 1974,
            "issue": "2",
            "pages": "22",
            "authors": ["Novotný, L."],
            "abstract": "Pokračovanie v prieskume Stratenskej jaskyne.",
            "caves": ["Stratenská jaskyňa"],
        },
        {
            "id": 2,
            "title": "Tomášovská jaskyňa v Stratenskej hornatine",
            "year": 1971,
            "issue": "4",
            "pages": "17-18",
            "authors": ["Novotný, L."],
            "abstract": "Opis jaskyne na okraji Stratenskej hornatiny.",
            "caves": ["Stratenská jaskyňa"],
        },
        {
            "id": 3,
            "title": "Novoobjavená jaskyňa Stratený potok pod Muránskou planinou",
            "year": 2004,
            "issue": "1",
            "pages": "33-44",
            "authors": ["Pap, I."],
            "abstract": "Prieskum a mapovanie jaskyne Stratený potok.",
            "caves": ["Stratenská jaskyňa"],
        },
        {
            "id": 4,
            "title": "Speleoexpedície do vnútra masívu Chimantá",
            "year": 2005,
            "issue": "3",
            "pages": "",
            "authors": ["Šmída, B."],
            "abstract": "Stratený svet Guayanskej vysočiny a Cueva Charles Brewer.",
            "caves": ["Stratenská jaskyňa"],
        },
        {
            "id": 6,
            "title": "Jazvečia jaskyňa - ďalší vstup do Dobšinsko-stratenského jaskynného systému?",
            "year": 2020,
            "issue": "3",
            "pages": "22-25",
            "authors": ["Horváth, J."],
            "abstract": "Článok sa zaoberá Jazvečou jaskyňou a možnosťou jej súvisu s Dobšinsko-stratenským jaskynným systémom.",
            "caves": ["Stratenská jaskyňa"],
        },
        {
            "id": 5,
            "title": "Prvé spomienky na Stratenskú jaskyňu",
            "year": 1984,
            "issue": "1",
            "pages": "3-5",
            "authors": ["Košel, V."],
            "abstract": "Opis objavu prvých priestorov Stratenskej jaskyne.",
            "caves": ["Stratenská jaskyňa"],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    stratenska = next(item for item in caves if item["name"] == "Stratenská jaskyňa")
    assert [item["id"] for item in stratenska["articles"]] == [1, 5]


def test_build_cave_index_accepts_verified_cave_metadata_without_exact_phrase():
    articles = [
        {
            "id": 1,
            "title": "Potrava sovy obyčajnej v jaskyni Maštaľná na Plešivskej planine",
            "year": 2023,
            "issue": "2",
            "pages": "129-138",
            "authors": ["Obuch, J."],
            "abstract": "Obsahový záznam importovaný z obsahu čísla.",
            "caves": ["Maštaľná jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Tomášovská jaskyňa v Stratenskej hornatine",
            "year": 1971,
            "issue": "4",
            "pages": "17-18",
            "authors": ["Novotný, L."],
            "abstract": "Opis jaskyne na okraji Stratenskej hornatiny.",
            "caves": ["Stratenská jaskyňa"],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    mastalna = next(item for item in caves if item["name"] == "Maštaľná jaskyňa")
    assert [item["id"] for item in mastalna["articles"]] == [1]
    assert all(item["name"] != "Stratenská jaskyňa" for item in caves)


def test_build_cave_index_deduplicates_same_cave_timeline_article_variants():
    articles = [
        {
            "id": 82,
            "title": "Oslavy 50. výročia jaskyne Slobody",
            "year": 1971,
            "volume": "II.",
            "issue": "4 (chybné stránkovanie)",
            "pages": "3-4",
            "authors": ["Tarnócy, Ľ."],
            "abstract": "Podujatia k výročiu objavenia Demänovskej jaskyne slobody.",
            "pdf_url": "https://example.test/714.pdf",
            "pdf_page_start": 3,
            "caves": ["Demänovské jaskyne"],
            "caves_verified": True,
        },
        {
            "id": 90,
            "title": "Oslavy 50. výročia jaskyne Slobody",
            "year": 1971,
            "volume": "II.",
            "issue": "4 (nové vydanie)",
            "pages": "3-4",
            "authors": ["Tarnócy, Ľ."],
            "abstract": "Podujatia k výročiu objavenia Demänovskej jaskyne slobody.",
            "pdf_url": "https://example.test/714.pdf",
            "pdf_page_start": 3,
            "caves": ["Demänovské jaskyne"],
            "caves_verified": True,
        },
        {
            "id": 2634,
            "title": "Oslavy 50. výročia jaskyne Slobody",
            "year": 1971,
            "issue": "4",
            "pages": "3 – 4",
            "authors": ["Tarnócy, Ľ."],
            "abstract": "Správa o oslavách 50. výročia objavenia Demänovskej jaskyne Slobody, vedeckom seminári, výstave, pietnej spomienke a slávnostnom koncerte v jaskyni.",
            "pdf_url": "https://example.test/714.pdf",
            "pdf_page_start": 3,
            "caves": ["Demänovské jaskyne"],
            "caves_verified": True,
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    demanovske = next(item for item in caves if item["name"] == "Demänovské jaskyne")
    assert demanovske["article_count"] == 1
    assert [item["id"] for item in demanovske["articles"]] == [2634]
    assert demanovske["articles"][0]["issue"] == "4"


def test_build_cave_index_splits_ambiguous_cave_names_by_area():
    articles = [
        {
            "id": 1,
            "title": "Medvedia jaskyňa v Stratenskej hornatine",
            "year": 1964,
            "issue": "",
            "pages": "10-36",
            "authors": ["Janáčik, P."],
            "abstract": "Príspevok opisuje Medvediu jaskyňu v Stratenskej hornatine v Slovenskom raji.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Medvedia jaskyňa v Jánskej doline",
            "year": 1991,
            "issue": "1",
            "pages": "13-17",
            "authors": ["Vajs, J."],
            "abstract": "Poloha Medvedej jaskyne v Jánskej doline v Nízkych Tatrách.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 3,
            "title": "Prejavy recentných pohybov v Medvedej jaskyni v Malej Fatre",
            "year": 1983,
            "issue": "",
            "pages": "209-216",
            "authors": ["Pavlarčík, S."],
            "abstract": "Príspevok sa zaoberá Medveďou jaskyňou v Malej Fatre.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 4,
            "title": "Z činnosti oblastnej skupiny č. 2",
            "year": 1970,
            "issue": "1",
            "pages": "27",
            "authors": ["Novák, J."],
            "abstract": "Prieskum komína v Medvedej jaskyni na svahu planiny Glac v Slovenskom raji.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    medvedie = [item for item in caves if item["name"] == "Medvedia jaskyňa"]

    assert {item["area"] for item in medvedie} == {
        "Slovenský raj / Stratenská hornatina",
        "Jánska dolina / Nízke Tatry",
        "Malá Fatra",
    }
    assert {item["area"]: item["article_count"] for item in medvedie} == {
        "Slovenský raj / Stratenská hornatina": 2,
        "Jánska dolina / Nízke Tatry": 1,
        "Malá Fatra": 1,
    }
    assert all(item["slug"].startswith("medvedia-jaskyna-") for item in medvedie)


def test_build_cave_index_adds_geomorphology_from_area_and_cave_name():
    articles = [
        {
            "id": 1,
            "title": "Medvedia jaskyňa v Jánskej doline",
            "year": 1991,
            "issue": "1",
            "pages": "13-17",
            "authors": ["Vajs, J."],
            "abstract": "Poloha Medvedej jaskyne v Jánskej doline v Nízkych Tatrách.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Výskum Jasovskej jaskyne",
            "year": 2018,
            "issue": "2",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Správa z Jasovskej jaskyne.",
            "caves": ["Jasovská jaskyňa"],
            "caves_verified": True,
        },
    ]
    geomorphology = {
        "areas": {
            "Jánska dolina / Nízke Tatry": {
                "local_area": "Jánska dolina",
                "geomorph_unit": "Nízke Tatry",
                "geomorph_area": "Fatransko-tatranská oblasť",
                "confidence": "curated",
            }
        },
        "caves": {
            "Jasovská jaskyňa": {
                "local_area": "Jasovská planina",
                "geomorph_unit": "Slovenský kras",
                "geomorph_area": "Slovenské rudohorie",
                "confidence": "curated",
            }
        },
    }

    caves = build_cave_index.build_cave_index(articles, geomorphology=geomorphology)

    medvedia = next(item for item in caves if item["name"] == "Medvedia jaskyňa")
    jasovska = next(item for item in caves if item["name"] == "Jasovská jaskyňa")

    assert medvedia["region"]["geomorph_unit"] == "Nízke Tatry"
    assert medvedia["region"]["local_area"] == "Jánska dolina"
    assert jasovska["region"]["geomorph_unit"] == "Slovenský kras"
    assert jasovska["region"]["local_area"] == "Jasovská planina"


def test_build_cave_index_normalizes_medvedia_inflected_context_titles():
    articles = [
        {
            "id": 1,
            "title": "Revízne zameranie Medvedej jaskyne",
            "year": 1998,
            "issue": "2",
            "pages": "56-59",
            "authors": ["Novák, J."],
            "abstract": "Dôvody revízneho zamerania Medvedej jaskyne v Jánskej doline.",
            "caves": [],
        },
        {
            "id": 2,
            "title": "Uzavretie Medvedej jaskyne II",
            "year": 2005,
            "issue": "4",
            "pages": "63",
            "authors": ["Mrázik, P."],
            "abstract": "Inštalácia uzáveru jaskyne v roku 2003 členmi Jaskyniarskeho klubu Varín.",
            "caves": [],
        },
        {
            "id": 3,
            "title": "Vek kostí jaskynného medveďa z jaskyne Psie diery v Slovenskom raji",
            "year": 1993,
            "issue": "2",
            "pages": "14-15",
            "authors": ["Hochmuth, Z."],
            "abstract": "Charakter nálezu kostí jaskynného medveďa z Medvedej chodby jaskyne Psie diery.",
            "caves": [],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)
    names = {item["name"] for item in caves}

    assert "Revízne zameranie Medvedej jaskyne" not in names
    assert "Uzavretie Medvedej jaskyne" not in names
    assert "Medvedej chodby jaskyne Psie diery" not in names
    assert next(item for item in caves if item["name"] == "Medvedia jaskyňa")["area"] == "Jánska dolina / Nízke Tatry"
    assert next(item for item in caves if item["name"] == "Jaskyňa Medvedia II")["area"] == "Vrátna dolina / Malá Fatra"
    assert next(item for item in caves if item["name"] == "Jaskyňa Psie diery")["area"] == "Slovenský raj / Psie diery"


def test_build_cave_index_does_not_assign_context_area_to_unambiguous_caves():
    articles = [
        {
            "id": 1,
            "title": "Domica a zahraničné porovnania",
            "year": 1977,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Článok opisuje jaskyňu Domica a spomína jaskyne v Poľsku len ako porovnanie.",
            "caves": ["Domica"],
            "caves_verified": True,
        }
    ]

    caves = build_cave_index.build_cave_index(articles)

    domica = next(item for item in caves if item["name"] == "Domica")
    assert domica["area"] == ""
    assert domica["slug"] == "domica"
    assert "cave_area" not in domica["articles"][0]


def test_build_cave_index_adds_official_smopaj_cave_number_and_region_for_unique_match():
    articles = [
        {
            "id": 1,
            "title": "Výskum jaskyne Domica",
            "year": 1970,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Domica.",
            "caves": ["Jaskyňa Domica"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Dobšinská ľadová jaskyňa",
            "year": 1971,
            "issue": "2",
            "pages": "20",
            "authors": ["Kováč, P."],
            "abstract": "Správa o Dobšinskej ľadovej jaskyni.",
            "caves": ["Dobšinská ľadová jaskyňa"],
            "caves_verified": True,
        },
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "3483.1",
                "registry_number": "238",
                "official_name": "Domica",
                "names": ["Domica"],
                "geomorph_celok": "Slovenský kras",
                "geomorph_podcelok": "Silická planina",
                "geomorph_cast": "",
            },
            {
                "cave_number": "4503",
                "registry_number": "105",
                "official_name": "Dobšinská ľadová jaskyňa",
                "names": ["Dobšinská ľadová jaskyňa"],
                "geomorph_celok": "Spišsko-gemerský kras",
                "geomorph_podcelok": "Slovenský raj",
                "geomorph_cast": "",
            },
        ]
    }

    caves = build_cave_index.build_cave_index(articles, smopaj_register=smopaj_register)

    domica = next(item for item in caves if item["name"] == "Domica")
    dobsinska = next(item for item in caves if item["name"] == "Dobšinská ľadová jaskyňa")

    assert domica["smopaj_cave_number"] == "3483.1"
    assert domica["smopaj_registry_number"] == "238"
    assert domica["region"]["geomorph_unit"] == "Slovenský kras"
    assert domica["region"]["local_area"] == "Silická planina"
    assert dobsinska["smopaj_cave_number"] == "4503"
    assert dobsinska["region"]["geomorph_unit"] == "Spišsko-gemerský kras"
    assert dobsinska["region"]["local_area"] == "Slovenský raj"


def test_build_cave_index_infers_inflected_official_smopaj_cave_mentions():
    articles = [
        {
            "id": 1195,
            "title": "Nové objavy v Jaskyni zlomísk",
            "year": 1996,
            "issue": "1",
            "pages": "27-28",
            "authors": ["Holúbek, P."],
            "abstract": "Prieskum Východnej siene jaskyne.",
            "caves": [],
        },
        {
            "id": 1273,
            "title": "Sifón Tichá tôňa v Jaskyni zlomísk",
            "year": 1997,
            "issue": "1",
            "pages": "40-41",
            "authors": ["Hutňan, D."],
            "abstract": "O prieskume sifónu v Jaskyni zlomísk.",
            "caves": [],
        },
        {
            "id": 1292,
            "title": "The Jaskyňa Zlomísk Cave",
            "year": 1997,
            "issue": "2",
            "pages": "14-15",
            "authors": ["Holúbek, P."],
            "abstract": "English note about Zlomiská Cave.",
            "caves": [],
        },
        {
            "id": 2451,
            "title": "Čo nové v Jaskyni zlomísk? Za posledných 10 rokov takmer nič!",
            "year": 2008,
            "issue": "4",
            "pages": "13-17",
            "authors": ["Holúbek, P."],
            "abstract": "Južný koniec, Ujgurská šikmina, Demänovský sifón a Sintrový sifón.",
            "caves": [],
        },
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "1709",
                "registry_number": "29",
                "official_name": "Jaskyňa zlomísk",
                "names": ["Jaskyňa zlomísk", "Jožova jaskyňa"],
                "aliases": ["Jožova jaskyňa"],
                "geomorph_celok": "Nízke Tatry",
                "geomorph_podcelok": "Ďumbierske Tatry",
                "geomorph_cast": "Demänovské vrchy",
            }
        ]
    }

    caves = build_cave_index.build_cave_index(articles, smopaj_register=smopaj_register)

    zlomisk = next(item for item in caves if item["name"] == "Jaskyňa zlomísk")
    assert zlomisk["smopaj_cave_number"] == "1709"
    assert zlomisk["region"]["geomorph_unit"] == "Nízke Tatry"
    assert [item["id"] for item in zlomisk["articles"]] == [1195, 1273, 1292, 2451]

    names = {item["name"] for item in caves}
    assert "Sifón Tichá tôňa" not in names
    assert "Demänovský sifón" not in names
    assert "Jaskyňa Zlomísk Cave" not in names


def test_build_cave_index_uses_short_distinctive_token_for_registered_cave_name():
    articles = [
        {
            "id": 1469,
            "title": "Nová turisticky sprístupnená jaskyňa Zlá diera pri Lipovciach",
            "year": 1999,
            "issue": "2",
            "pages": "37",
            "authors": ["Novák, J."],
            "abstract": "Stručne o sprístupnení ďalšej jaskyne a jej slávnostnom otvorení.",
            "caves": [],
        }
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "19",
                "registry_number": "100",
                "official_name": "Zlá diera",
                "names": ["Zlá diera", "Zlá džura"],
                "geomorph_celok": "Bachureň",
                "geomorph_podcelok": "",
                "geomorph_cast": "",
            }
        ]
    }

    caves = build_cave_index.build_cave_index(articles, smopaj_register=smopaj_register)
    names = {item["name"] for item in caves}

    assert names == {"Zlá diera"}
    zla_diera = caves[0]
    assert zla_diera["smopaj_cave_number"] == "19"
    assert zla_diera["article_count"] == 1


def test_build_cave_index_does_not_auto_assign_official_number_for_ambiguous_smopaj_name():
    articles = [
        {
            "id": 1,
            "title": "Medvedia jaskyňa",
            "year": 1970,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o Medvedej jaskyni.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        }
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "276",
                "registry_number": "1053",
                "official_name": "Medvedia jaskyňa",
                "names": ["Medvedia jaskyňa"],
                "geomorph_celok": "Čierna hora",
                "geomorph_podcelok": "Pokryvy",
                "geomorph_cast": "",
            },
            {
                "cave_number": "1810",
                "registry_number": "360",
                "official_name": "Medvedia jaskyňa",
                "names": ["Medvedia jaskyňa", "Zimná jaskyňa"],
                "geomorph_celok": "Nízke Tatry",
                "geomorph_podcelok": "Ďumbierske Tatry",
                "geomorph_cast": "Ďumbierske vrchy",
            },
        ]
    }

    caves = build_cave_index.build_cave_index(articles, smopaj_register=smopaj_register)

    medvedia = next(item for item in caves if item["name"] == "Medvedia jaskyňa")
    assert "smopaj_cave_number" not in medvedia
    assert "region" not in medvedia


def test_build_cave_index_uses_curated_smopaj_override_for_ambiguous_name():
    articles = [
        {
            "id": 1,
            "title": "Jaskyňa Pustá – pokračovanie prieskumu",
            "year": 1980,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Pustá v systéme Pustá – Psie diery v Demänovskej doline.",
            "caves": ["Jaskyňa Pustá"],
            "caves_verified": True,
        }
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "1509.8",
                "registry_number": "247",
                "official_name": "Pustá jaskyňa",
                "names": ["Pustá jaskyňa", "Psie diery"],
                "geomorph_celok": "Nízke Tatry",
                "geomorph_podcelok": "Demänovské vrchy",
                "geomorph_cast": "",
            },
            {
                "cave_number": "4784",
                "registry_number": "867",
                "official_name": "Pustá jaskyňa",
                "names": ["Pustá jaskyňa"],
                "geomorph_celok": "Spišsko-gemerský kras",
                "geomorph_podcelok": "Slovenský raj",
                "geomorph_cast": "",
            },
        ]
    }
    smopaj_overrides = {
        "matches": [
            {
                "cave_slug": "jaskyna-pusta",
                "cave_number": "1509.8",
                "confidence": "ai-curated-high",
                "note": "Article context mentions Pustá - Psie diery in Demänovská dolina.",
            }
        ]
    }

    caves = build_cave_index.build_cave_index(
        articles,
        smopaj_register=smopaj_register,
        smopaj_overrides=smopaj_overrides,
    )

    pusta = next(item for item in caves if item["name"] == "Pustá jaskyňa")
    assert pusta["smopaj_cave_number"] == "1509.8"
    assert pusta["smopaj_registry_number"] == "247"
    assert pusta["smopaj_match_confidence"] == "ai-curated-high"
    assert pusta["smopaj_match_source"] == "curated-override"
    assert pusta["region"]["geomorph_unit"] == "Nízke Tatry"
    assert pusta["aliases"] == ["Jaskyňa Pustá"]


def test_build_cave_index_rejects_curated_smopaj_override_with_unknown_number():
    articles = [
        {
            "id": 1,
            "title": "Jaskyňa Pustá",
            "year": 1980,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Pustá.",
            "caves": ["Jaskyňa Pustá"],
            "caves_verified": True,
        }
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "1509.8",
                "registry_number": "247",
                "official_name": "Pustá jaskyňa",
                "names": ["Pustá jaskyňa"],
            }
        ]
    }
    smopaj_overrides = {
        "matches": [
            {
                "cave_slug": "jaskyna-pusta",
                "cave_number": "999999",
                "confidence": "ai-curated-high",
            }
        ]
    }

    with pytest.raises(ValueError, match="999999"):
        build_cave_index.build_cave_index(
            articles,
            smopaj_register=smopaj_register,
            smopaj_overrides=smopaj_overrides,
        )


def test_build_cave_index_uses_area_specific_curated_override_for_repeated_cave_name():
    articles = [
        {
            "id": 1,
            "title": "Medvedia jaskyňa v Stratenskej hornatine",
            "year": 1964,
            "issue": "",
            "pages": "10-36",
            "authors": ["Janáčik, P."],
            "abstract": "Príspevok opisuje Medvediu jaskyňu v Stratenskej hornatine v Slovenskom raji.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Medvedia jaskyňa v Jánskej doline",
            "year": 1991,
            "issue": "1",
            "pages": "13-17",
            "authors": ["Vajs, J."],
            "abstract": "Poloha Medvedej jaskyne v Jánskej doline v Nízkych Tatrách.",
            "caves": ["Medvedia jaskyňa"],
            "caves_verified": True,
        },
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "4692",
                "registry_number": "95",
                "official_name": "Medvedia jaskyňa",
                "names": ["Medvedia jaskyňa"],
                "geomorph_celok": "Spišsko-gemerský kras",
                "geomorph_podcelok": "Slovenský raj",
            },
            {
                "cave_number": "1810",
                "registry_number": "360",
                "official_name": "Medvedia jaskyňa",
                "names": ["Medvedia jaskyňa", "Zimná jaskyňa"],
                "geomorph_celok": "Nízke Tatry",
                "geomorph_podcelok": "Ďumbierske Tatry",
                "geomorph_cast": "Demänovské vrchy",
            },
        ]
    }
    smopaj_overrides = {
        "matches": [
            {
                "cave_name": "Medvedia jaskyňa",
                "cave_area": "Slovenský raj / Stratenská hornatina",
                "cave_number": "4692",
                "confidence": "ai-curated-high",
            },
            {
                "cave_name": "Medvedia jaskyňa",
                "cave_area": "Jánska dolina / Nízke Tatry",
                "cave_number": "1810",
                "confidence": "ai-curated-high",
            },
        ]
    }

    caves = build_cave_index.build_cave_index(
        articles,
        smopaj_register=smopaj_register,
        smopaj_overrides=smopaj_overrides,
    )

    by_area = {item["area"]: item for item in caves if item["name"] == "Medvedia jaskyňa"}
    assert by_area["Slovenský raj / Stratenská hornatina"]["smopaj_cave_number"] == "4692"
    assert by_area["Jánska dolina / Nízke Tatry"]["smopaj_cave_number"] == "1810"


def test_build_cave_index_splits_same_name_by_article_specific_smopaj_match():
    articles = [
        {
            "id": 1,
            "title": "Zbojnícka diera v Čergove",
            "year": 1997,
            "issue": "1",
            "pages": "38-39",
            "authors": ["Novák, J."],
            "abstract": "Správa o Zbojníckej diere známej aj ako Oltárkameň v Čergove.",
            "caves": ["Zbojnícka diera"],
            "caves_verified": True,
        },
        {
            "id": 2,
            "title": "Zbojnícka diera pri Švošove",
            "year": 2010,
            "issue": "2",
            "pages": "34-36",
            "authors": ["Kováč, P."],
            "abstract": "Príspevok predstavuje Zbojnícku dieru pri Švošove vo Veľkej Fatre.",
            "caves": ["Zbojnícka diera"],
            "caves_verified": True,
        },
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "211",
                "registry_number": "3757",
                "official_name": "Zbojnícka diera",
                "names": ["Zbojnícka diera", "Oltárkameň"],
                "aliases": ["Oltárkameň"],
                "geomorph_celok": "Čergov",
                "geomorph_podcelok": "",
            },
            {
                "cave_number": "6796",
                "registry_number": "2961",
                "official_name": "Zbojnícka diera",
                "names": ["Zbojnícka diera"],
                "geomorph_celok": "Veľká Fatra",
                "geomorph_podcelok": "Šípska Fatra",
            },
        ]
    }
    smopaj_overrides = {
        "article_matches": [
            {
                "article_ids": [1],
                "cave_slug": "zbojnicka-diera",
                "cave_number": "211",
                "confidence": "manual-confirmed-high",
            },
            {
                "article_ids": [2],
                "cave_slug": "zbojnicka-diera",
                "cave_number": "6796",
                "confidence": "manual-confirmed-high",
            },
        ]
    }

    caves = build_cave_index.build_cave_index(
        articles,
        smopaj_register=smopaj_register,
        smopaj_overrides=smopaj_overrides,
    )

    by_number = {item["smopaj_cave_number"]: item for item in caves if item["name"] == "Zbojnícka diera"}
    assert set(by_number) == {"211", "6796"}
    assert [item["id"] for item in by_number["211"]["articles"]] == [1]
    assert [item["id"] for item in by_number["6796"]["articles"]] == [2]
    assert by_number["211"]["area"] == "Čergov"
    assert by_number["6796"]["area"] == "Veľká Fatra / Šípska Fatra"
    assert by_number["211"]["region"]["geomorph_unit"] == "Čergov"
    assert by_number["6796"]["region"]["geomorph_subunit"] == "Šípska Fatra"


def test_build_cave_index_merges_ai_smopaj_match_source_after_curated_overrides():
    manual_overrides = {
        "matches": [
            {
                "cave_slug": "jaskyna-pusta",
                "cave_number": "1509.8",
                "confidence": "manual-confirmed-high",
            }
        ]
    }
    ai_matches = {
        "matches": [
            {
                "cave_slug": "jaskyna-okno",
                "cave_number": "1519",
                "confidence": "ai-assisted-high",
            },
            {
                "cave_slug": "jaskyna-pusta",
                "cave_number": "4784",
                "confidence": "ai-assisted-high",
            },
        ]
    }

    merged = build_cave_index.merge_smopaj_match_sources(manual_overrides, ai_matches)

    by_slug = {item["cave_slug"]: item for item in merged["matches"]}
    assert by_slug["jaskyna-pusta"]["cave_number"] == "1509.8"
    assert by_slug["jaskyna-pusta"]["match_source"] == "curated-override"
    assert by_slug["jaskyna-okno"]["cave_number"] == "1519"
    assert by_slug["jaskyna-okno"]["match_source"] == "ai-generated-override"


def test_build_cave_index_marks_ai_generated_smopaj_override_source():
    articles = [
        {
            "id": 1,
            "title": "Jaskyňa Okno v Demänovskej doline",
            "year": 1980,
            "issue": "1",
            "pages": "10",
            "authors": ["Novák, J."],
            "abstract": "Správa o jaskyni Okno v Demänovskej doline.",
            "caves": ["Jaskyňa Okno"],
            "caves_verified": True,
        }
    ]
    smopaj_register = {
        "entries": [
            {
                "cave_number": "1519",
                "registry_number": "1001",
                "official_name": "Okno",
                "names": ["Okno", "Jaskyňa Okno"],
                "geomorph_celok": "Nízke Tatry",
                "geomorph_podcelok": "Demänovské vrchy",
            }
        ]
    }
    ai_overrides = build_cave_index.merge_smopaj_match_sources(
        {},
        {
            "matches": [
                {
                    "cave_slug": "jaskyna-okno",
                    "cave_number": "1519",
                    "confidence": "ai-assisted-high",
                }
            ]
        },
    )

    caves = build_cave_index.build_cave_index(
        articles,
        smopaj_register=smopaj_register,
        smopaj_overrides=ai_overrides,
    )

    okno = next(item for item in caves if item["name"] == "Okno")
    assert okno["smopaj_cave_number"] == "1519"
    assert okno["smopaj_match_source"] == "ai-generated-override"
    assert okno["smopaj_match_confidence"] == "ai-assisted-high"


def test_current_cave_index_data_is_generated_for_web():
    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    assert caves_path.exists()


def test_current_javorinka_alias_points_to_high_tatras_official_record():
    import json

    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    caves = json.loads(caves_path.read_text(encoding="utf-8"))

    javorinka = next(item for item in caves if item["slug"] == "javorinka")
    assert javorinka["name"] == "Javorinka"
    assert "Jaskyňa Javorinka" in javorinka["aliases"]
    assert javorinka["smopaj_cave_number"] == "5930.1"
    assert javorinka["region"]["geomorph_part"] == "Vysoké Tatry"


def test_current_stratenska_jaskyna_timeline_excludes_known_false_positives():
    import json

    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    caves = json.loads(caves_path.read_text(encoding="utf-8"))
    stratenska = next(item for item in caves if item["slug"] == "stratenska-jaskyna")
    article_ids = {item["id"] for item in stratenska["articles"]}

    assert not ({49, 85, 93, 592, 690, 1628, 1858, 1974, 2127, 2524, 3334} & article_ids)
