import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import journal_sources


def test_extract_links_normalizes_relative_urls_and_text():
    html = """
    <a href="/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf">
      <span>2009/2</span>
    </a>
    """

    links = journal_sources.extract_links(html, "http://archiv.smopaj.sk/index.php/Online_publik%C3%A1cie")

    assert links == [
        journal_sources.Link(
            url="http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf",
            text="2009/2",
        )
    ]


def test_extract_links_uses_anchor_title_when_link_has_no_text():
    html = """
    <a href="/sk/documentloader.php?id=5336&filename=zborník 61_2_2023.pdf"
       title="Slovenský kras 61 - 2 - 2023"><img src="/icon.png"></a>
    """

    links = journal_sources.extract_links(html, "https://www.smopaj.sk/sk/slovensky-kras")

    assert links == [
        journal_sources.Link(
            url="https://www.smopaj.sk/sk/documentloader.php?id=5336&filename=zborník 61_2_2023.pdf",
            text="Slovenský kras 61 - 2 - 2023",
        )
    ]


def test_slovensky_kras_identity_handles_full_issue_and_continued_parts():
    identity = journal_sources.parse_slovensky_kras_identity(
        "2009/2",
        "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf",
    )

    assert identity["issue_key"] == "47_2009_2"
    assert identity["volume"] == "47"
    assert identity["year"] == 2009
    assert identity["issue"] == "2"
    assert identity["item_type"] == "issue"
    assert identity["pdf_page_offset"] == 0


def test_slovensky_kras_identity_handles_smopaj_documentloader_issue_pdf():
    identity = journal_sources.parse_slovensky_kras_identity(
        "Slovenský kras 61 - 2 - 2023",
        "https://www.smopaj.sk/sk/documentloader.php?id=5336&filename=zborník 61_2_2023.pdf",
    )

    assert identity["issue_key"] == "61_2023_2"
    assert identity["volume"] == "61"
    assert identity["year"] == 2023
    assert identity["issue"] == "2"
    assert identity["item_type"] == "issue"
    assert identity["pdf_page_offset"] == 0


def test_slovensky_kras_identity_infers_smopaj_supplement_year_from_volume():
    identity = journal_sources.parse_slovensky_kras_identity(
        "Slovenský kras 61 supplementum",
        "https://www.smopaj.sk/sk/documentloader.php?id=5335&filename=zborník 61_supplementum net.pdf",
    )

    assert identity["issue_key"] == "61_2023_suppl"
    assert identity["year_label"] == "2023"
    assert identity["year"] == 2023
    assert identity["issue"] == "suppl"


def test_slovensky_kras_identity_handles_smopaj_single_volume_without_issue_number():
    identity = journal_sources.parse_slovensky_kras_identity(
        "Slovenský kras 45 - 2007",
        "https://www.smopaj.sk/sk/documentloader.php?id=330&filename=sk-45-2007.pdf",
    )

    assert identity["issue_key"] == "45_2007"
    assert identity["volume"] == "45"
    assert identity["year"] == 2007
    assert identity["issue"] == ""


def test_slovensky_kras_identity_handles_year_range_volume():
    identity = journal_sources.parse_slovensky_kras_identity(
        "1957-1958",
        "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/2_1957_1958.pdf",
    )

    assert identity["issue_key"] == "2_1957-1958"
    assert identity["year_label"] == "1957-1958"
    assert identity["year"] == 1958


def test_slovensky_kras_identity_normalizes_supplement_issue_label():
    identity = journal_sources.parse_slovensky_kras_identity(
        "2008/supl.",
        "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/46_2008_supl_1.pdf",
    )

    assert identity["issue_key"] == "46_2008_suppl-1"
    assert identity["issue"] == "suppl-1"


def test_slovensky_kras_identity_keeps_ssj_article_pdf_under_supplement_context():
    identity = journal_sources.parse_slovensky_kras_identity(
        "Attempt on the reconstruction",
        "https://www.ssj.sk/sk/user_files/ACS_47_S101.pdf",
        context="Slovenský kras 47 Suppl. 1 2009",
    )

    assert identity["issue_key"] == "47_2009_suppl-1_acs_47_s101"
    assert identity["issue"] == "suppl-1"
    assert identity["item_type"] == "article_pdf"


def test_slovensky_kras_source_excludes_individual_acs_article_pdfs():
    source = journal_sources.source_by_id("ssj_slovensky_kras")

    assert journal_sources.source_allows_link(
        source,
        journal_sources.Link("http://www.ssj.sk/web/user_files/SlovKras-kompl.pdf", "Celé číslo"),
    )
    assert not journal_sources.source_allows_link(
        source,
        journal_sources.Link("https://www.ssj.sk/sk/user_files/ACS_47_S101.pdf", "Samostatný článok"),
    )


def test_slovensky_kras_new_smopaj_source_accepts_documentloader_issue_pdfs():
    source = journal_sources.source_by_id("smopaj_slovensky_kras_new")

    assert journal_sources.source_allows_link(
        source,
        journal_sources.Link(
            "https://www.smopaj.sk/sk/documentloader.php?id=5336&filename=zborník 61_2_2023.pdf",
            "Slovenský kras 61 - 2 - 2023",
        ),
    )


def test_aragonit_identity_uses_whole_issue_pdf_filename():
    identity = journal_sources.parse_aragonit_identity(
        "Celé číslo v PDF",
        "http://www.ssj.sk/user_files/Aragon_29_2_web.pdf",
        context="Časopis Aragonit č. 29/2 Vydala Správa slovenských jaskýň roku 2024.",
    )

    assert identity["issue_key"] == "29_2"
    assert identity["volume"] == "29"
    assert identity["issue"] == "2"
    assert identity["year"] == 2024
    assert identity["item_type"] == "issue"
    assert identity["pdf_page_offset"] == 2


def test_aragonit_first_issue_uses_1996_from_detail_page_context_and_two_page_offset():
    identity = journal_sources.parse_aragonit_identity(
        "Celé číslo v PDF",
        "https://www.ssj.sk/sk/user_files/Aragonit1_komplet.pdf",
        context=(
            "Časopis Aragonit č. 1. "
            "Vydala Správa slovenských jaskýň v Liptovskom Mikuláši roku 1996."
        ),
    )

    assert identity["issue_key"] == "1"
    assert identity["year"] == 1996
    assert identity["pdf_page_offset"] == 2


def test_aragonit_identity_infers_year_from_volume_when_detail_page_has_no_year():
    identity = journal_sources.parse_aragonit_identity(
        "Celé číslo v PDF",
        "http://www.ssj.sk/user_files/Aragon_29_2_web.pdf",
        context="Časopis Aragonit č. 29/2 Obsah / Contents",
    )

    assert identity["issue_key"] == "29_2"
    assert identity["year"] == 2024
    assert identity["year_label"] == "2024"


def test_aragonit_source_excludes_cover_only_pdfs():
    source = journal_sources.source_by_id("ssj_aragonit")

    assert journal_sources.source_allows_link(
        source,
        journal_sources.Link("https://www.ssj.sk/sk/user_files/Aragonit13_1_komplet.pdf", "Celé číslo v PDF"),
    )
    assert not journal_sources.source_allows_link(
        source,
        journal_sources.Link("https://www.ssj.sk/sk/user_files/Aragonit13_1obal.pdf", "Obálka"),
    )
    assert not journal_sources.source_allows_link(
        source,
        journal_sources.Link("https://www.ssj.sk/sk/user_files/Aragonit7_10.pdf", "Samostatný článok"),
    )


def test_choose_best_candidates_prefers_domain_priority_and_keeps_alternatives():
    smopaj = journal_sources.build_manifest_item(
        "slovensky_kras",
        "Slovenský kras",
        "Slovenský kras",
        {"source_id": "smopaj", "url": "http://archiv.smopaj.sk/index.php/Online_publik%C3%A1cie", "priority": 3},
        journal_sources.Link(
            "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf",
            "2009/2",
        ),
    )
    ssj = journal_sources.build_manifest_item(
        "slovensky_kras",
        "Slovenský kras",
        "Slovenský kras",
        {"source_id": "ssj", "url": "https://www.ssj.sk/sk/slovensky-kras", "priority": 2},
        journal_sources.Link("https://www.ssj.sk/sk/user_files/47_2009_2.pdf", "Slovenský kras 47/2"),
    )

    chosen = journal_sources.choose_best_candidates([smopaj, ssj])

    assert len(chosen) == 1
    assert chosen[0]["pdf_url"] == "https://www.ssj.sk/sk/user_files/47_2009_2.pdf"
    assert chosen[0]["alternatives"][0]["pdf_url"] == smopaj["pdf_url"]


def test_choose_best_candidates_prefers_new_smopaj_page_over_old_archive():
    old_archive = journal_sources.build_manifest_item(
        "slovensky_kras",
        "Slovenský kras",
        "Slovenský kras",
        {
            "source_id": "smopaj_slovensky_kras",
            "url": "http://archiv.smopaj.sk/index.php/Online_publik%C3%A1cie",
            "priority": 4,
        },
        journal_sources.Link(
            "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf",
            "2009/2",
        ),
    )
    new_page = journal_sources.build_manifest_item(
        "slovensky_kras",
        "Slovenský kras",
        "Slovenský kras",
        {
            "source_id": "smopaj_slovensky_kras_new",
            "url": "https://www.smopaj.sk/sk/slovensky-kras",
            "priority": 3,
        },
        journal_sources.Link(
            "https://www.smopaj.sk/sk/documentloader.php?id=344&filename=sk-47_2-2009.pdf",
            "Slovenský kras 47 - 2 - 2009",
        ),
    )

    chosen = journal_sources.choose_best_candidates([old_archive, new_page])

    assert len(chosen) == 1
    assert chosen[0]["source_id"] == "smopaj_slovensky_kras_new"
    assert chosen[0]["alternatives"][0]["source_id"] == "smopaj_slovensky_kras"


def test_smopaj_other_publications_excludes_spravodaj_and_slovensky_kras_duplicates():
    spravodaj = journal_sources.Link(
        "http://archiv.smopaj.sk/data/_uploaded/media/public/Spravodaj_SSS/Spravodaj_SSS_1988_1-2_0001.pdf",
        "1988/1-2",
    )
    kras = journal_sources.Link(
        "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_2.pdf",
        "2009/2",
    )
    jvs = journal_sources.Link(
        "http://archiv.smopaj.sk/data/_uploaded/media/public/JVS/Peniny.pdf",
        "Pěniny",
    )
    source = journal_sources.source_by_id("smopaj_other_publications")

    assert not journal_sources.source_allows_link(source, spravodaj)
    assert not journal_sources.source_allows_link(source, kras)
    assert journal_sources.source_allows_link(source, jvs)


def test_discover_journal_sources_crawls_ssj_detail_pages_for_pdf_links():
    pages = {
        "https://www.ssj.sk/sk/casopis-aragonit": """
            <a href="https://www.ssj.sk/sk/clanok/634-casopis-aragonit-c-29-2">Časopis Aragonit č. 29/2</a>
        """,
        "https://www.ssj.sk/sk/clanok/634-casopis-aragonit-c-29-2": """
            <p>Vydala Správa slovenských jaskýň roku 2024.</p>
            <a class="pdf" href="http://www.ssj.sk/user_files/Aragon_29_2_web.pdf">Celé číslo v PDF</a>
        """,
    }

    def fetch(url):
        return pages[url]

    manifest = journal_sources.discover_journal_sources(
        journals=[journal_sources.journal_by_id("aragonit")],
        fetch_text=fetch,
    )

    assert manifest["summary"]["items"] == 1
    assert manifest["items"][0]["journal_id"] == "aragonit"
    assert manifest["items"][0]["issue_key"] == "29_2"
    assert manifest["items"][0]["year"] == 2024
    assert manifest["items"][0]["pdf_page_offset"] == 2
    assert manifest["items"][0]["pdf_url"] == "http://www.ssj.sk/user_files/Aragon_29_2_web.pdf"
