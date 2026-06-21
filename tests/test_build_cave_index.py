import sys
from pathlib import Path

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


def test_current_cave_index_data_is_generated_for_web():
    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    assert caves_path.exists()


def test_current_stratenska_jaskyna_timeline_excludes_known_false_positives():
    import json

    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    caves = json.loads(caves_path.read_text(encoding="utf-8"))
    stratenska = next(item for item in caves if item["slug"] == "stratenska-jaskyna")
    article_ids = {item["id"] for item in stratenska["articles"]}

    assert not ({49, 85, 93, 592, 690, 1628, 1858, 1974, 2127, 2524, 3334} & article_ids)
