import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_lalkovic_format as exporter


def test_article_line_hides_pdf_url_behind_short_markdown_label():
    article = {
        "id": 816,
        "authors": ["Piovarči, E."],
        "title": "Na terchovskej akcii",
        "extras": ["4 obr."],
        "pages": "45-50",
        "pdf_url": "https://sss.sk/wp-content/uploads/2022/04/Spravodaj_SSS_1987_1-2.pdf",
        "pdf_page_start": 47,
    }

    line = exporter.article_line(article, markdown=True)

    assert line.startswith('<span id="clanok-816"></span>**816. Na terchovskej akcii**')
    assert "**AUTOR:** Piovarči, E." in line
    assert "**STRANY:** s. 45 – 50 [↗ PDF](" in line
    assert "Spravodaj_SSS_1987_1-2.pdf#page=47)" in line
    assert "**POZNÁMKY:** 4 obr." in line
    assert "Online:" not in line


def test_plain_article_line_uses_readable_labeled_block():
    article = {
        "id": 816,
        "authors": ["Piovarči, E."],
        "title": "Na terchovskej akcii",
        "extras": ["4 obr."],
        "pages": "45-50",
    }

    line = exporter.article_line(article, markdown=False)

    assert line.splitlines() == [
        "816. Na terchovskej akcii",
        "     AUTOR: Piovarči, E.",
        "     STRANY: s. 45 – 50",
        "     POZNÁMKY: 4 obr.",
    ]


def test_maps_and_plans_hides_pdf_url_behind_short_markdown_label():
    article = {
        "id": 100,
        "year": 1987,
        "issue": "1-2",
        "authors": ["Autor"],
        "title": "Mapa krasového územia",
        "extras": ["1 mapa"],
        "pages": "10",
        "pdf_url": "https://sss.sk/Spravodaj_SSS_1987_1-2.pdf",
        "pdf_page_start": 12,
    }

    markdown = exporter.render_maps_and_plans([article], markdown=True)

    assert "[↗ PDF](" in markdown
    assert "Online: [https://" not in markdown
    assert "Spravodaj_SSS_1987_1-2.pdf#page=12)" in markdown


def test_render_html_document_preserves_headings_and_pdf_links():
    markdown = (
        "# Bibliografia Spravodaja SSS\n\n"
        "## Ročník 2007 (XXXVIII.)\n\n"
        "### Číslo 1\n\n"
        "2298. Ošková, M.: Speleofotografia 2006, s. 92  \n"
        "Online: [↗ PDF](https://sss.sk/Spravodaj-2007-1.pdf#page=94)\n"
    )

    html = exporter.render_html_document(markdown, "Test export")

    assert "<!doctype html>" in html
    assert "<h1>Bibliografia Spravodaja SSS</h1>" in html
    assert "<h2>Ročník 2007 (XXXVIII.)</h2>" in html
    assert "<h3>Číslo 1</h3>" in html
    assert "Speleofotografia 2006" in html
    assert 'href="https://sss.sk/Spravodaj-2007-1.pdf#page=94"' in html
    assert ">↗ PDF</a>" in html
    assert ">https://sss.sk/Spravodaj-2007-1.pdf#page=94</a>" not in html


def test_render_html_document_styles_article_title_and_metadata():
    markdown = (
        '<span id="clanok-816"></span>**816. Na terchovskej akcii**\n'
        "**AUTOR:** Piovarči, E.  \n"
        "**STRANY:** s. 45 – 50 [↗ PDF](https://sss.sk/example.pdf#page=47)\n"
    )

    html = exporter.render_html_document(markdown, "Test")

    assert '<p class="article-title"><span id="clanok-816"></span><strong>816. Na terchovskej akcii</strong></p>' in html
    assert '<p class="article-meta"><strong>AUTOR:</strong> Piovarči, E.</p>' in html
    assert '<p class="article-meta"><strong>STRANY:</strong> s. 45 – 50 <a href="https://sss.sk/example.pdf#page=47">↗ PDF</a></p>' in html


def test_render_registers_builds_name_locality_subject_and_cave_indexes():
    articles = [
        {
            "id": 10,
            "authors": ["Novák, J.", "Kováč, P."],
            "title": "Výskum v Demänovskej doline",
            "year": 2001,
            "issue": "1",
            "pages": "12-14",
            "tags": ["hydrológia", "mapovanie jaskýň"],
            "caves": ["Demänovská jaskyňa slobody"],
            "groups": [],
            "knowledge": {
                "people": ["Ján Majko"],
                "locations": ["Demänovská dolina", "Liptov"],
            },
        },
        {
            "id": 11,
            "authors": ["Novák, J."],
            "title": "Ďalšie poznámky",
            "year": 2002,
            "issue": "2",
            "pages": "5",
            "tags": ["hydrológia"],
            "caves": ["Demänovská jaskyňa slobody"],
            "groups": [],
            "knowledge": {"locations": ["Liptov"]},
        },
    ]

    registers = exporter.render_registers(articles, markdown=False)

    assert "Menný register" in registers
    assert "J. Novák: 10 (2001, č. 1, s. 12 – 14); 11 (2002, č. 2, s. 5)" in registers
    assert "Ján Majko: 10 (2001, č. 1, s. 12 – 14)" in registers
    assert "Lokalitný register" in registers
    assert "Liptov: 10 (2001, č. 1, s. 12 – 14); 11 (2002, č. 2, s. 5)" in registers
    assert "Vecný register" in registers
    assert "hydrológia: 10 (2001, č. 1, s. 12 – 14); 11 (2002, č. 2, s. 5)" in registers
    assert "Názvový register jaskýň" in registers
    assert "Demänovská jaskyňa slobody: 10 (2001, č. 1, s. 12 – 14); 11 (2002, č. 2, s. 5)" in registers


def test_render_markdown_register_links_article_references():
    articles = [
        {
            "id": 10,
            "authors": ["Novák, J."],
            "title": "Výskum",
            "year": 2001,
            "issue": "1",
            "pages": "12-14",
            "tags": ["hydrológia"],
            "caves": ["Demänovská jaskyňa slobody"],
            "groups": [],
            "knowledge": {"locations": ["Demänovská dolina"]},
        }
    ]

    registers = exporter.render_registers(articles, markdown=True)

    assert "## Menný register" in registers
    assert "J. Novák: [10](#clanok-10) (2001, č. 1, s. 12 – 14)" in registers
    assert "## Lokalitný register" in registers
    assert "Demänovská dolina: [10](#clanok-10) (2001, č. 1, s. 12 – 14)" in registers
    assert "## Vecný register" in registers
    assert "hydrológia: [10](#clanok-10) (2001, č. 1, s. 12 – 14)" in registers
    assert "## Názvový register jaskýň" in registers
    assert "Demänovská jaskyňa slobody: [10](#clanok-10) (2001, č. 1, s. 12 – 14)" in registers


def test_render_articles_adds_markdown_anchors_for_register_links():
    article = {
        "id": 10,
        "authors": ["Novák, J."],
        "title": "Výskum",
        "year": 2001,
        "volume": "XXXII.",
        "issue": "1",
        "pages": "12-14",
        "extras": [],
        "abstract": "",
    }

    markdown = exporter.render_articles([article], markdown=True)
    html = exporter.render_html_document(markdown, "Test")

    assert '<span id="clanok-10"></span><strong>10. Výskum</strong>' in html
    assert '<strong>AUTOR:</strong> Novák, J.' in html


def test_render_articles_emphasizes_year_and_issue_in_plain_text():
    article = {
        "id": 10,
        "authors": ["Novák, J."],
        "title": "Výskum",
        "year": 2001,
        "volume": "XXXII.",
        "issue": "1",
        "pages": "12-14",
        "extras": [],
        "abstract": "",
    }

    text = exporter.render_articles([article], markdown=False)

    assert "========================================================================\nROČNÍK 2001 (XXXII.)\n========================================================================" in text
    assert "---- ČÍSLO 1 ----" in text


def test_render_html_document_styles_year_and_issue_headings():
    markdown = "### Ročník 2001 (XXXII.)\n\n#### Číslo 1\n"

    html = exporter.render_html_document(markdown, "Test")

    assert '<h3 class="volume-heading">Ročník 2001 (XXXII.)</h3>' in html
    assert '<h4 class="issue-heading">Číslo 1</h4>' in html
    assert "h3.volume-heading" in html
    assert "h4.issue-heading" in html


def test_render_contents_links_major_bibliography_sections():
    contents = exporter.render_contents(
        markdown=True,
        section_pages={
            "Zoznam článkov": 9,
            "Menný register": 159,
            "Lokalitný register": 167,
            "Vecný register": 175,
            "Súpis plánov jaskýň": 181,
            "Názvový register jaskýň": 220,
        },
    )

    assert contents.startswith("## Obsah")
    assert "[Zoznam článkov](#zoznam-clankov) - 9" in contents
    assert "[Menný register](#menny-register) - 159" in contents
    assert "[Lokalitný register](#lokalitny-register) - 167" in contents
    assert "[Vecný register](#vecny-register) - 175" in contents
    assert "[Súpis plánov jaskýň](#supis-planov-jaskyn) - 181" in contents
    assert "[Názvový register jaskýň](#nazvovy-register-jaskyn) - 220" in contents
    assert "..." not in contents


def test_render_bibliography_places_contents_before_main_sections():
    articles = [
        {
            "id": 10,
            "authors": ["Novák, J."],
            "title": "Výskum",
            "year": 2001,
            "volume": "XXXII.",
            "issue": "1",
            "pages": "12-14",
            "extras": ["1 mapa"],
            "abstract": "",
            "tags": ["hydrológia"],
            "caves": ["Demänovská jaskyňa slobody"],
            "groups": [],
            "knowledge": {"locations": ["Demänovská dolina"]},
        }
    ]

    bibliography = exporter.render_bibliography(articles, markdown=True)

    assert bibliography.index("## Obsah") < bibliography.index("## Zoznam článkov")
    assert bibliography.index("## Menný register") < bibliography.index("## Súpis plánov jaskýň")
    assert bibliography.index("## Súpis plánov jaskýň") < bibliography.index("## Názvový register jaskýň")
    assert "[Názvový register jaskýň](#nazvovy-register-jaskyn)" in bibliography
    assert "..." not in bibliography.split("## Zoznam článkov", 1)[0]


def test_render_html_document_adds_heading_ids_for_contents_links():
    markdown = (
        "# Bibliografia Spravodaja SSS\n\n"
        "## Obsah\n\n"
        "[Zoznam článkov](#zoznam-clankov) - 9\n\n"
        "## Zoznam článkov\n\n"
        "## Menný register\n"
    )

    html = exporter.render_html_document(markdown, "Test")

    assert '<h2 id="obsah">Obsah</h2>' in html
    assert '<a href="#zoznam-clankov">Zoznam článkov</a>' in html
    assert '<h2 id="zoznam-clankov">Zoznam článkov</h2>' in html
    assert '<h2 id="menny-register">Menný register</h2>' in html


def test_build_pdf_from_html_invokes_wkhtmltopdf(monkeypatch, tmp_path):
    html_path = tmp_path / "export.html"
    pdf_path = tmp_path / "export.pdf"
    html_path.write_text("<!doctype html><title>Export</title>", encoding="utf-8")
    calls = []

    monkeypatch.setattr(exporter.shutil, "which", lambda binary: f"/usr/bin/{binary}")

    def fake_run(command, capture_output, text, check):
        calls.append(command)
        pdf_path.write_bytes(b"%PDF-1.4\n")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(exporter.subprocess, "run", fake_run)

    exporter.build_pdf_from_html(html_path, pdf_path, "wkhtmltopdf")

    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert calls
    assert calls[0][0] == "/usr/bin/wkhtmltopdf"
    assert "--encoding" in calls[0]
    assert str(html_path) in calls[0]
    assert str(pdf_path) in calls[0]


def test_default_basename_uses_danko_without_duplicate_pdf_suffix():
    basename = exporter.default_basename("20260616")

    assert basename == "bibliografia_spravodaj_sss_danko_20260616"
    assert "lalkovic" not in basename
    assert not basename.endswith("_pdf")


def test_missing_pages_render_as_unverified_without_empty_s_prefix():
    article = {
        "id": 1424,
        "authors": ["Hochmuth, Z."],
        "title": "História speleopotápačských výskumov na Slovensku",
        "extras": [],
        "pages": "",
        "pdf_url": "https://sss.sk/Spravodaj_SSS_4_1998.pdf",
    }

    markdown = exporter.article_line(article, markdown=True)

    assert "**STRANY:** neoverené [↗ PDF](" in markdown
    assert "**STRANY:** s. " not in markdown


def test_parse_section_pages_from_pdftotext_output_ignores_contents_entries():
    pdf_text = (
        "Obsah\n"
        "Zoznam článkov - 2\n"
        "\f"
        "Zoznam článkov\n"
        "1. Úvodník\n"
        "\f"
        "Menný register\n"
        "A. Autor\n"
    )

    pages = exporter.parse_pdf_section_pages_from_text(pdf_text)

    assert pages == {"Zoznam článkov": 2, "Menný register": 3}
