import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repair_suspicious_articles as repair


def test_repair_embedded_pages_title_and_abstract():
    articles = [
        {
            "id": 1423,
            "title": "Čachtické jasky",
            "pages": "44",
            "pdf_page_start": 46,
            "pdf_url": "https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_4_1998.pdf",
        },
        {
            "id": 1424,
            "authors": ["Hochmuth, Z."],
            "title": (
                "História speleopotápačských výskumov na Slovensku, 2 obr., lit., "
                "s. 45 – 51 Obdobie pred znovuobnovením SSS v roku 1969, pôsobenie "
                "zahraničných potápačov"
            ),
            "extras": [],
            "pages": "",
            "abstract": "",
            "pdf_page_start": None,
            "pdf_page_end": None,
            "pdf_url": "https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_4_1998.pdf",
        },
    ]

    changes = repair.repair_articles(articles)
    fixed = articles[1]

    assert changes[0]["id"] == 1424
    assert fixed["title"] == "História speleopotápačských výskumov na Slovensku"
    assert fixed["extras"] == ["2 obr.", "lit."]
    assert fixed["pages"] == "45-51"
    assert fixed["abstract"].startswith("Obdobie pred znovuobnovením SSS")
    assert fixed["pdf_page_start"] == 47
    assert fixed["pdf_page_end"] == 53


def test_suspicious_reasons_include_missing_pages_and_long_title():
    article = {
        "id": 1,
        "title": "x" * 221,
        "pages": "",
    }

    reasons = repair.suspicion_reasons(article)

    assert "missing_pages" in reasons
    assert "long_title" in reasons


def test_build_ai_candidate_contains_pdf_context_request():
    article = {
        "id": 1,
        "title": "Nejasný záznam",
        "pages": "",
        "pdf_url": "https://sss.sk/test.pdf",
    }

    candidate = repair.build_ai_candidate(article, ["missing_pages"], "PDF text")

    assert candidate["id"] == 1
    assert candidate["reasons"] == ["missing_pages"]
    assert "PDF text" in candidate["prompt"]
    assert "title" in candidate["schema"]["properties"]


def test_parse_authoritative_bibliography_handles_split_page_line():
    text = """
Ročník 1998 (XXIX.)
Číslo 4
1423. Ducár, J.: Čachtické jasky, 1 obr., s. 44
Dobový opis
1424. Hochmuth, Z.: História speleopotápačských výskumov na Slovensku, 2 obr., lit.,
s. 45 – 51
Obdobie pred znovuobnovením SSS v roku 1969
1425. Holúbek, P.: Niekoľko poznámok, 1 obr., s. 52 – 54
Niečo z histórie
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[1424]
    assert fixed["authors"] == ["Hochmuth, Z."]
    assert fixed["title"] == "História speleopotápačských výskumov na Slovensku"
    assert fixed["extras"] == ["2 obr.", "lit."]
    assert fixed["pages"] == "45-51"
    assert fixed["abstract"] == "Obdobie pred znovuobnovením SSS v roku 1969"


def test_parse_authoritative_bibliography_handles_missing_comma_before_pages():
    text = """
Ročník 1983 (XIV.)
Číslo 1
553. Roda, Š.: Quo vadis, jaskyniar?, s. 1
Úvaha o jaskyniarovi
554. Mrázik, P.: Nové objavy vo Veľkej Fatre, 1 obr., 1 pl. j. s. 3 – 4
Opis jaskyne Javorina
555. Hlaváč, J.: Správa o činnosti SSS za rok 1982, 3 obr., s. 5 – 11
Členská základňa
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[554]
    assert fixed["title"] == "Nové objavy vo Veľkej Fatre"
    assert fixed["extras"] == ["1 obr.", "1 pl. j."]
    assert fixed["pages"] == "3-4"
    assert fixed["abstract"] == "Opis jaskyne Javorina"


def test_split_authors_keeps_surname_initial_pairs_together():
    authors = repair.split_authors("Šmída, B., Brewer-Carías, Ch., Audy, M.")

    assert authors == ["Šmída, B.", "Brewer-Carías, Ch.", "Audy, M."]


def test_parse_authoritative_bibliography_handles_discontinuous_pages():
    text = """
Ročník 1985 (XVI.)
Číslo 1
704. Anonymus: Lezecké dni v Slovenskom krase, 2 obr., s. 1 a 32 – 33
O vzniku podujatia
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[704]
    assert fixed["title"] == "Lezecké dni v Slovenskom krase"
    assert fixed["extras"] == ["2 obr."]
    assert fixed["pages"] == "1 a 32-33"
    assert repair.page_bounds(fixed["pages"]) == (1, 33)


def test_parse_authoritative_bibliography_handles_no_colon_author_typo():
    text = """
Ročník 2009 (XL.)
Číslo 3
2515. Holúbek, p. Jaskyniarske týždne sss, 3 obr., 2 tab., s. 6 – 8
Prehľad o jaskyniarskych týždňoch
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[2515]
    assert fixed["authors"] == ["Holúbek, p."]
    assert fixed["title"] == "Jaskyniarske týždne sss"
    assert fixed["extras"] == ["3 obr.", "2 tab."]
    assert fixed["pages"] == "6-8"


def test_parse_authoritative_bibliography_does_not_read_issn_as_pages():
    text = """
Ročník 2003 (XXXIV.)
Číslo 2 (mimoriadne číslo)
1905. Šmída, B., Audy, M., Vlček, L.: Expedícia Roraima 2003, Venezuela, 191 s.,
issn 1335-5023
Predvýprava, prípravy
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[1905]
    assert fixed["authors"] == ["Šmída, B.", "Audy, M.", "Vlček, L."]
    assert fixed["title"] == "Expedícia Roraima 2003, Venezuela, 191 s., issn 1335-5023"
    assert fixed["pages"] == ""
    assert fixed["abstract"] == "Predvýprava, prípravy"


def test_parse_authoritative_bibliography_does_not_treat_split_extra_number_as_page():
    text = """
Ročník 1996 (XXVII.)
Číslo 1
1206. Hochmuth, Z.: Používanie a údržba baníckeho čelového osvetlenia typu 1662 E, 2
obr., lit., s. 48 – 49
Podstatné náležitosti okolo používania čelového osvetlenia
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[1206]
    assert fixed["title"] == "Používanie a údržba baníckeho čelového osvetlenia typu 1662 E"
    assert fixed["extras"] == ["2 obr.", "lit."]
    assert fixed["pages"] == "48-49"
    assert fixed["abstract"] == "Podstatné náležitosti okolo používania čelového osvetlenia"


def test_parse_authoritative_bibliography_moves_page_postscript_to_abstract():
    text = """
Ročník 1973 (IV.)
Číslo 3
152. Erdős, M.: Bezpečnostné predpisy pre členov SSS, s. 8 – 23 (dokončenie)
Osobné ochranné pomôcky
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[152]
    assert fixed["title"] == "Bezpečnostné predpisy pre členov SSS"
    assert fixed["pages"] == "8-23"
    assert fixed["abstract"] == "(dokončenie) Osobné ochranné pomôcky"


def test_parse_authoritative_bibliography_accepts_missing_dot_after_page_abbreviation():
    text = """
Ročník 2006 (XXXVII.)
Číslo 2
2201. Soják, M.: Archeologické svedectvá v Praslene, 9 obr., lit., s 41 – 43
Opis archeologických nálezov
"""

    records = repair.parse_authoritative_bibliography_text(text)

    fixed = records[2201]
    assert fixed["title"] == "Archeologické svedectvá v Praslene"
    assert fixed["extras"] == ["9 obr.", "lit."]
    assert fixed["pages"] == "41-43"
    assert fixed["abstract"] == "Opis archeologických nálezov"


def test_apply_authoritative_records_repairs_historic_article_and_preserves_online_fields():
    articles = [
        {
            "id": 1423,
            "title": "Čachtické jasky",
            "pages": "44",
            "pdf_page_start": 46,
            "pdf_url": "https://sss.sk/Spravodaj_SSS_4_1998.pdf",
            "year": 1998,
        },
        {
            "id": 1424,
            "authors": ["Hochmuth, Z."],
            "title": "História speleopotápačských výskumov na Slovensku, 2 obr., lit., s. 45 – 51 Obdobie",
            "extras": [],
            "pages": "",
            "abstract": "",
            "pdf_page_start": None,
            "pdf_page_end": None,
            "pdf_url": "https://sss.sk/Spravodaj_SSS_4_1998.pdf",
            "year": 1998,
        },
    ]
    authoritative = {
        1424: {
            "id": 1424,
            "authors": ["Hochmuth, Z."],
            "title": "História speleopotápačských výskumov na Slovensku",
            "pages": "45-51",
            "extras": ["2 obr.", "lit."],
            "year": 1998,
            "volume": "XXIX.",
            "issue": "4",
            "abstract": "Obdobie pred znovuobnovením SSS",
        }
    }

    changes = repair.apply_authoritative_records(articles, authoritative)
    fixed = articles[1]

    assert changes[0]["id"] == 1424
    assert fixed["title"] == "História speleopotápačských výskumov na Slovensku"
    assert fixed["extras"] == ["2 obr.", "lit."]
    assert fixed["pages"] == "45-51"
    assert fixed["pdf_url"] == "https://sss.sk/Spravodaj_SSS_4_1998.pdf"
    assert fixed["pdf_page_start"] == 47
    assert fixed["pdf_page_end"] == 53


def test_apply_authoritative_records_clears_pdf_pages_when_authoritative_pages_missing():
    articles = [
        {
            "id": 2127,
            "authors": ["AI"],
            "title": "AI title",
            "pages": "3-10",
            "extras": [],
            "year": 2005,
            "volume": "XXXVI.",
            "issue": "3",
            "abstract": "",
            "pdf_url": "https://sss.sk/Spravodaj-2005-3.pdf",
            "pdf_page_start": 5,
            "pdf_page_end": 12,
        }
    ]
    authoritative = {
        2127: {
            "id": 2127,
            "authors": ["Šmída, B.", "Brewer-Carías, Ch.", "Audy, M."],
            "title": "Speleoexpedície do vnútra masívu Chimantá",
            "pages": "",
            "extras": [],
            "year": 2005,
            "volume": "XXXVI.",
            "issue": "3 (mimoriadne číslo)",
            "abstract": "Pôvodná anotácia",
        }
    }

    repair.apply_authoritative_records(articles, authoritative)

    assert articles[0]["pages"] == ""
    assert articles[0]["pdf_page_start"] is None
    assert articles[0]["pdf_page_end"] is None


def test_sync_pdf_urls_from_map_uses_numeric_issue_core_with_parenthetical_note():
    articles = [
        {
            "id": 1,
            "year": 1979,
            "issue": "2",
            "pages": "3",
            "pdf_url": "https://sss.sk/Spravodaj_2_1979.pdf",
            "pdf_page_start": 4,
            "pdf_page_end": 4,
        },
        {
            "id": 2,
            "year": 1979,
            "issue": "2 (venované konferencii Dokumentácia krasu a jaskýň)",
            "pages": "57-63",
            "pdf_url": "https://sss.sk/Spravodaj_1_1979.pdf",
            "pdf_page_start": 57,
            "pdf_page_end": 63,
        },
    ]

    changes = repair.sync_pdf_urls_from_map(
        articles,
        {"1979_2": "https://sss.sk/Spravodaj_2_1979.pdf"},
    )

    assert changes[0]["id"] == 2
    assert articles[1]["pdf_url"] == "https://sss.sk/Spravodaj_2_1979.pdf"
    assert articles[1]["pdf_page_start"] == 58
    assert articles[1]["pdf_page_end"] == 64


def test_apply_ai_result_updates_article_when_confident():
    articles = [
        {
            "id": 1,
            "title": "Predošlý článok",
            "pages": "9",
            "pdf_page_start": 11,
            "pdf_page_end": 11,
            "pdf_url": "https://sss.sk/issue.pdf",
        },
        {
            "id": 3000,
            "authors": ["Anonymus"],
            "title": "Príliš dlhý chybný názov",
            "pages": "",
            "extras": [],
            "abstract": "",
            "pdf_page_start": None,
            "pdf_page_end": None,
            "pdf_url": "https://sss.sk/issue.pdf",
        },
    ]
    articles_by_pdf = {"https://sss.sk/issue.pdf": articles}
    result = {
        "title": "Opravený názov",
        "authors": ["Novák, J."],
        "pages": "10 – 12",
        "extras": ["2 obr.", "lit."],
        "abstract": "Overená anotácia",
        "confidence": 0.9,
        "needs_human_review": False,
    }

    change, status = repair.apply_ai_result(articles[1], result, articles_by_pdf, min_confidence=0.75)

    assert status == "applied"
    assert change["id"] == 3000
    assert articles[1]["title"] == "Opravený názov"
    assert articles[1]["authors"] == ["Novák, J."]
    assert articles[1]["pages"] == "10-12"
    assert articles[1]["pdf_page_start"] == 12
    assert articles[1]["pdf_page_end"] == 14


def test_apply_ai_result_rejects_low_confidence():
    article = {
        "id": 2,
        "title": "Pôvodný názov",
        "authors": ["Anonymus"],
        "pages": "",
        "extras": [],
        "abstract": "",
    }

    change, status = repair.apply_ai_result(
        article,
        {
            "title": "Neistý názov",
            "authors": ["Novák, J."],
            "pages": "10",
            "extras": [],
            "abstract": "",
            "confidence": 0.4,
            "needs_human_review": False,
        },
        {},
        min_confidence=0.75,
    )

    assert change is None
    assert status == "low_confidence"
    assert article["title"] == "Pôvodný názov"


def test_apply_ai_result_historic_keeps_authoritative_metadata_and_fills_pages():
    articles = [
        {
            "id": 1,
            "title": "Predošlý článok",
            "pages": "9",
            "pdf_page_start": 11,
            "pdf_page_end": 11,
            "pdf_url": "https://sss.sk/issue.pdf",
        },
        {
            "id": 1580,
            "authors": ["Iždinský, L."],
            "title": "Jaskyne Nad Kadlubom a Podbanište sa spojili",
            "pages": "",
            "extras": ["4 obr.", "1 pl. j.", "lit."],
            "abstract": "Pôvodná anotácia",
            "pdf_page_start": None,
            "pdf_page_end": None,
            "pdf_url": "https://sss.sk/issue.pdf",
        },
    ]
    result = {
        "title": "Ako sa spojili jaskyne Podbanište a Nad Kadlubom",
        "authors": ["Ladislav Iždinský"],
        "pages": "5 – 8",
        "extras": [],
        "abstract": "AI anotácia",
        "confidence": 0.93,
        "needs_human_review": False,
    }

    change, status = repair.apply_ai_result(
        articles[1],
        result,
        {"https://sss.sk/issue.pdf": articles},
        min_confidence=0.75,
    )

    assert status == "applied"
    assert change["source"] == "codex_ai_fallback_pages_only"
    assert articles[1]["authors"] == ["Iždinský, L."]
    assert articles[1]["title"] == "Jaskyne Nad Kadlubom a Podbanište sa spojili"
    assert articles[1]["abstract"] == "Pôvodná anotácia"
    assert articles[1]["pages"] == "5-8"
    assert articles[1]["pdf_page_start"] == 7
    assert articles[1]["page_source"] == "codex_ai_fallback_pages_only"


def test_apply_ai_result_historic_rejects_title_mismatch():
    article = {
        "id": 2127,
        "authors": ["Šmída, B.", "Brewer-Carías, Ch.", "Audy, M."],
        "title": "Speleoexpedície do vnútra masívu Chimantá (Venezuela) v roku 2004",
        "pages": "",
        "extras": [],
        "abstract": "Pôvodná anotácia",
    }

    change, status = repair.apply_ai_result(
        article,
        {
            "title": "Cueva Charles Brewer the greatest quartzite caves of the world",
            "authors": ["Šmída, Branislav"],
            "pages": "3-10",
            "extras": [],
            "abstract": "Iný článok",
            "confidence": 0.93,
            "needs_human_review": False,
        },
        {},
        min_confidence=0.75,
    )

    assert change is None
    assert status == "historic_title_mismatch"
    assert article["pages"] == ""


def test_apply_authoritative_records_preserves_ai_verified_missing_pages():
    articles = [
        {
            "id": 968,
            "authors": ["Kladiva, E."],
            "title": "Úvodník",
            "pages": "1",
            "extras": [],
            "year": 1992,
            "volume": "XXIII.",
            "issue": "2",
            "abstract": "O charaktere čísla",
            "pdf_url": "https://sss.sk/sp922.pdf",
            "pdf_page_start": 3,
            "pdf_page_end": 3,
            "page_source": "codex_ai_fallback_pages_only",
        }
    ]
    authoritative = {
        968: {
            "id": 968,
            "authors": ["Kladiva, E."],
            "title": "Úvodník",
            "pages": "",
            "extras": [],
            "year": 1992,
            "volume": "XXIII.",
            "issue": "2",
            "abstract": "O charaktere čísla",
        }
    }

    repair.apply_authoritative_records(articles, authoritative)

    assert articles[0]["pages"] == "1"
