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
    assert domica["articles"][0]["pdf_link"] == "https://example.test/1970.pdf#page=12"

    jasov = next(item for item in caves if item["name"] == "Jasovská jaskyňa")
    assert jasov["article_count"] == 1


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
