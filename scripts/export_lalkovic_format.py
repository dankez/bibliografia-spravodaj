#!/usr/bin/env python3
"""
Export Spravodaj SSS bibliography in a readable Danko textual format.

The text export keeps the historic bibliography rhythm:

Ročník 1970 (I.)
Číslo 1
1. Názov
   Autor: Autor
   Strany: s. 1 – 3
Vecná anotácia

The Markdown export keeps the same shape but adds online PDF links.
"""

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import unicodedata
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
EXPORT_DIR = BASE_DIR / "data" / "exports"
ONLINE_PDF_LABEL = "↗ PDF"
MAPS_AND_PLANS_TITLE = "Súpis plánov jaskýň"
DEFAULT_BASENAME_PREFIX = "bibliografia_spravodaj_sss_danko"
PDF_COVER_PAGE_OFFSET_YEAR_FROM = 2024
PDF_COVER_PAGE_OFFSET = 2
CONTENT_SECTIONS = [
    ("Zoznam článkov", "zoznam-clankov"),
    ("Menný register", "menny-register"),
    ("Lokalitný register", "lokalitny-register"),
    ("Vecný register", "vecny-register"),
    (MAPS_AND_PLANS_TITLE, "supis-planov-jaskyn"),
    ("Názvový register jaskýň", "nazvovy-register-jaskyn"),
]
HEADING_IDS = {title: anchor for title, anchor in CONTENT_SECTIONS}
HEADING_IDS["Obsah"] = "obsah"


def page_start(pages: str) -> str:
    match = re.match(r"\s*(\d+)", str(pages or ""))
    return match.group(1) if match else "1"


def pdf_page_start(article: dict) -> str:
    return str(article.get("pdf_page_start") or page_start(article.get("pages", "")))


def pdf_link_page(article: dict) -> str:
    try:
        page = int(pdf_page_start(article))
    except (TypeError, ValueError):
        return ""
    if int(article.get("year") or 0) >= PDF_COVER_PAGE_OFFSET_YEAR_FROM:
        page += PDF_COVER_PAGE_OFFSET
    return str(page)


def default_basename(stamp: str) -> str:
    return f"{DEFAULT_BASENAME_PREFIX}_{stamp}"


def markdown_pdf_link(url: str) -> str:
    return f"[{ONLINE_PDF_LABEL}]({url})"


def slugify_heading(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")


def heading_id(title: str) -> str:
    return HEADING_IDS.get(title, "")


def render_heading(level: int, title: str, css_class: str | None = None) -> str:
    anchor = heading_id(title)
    id_attr = f' id="{html.escape(anchor, quote=True)}"' if anchor else ""
    class_attr = f' class="{html.escape(css_class, quote=True)}"' if css_class else ""
    return f"<h{level}{id_attr}{class_attr}>{html.escape(title)}</h{level}>"


def content_line(
    title: str,
    anchor: str,
    markdown: bool = False,
    section_pages: dict[str, int] | None = None,
) -> str:
    label = f"[{title}](#{anchor})" if markdown else title
    page = (section_pages or {}).get(title)
    return f"{label} - {page}" if page else label


def render_contents(markdown: bool = False, section_pages: dict[str, int] | None = None) -> str:
    title = "## Obsah" if markdown else "Obsah"
    lines = [title, ""]
    lines.extend(
        content_line(section_title, anchor, markdown=markdown, section_pages=section_pages)
        for section_title, anchor in CONTENT_SECTIONS
    )
    return "\n".join(lines).rstrip() + "\n"


def format_pages(pages: str) -> str:
    value = str(pages or "").strip()
    return value.replace("-", " – ")


def pages_label(pages: str) -> str:
    formatted = format_pages(pages)
    return f"s. {formatted}" if formatted else "neoverené"


def authors_label(authors: list[str]) -> str:
    if not authors:
        return "Anonymus"
    return ", ".join(authors)


def article_anchor(article: dict) -> str:
    return f"clanok-{article['id']}"


def markdown_article_anchor(article: dict) -> str:
    return f'<span id="{article_anchor(article)}"></span>'


def article_line(article: dict, markdown: bool = False) -> str:
    authors = authors_label(article.get("authors", []))
    extras = article.get("extras") or []
    extras_part = ", ".join(extras)
    title = article.get("title", "")
    pages = pages_label(article.get("pages", ""))
    if markdown:
        pdf_link = ""
        if article.get("pdf_url"):
            url = f"{article['pdf_url']}#page={pdf_link_page(article)}"
            pdf_link = f" {markdown_pdf_link(url)}"
        lines = [
            f"{markdown_article_anchor(article)}**{article['id']}. {title}**",
            f"**AUTOR:** {authors}  ",
            f"**STRANY:** {pages}{pdf_link}  ",
        ]
        if extras_part:
            lines.append(f"**POZNÁMKY:** {extras_part}  ")
        return "\n".join(lines)

    lines = [
        f"{article['id']}. {title}",
        f"     AUTOR: {authors}",
        f"     STRANY: {pages}",
    ]
    if extras_part:
        lines.append(f"     POZNÁMKY: {extras_part}")
    return "\n".join(lines)


def clean_register_term(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = "".join(
        char
        for char in text
        if unicodedata.category(char) not in {"So", "Sk"} and char != "\ufe0f"
    )
    return re.sub(r"\s+", " ", text).strip(" ,;")


def author_register_name(author: str) -> str:
    author = clean_register_term(author)
    if "," not in author:
        return author
    surname, given = [part.strip() for part in author.split(",", 1)]
    if not surname or not given:
        return author
    return f"{given} {surname}"


def knowledge_values(article: dict, key: str) -> list[str]:
    knowledge = article.get("knowledge") or {}
    values = knowledge.get(key) or []
    if isinstance(values, list):
        return [str(value) for value in values]
    return [str(values)]


def wikidata_names(article: dict) -> list[str]:
    names = []
    for item in article.get("wikidata") or []:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def name_register_terms(article: dict) -> list[str]:
    terms = [author_register_name(author) for author in article.get("authors") or []]
    terms.extend(knowledge_values(article, "people"))
    return terms


def locality_register_terms(article: dict) -> list[str]:
    return knowledge_values(article, "locations")


def subject_register_terms(article: dict) -> list[str]:
    terms = list(article.get("tags") or [])
    terms.extend(knowledge_values(article, "keywords"))
    return terms


def cave_register_terms(article: dict) -> list[str]:
    terms = list(article.get("caves") or [])
    terms.extend(wikidata_names(article))
    return terms


def register_sort_key(value: str) -> str:
    return value.casefold()


def register_reference(article: dict, markdown: bool = False) -> str:
    year = article.get("year", "")
    issue = article.get("issue", "")
    pages = format_pages(article.get("pages", ""))
    suffix = f"({year}, č. {issue}, s. {pages})"
    if markdown:
        return f"[{article['id']}](#{article_anchor(article)}) {suffix}"
    return f"{article['id']} {suffix}"


def build_register_index(articles: list[dict], term_getter) -> dict[str, list[dict]]:
    index: dict[str, dict[int, dict]] = defaultdict(dict)
    for article in articles:
        for raw_term in term_getter(article):
            term = clean_register_term(raw_term)
            if term:
                index[term][article["id"]] = article
    return {
        term: sorted(article_map.values(), key=lambda item: item["id"])
        for term, article_map in index.items()
    }


def render_register_section(title: str, index: dict[str, list[dict]], markdown: bool = False) -> str:
    heading = f"## {title}" if markdown else title
    lines = [heading, ""]
    if not index:
        lines.append("(bez záznamov)")
        return "\n".join(lines).rstrip() + "\n"

    for term in sorted(index.keys(), key=register_sort_key):
        refs = "; ".join(register_reference(article, markdown=markdown) for article in index[term])
        lines.append(f"{term}: {refs}")
    return "\n".join(lines).rstrip() + "\n"


def register_sections(articles: list[dict]) -> list[tuple[str, dict[str, list[dict]]]]:
    return [
        ("Menný register", build_register_index(articles, name_register_terms)),
        ("Lokalitný register", build_register_index(articles, locality_register_terms)),
        ("Vecný register", build_register_index(articles, subject_register_terms)),
        ("Názvový register jaskýň", build_register_index(articles, cave_register_terms)),
    ]


def render_registers(articles: list[dict], markdown: bool = False, titles: set[str] | None = None) -> str:
    sections = register_sections(articles)
    if titles is not None:
        sections = [(title, index) for title, index in sections if title in titles]
    return "\n\n".join(
        render_register_section(title, index, markdown=markdown).rstrip()
        for title, index in sections
    ) + "\n"


def issue_sort_key(issue: str) -> tuple[int, str]:
    text = str(issue)
    match = re.match(r"(\d+)", text)
    if match:
        return int(match.group(1)), text
    return 999, text


def plain_rule(char: str = "=", width: int = 72) -> str:
    return char * width


def plain_volume_heading(year: int, volume: str) -> str:
    volume_part = f" ({volume})" if volume else ""
    return "\n".join([plain_rule("="), f"ROČNÍK {year}{volume_part}", plain_rule("=")])


def plain_issue_heading(issue: str) -> str:
    return f"---- ČÍSLO {issue} ----"


def has_map_or_plan(article: dict) -> bool:
    if article.get("has_map_plan") is True:
        return True
    detected = article.get("detected_features", {}).get("map_plan")
    if isinstance(detected, dict) and detected.get("present") is True:
        return True
    tags = [str(tag).casefold() for tag in article.get("tags") or []]
    if "mapa/plán" in tags:
        return True
    text = " ".join(article.get("extras") or []) + " " + article.get("title", "")
    lowered = text.lower()
    return "pl. j." in lowered or "map" in lowered or "plán" in lowered or "plan" in lowered


def render_articles(articles: list[dict], markdown: bool = False) -> str:
    grouped: dict[tuple[int, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for article in articles:
        grouped[(article.get("year"), article.get("volume", ""))][str(article.get("issue", ""))].append(article)

    lines: list[str] = []
    title = "## Zoznam článkov" if markdown else "Zoznam článkov"
    lines.extend([title, ""])

    for (year, volume) in sorted(grouped.keys()):
        volume_part = f" ({volume})" if volume else ""
        heading = f"### Ročník {year}{volume_part}" if markdown else plain_volume_heading(year, volume)
        lines.extend([heading, ""])
        issues = grouped[(year, volume)]
        for issue in sorted(issues.keys(), key=issue_sort_key):
            issue_heading = f"#### Číslo {issue}" if markdown else plain_issue_heading(issue)
            lines.extend([issue_heading, ""])
            for article in sorted(issues[issue], key=lambda item: item["id"]):
                lines.append(article_line(article, markdown=markdown))
                abstract = (article.get("abstract") or "").strip()
                if abstract:
                    lines.append(abstract)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_maps_and_plans(articles: list[dict], markdown: bool = False) -> str:
    mapped = [article for article in articles if has_map_or_plan(article)]
    lines: list[str] = []
    title = f"## {MAPS_AND_PLANS_TITLE}" if markdown else MAPS_AND_PLANS_TITLE
    lines.extend([title, ""])
    for index, article in enumerate(sorted(mapped, key=lambda item: (item.get("year", 0), item["id"])), start=1):
        extras = ", ".join(article.get("extras") or [])
        where = f"{article.get('year')}, č. {article.get('issue')}, s. {format_pages(article.get('pages', ''))}"
        line = f"{index}. {article.get('title', '')} ({where})"
        if extras:
            line += f" - {extras}"
        if markdown and article.get("pdf_url"):
            url = f"{article['pdf_url']}#page={pdf_link_page(article)}"
            line += f" {markdown_pdf_link(url)}"
        lines.append(line)
        authors = authors_label(article.get("authors", []))
        lines.append(f"Súvisiaci článok: {authors}: {article.get('title', '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_bibliography(
    articles: list[dict],
    markdown: bool = False,
    section_pages: dict[str, int] | None = None,
) -> str:
    title = "# Bibliografia Spravodaja SSS" if markdown else "Bibliografia Spravodaja SSS"
    name_locality_subject = {"Menný register", "Lokalitný register", "Vecný register"}
    cave_register = {"Názvový register jaskýň"}
    return (
        title
        + "\n\n"
        + render_contents(markdown=markdown, section_pages=section_pages)
        + "\n"
        + render_articles(articles, markdown=markdown)
        + "\n"
        + render_registers(articles, markdown=markdown, titles=name_locality_subject)
        + "\n"
        + render_maps_and_plans(articles, markdown=markdown)
        + "\n"
        + render_registers(articles, markdown=markdown, titles=cave_register)
    )


def render_markdown_line(line: str) -> str:
    text = line.rstrip()
    if not text:
        return ""
    if text.startswith("# "):
        title = text[2:].strip()
        return render_heading(1, title)
    if text.startswith("## "):
        title = text[3:].strip()
        return render_heading(2, title)
    if text.startswith("### "):
        title = text[4:].strip()
        css_class = "volume-heading" if title.startswith("Ročník ") else None
        return render_heading(3, title, css_class=css_class)
    if text.startswith("#### "):
        title = text[5:].strip()
        css_class = "issue-heading" if title.startswith("Číslo ") else None
        return render_heading(4, title, css_class=css_class)

    anchor = ""
    anchor_match = re.match(r'^<span id="([A-Za-z0-9_-]+)"></span>(.*)$', text)
    if anchor_match:
        anchor = f'<span id="{html.escape(anchor_match.group(1), quote=True)}"></span>'
        text = anchor_match.group(2)

    css_classes = []
    if re.match(r"^\*\*\d+\. ", text):
        css_classes.append("article-title")
    if re.match(r"^\*\*(AUTOR|STRANY|POZNÁMKY):\*\*", text):
        css_classes.append("article-meta")
    if text.startswith("Online: "):
        css_classes.append("online")

    escaped = html.escape(text).replace("  ", " ")
    escaped = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda match: f"<strong>{match.group(1)}</strong>",
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>',
        escaped,
    )
    css_class = f' class="{" ".join(css_classes)}"' if css_classes else ""
    return f"<p{css_class}>{anchor}{escaped}</p>"


def render_html_document(markdown_text: str, title: str) -> str:
    body = "\n".join(
        rendered for line in markdown_text.splitlines() if (rendered := render_markdown_line(line))
    )
    return f"""<!doctype html>
<html lang="sk">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    @page {{ size: A4; margin: 16mm 14mm 18mm; }}
    html {{
      background: white;
    }}
    body {{
      background: white;
      color: rgb(36, 23, 21);
      font-family: "DejaVu Serif", Georgia, serif;
      font-size: 10.5pt;
      line-height: 1.42;
    }}
    h1 {{
      border-bottom: 2px solid rgb(206, 61, 59);
      color: rgb(206, 61, 59);
      font-size: 20pt;
      margin: 0 0 14mm;
      padding-bottom: 5mm;
    }}
    h2 {{
      border-bottom: 1px solid rgb(160, 163, 165);
      color: rgb(206, 61, 59);
      font-size: 15pt;
      margin: 9mm 0 4mm;
      padding-bottom: 2mm;
      page-break-after: avoid;
    }}
    h3 {{
      color: rgb(204, 159, 88);
      font-size: 12pt;
      margin: 5mm 0 2mm;
      page-break-after: avoid;
    }}
    h3.volume-heading {{
      background: white;
      border-left: 4mm solid rgb(206, 61, 59);
      border-top: 1px solid rgb(135, 143, 159);
      color: rgb(206, 61, 59);
      font-family: "DejaVu Sans", Arial, sans-serif;
      font-size: 13pt;
      margin: 8mm 0 3mm;
      padding: 2.5mm 3mm;
      text-transform: uppercase;
    }}
    h4 {{
      color: rgb(206, 61, 59);
      font-size: 10.5pt;
      margin: 3.5mm 0 2mm;
      page-break-after: avoid;
    }}
    h4.issue-heading {{
      background: white;
      border-bottom: 1px solid rgb(160, 163, 165);
      border-top: 1px solid rgb(160, 163, 165);
      color: rgb(204, 159, 88);
      display: inline-block;
      font-family: "DejaVu Sans", Arial, sans-serif;
      font-size: 10pt;
      margin: 1.5mm 0 2.5mm;
      padding: 1.2mm 3mm;
      text-transform: uppercase;
    }}
    p {{
      margin: 0 0 2.5mm;
      orphans: 2;
      widows: 2;
    }}
    p.article-title {{
      border-top: 1px solid rgb(160, 163, 165);
      color: rgb(36, 23, 21);
      font-size: 11.5pt;
      margin: 4mm 0 1mm;
      padding-top: 2mm;
      page-break-after: avoid;
    }}
    p.article-title strong {{
      color: rgb(206, 61, 59);
    }}
    p.article-meta {{
      color: rgb(78, 72, 71);
      font-size: 9.5pt;
      margin: 0 0 0.8mm 5mm;
    }}
    p.article-meta strong {{
      color: rgb(204, 159, 88);
      font-family: "DejaVu Sans", Arial, sans-serif;
      font-size: 8.5pt;
      text-transform: uppercase;
    }}
    p.online {{
      color: rgb(206, 61, 59);
      font-size: 9pt;
      margin: 1mm 0 4mm 5mm;
    }}
    a {{ color: rgb(206, 61, 59); text-decoration: none; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def build_pdf_from_html(html_path: Path, pdf_path: Path, pdf_engine: str = "wkhtmltopdf") -> None:
    engine_path = shutil.which(pdf_engine)
    if not engine_path:
        raise RuntimeError(f"PDF engine not found on PATH: {pdf_engine}")
    command = [
        engine_path,
        "--encoding",
        "utf-8",
        "--page-size",
        "A4",
        "--margin-top",
        "16mm",
        "--margin-bottom",
        "18mm",
        "--margin-left",
        "14mm",
        "--margin-right",
        "14mm",
        "--footer-center",
        "[page]",
        "--footer-font-size",
        "8",
        str(html_path),
        str(pdf_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "wkhtmltopdf failed")


def parse_pdf_section_pages_from_text(pdf_text: str) -> dict[str, int]:
    pages: dict[str, int] = {}
    wanted = {title for title, _ in CONTENT_SECTIONS}
    wanted.add("Obsah")
    for page_number, page_text in enumerate(pdf_text.split("\f"), start=1):
        for raw_line in page_text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line in wanted and line not in pages:
                pages[line] = page_number
    pages.pop("Obsah", None)
    return pages


def detect_pdf_section_pages(pdf_path: Path) -> dict[str, int]:
    if not shutil.which("pdftotext"):
        return {}
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    return parse_pdf_section_pages_from_text(result.stdout)


def write_exports(
    articles: list[dict],
    txt_path: Path,
    md_path: Path,
    html_path: Path | None = None,
    section_pages: dict[str, int] | None = None,
) -> tuple[str, str]:
    text_output = render_bibliography(articles, markdown=False, section_pages=section_pages)
    markdown_output = render_bibliography(articles, markdown=True, section_pages=section_pages)
    txt_path.write_text(text_output, encoding="utf-8")
    md_path.write_text(markdown_output, encoding="utf-8")
    if html_path:
        html_path.write_text(render_html_document(markdown_output, "Bibliografia Spravodaja SSS"), encoding="utf-8")
    return text_output, markdown_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bibliography in readable Danko TXT, Markdown, HTML and PDF.")
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Path to article JSON database.")
    parser.add_argument("--output-dir", default=str(EXPORT_DIR), help="Directory for export files.")
    parser.add_argument("--basename", default=None, help="Output basename without extension.")
    parser.add_argument("--pdf", action="store_true", help="Also create HTML and PDF export using wkhtmltopdf.")
    parser.add_argument("--pdf-engine", default="wkhtmltopdf", help="PDF engine command, defaults to wkhtmltopdf.")
    args = parser.parse_args()

    articles_path = Path(args.articles)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with articles_path.open("r", encoding="utf-8") as handle:
        articles = json.load(handle)

    stamp = dt.datetime.now().strftime("%Y%m%d")
    basename = args.basename or default_basename(stamp)

    txt_path = output_dir / f"{basename}.txt"
    md_path = output_dir / f"{basename}.md"
    if args.pdf:
        html_path = output_dir / f"{basename}.html"
        pdf_path = output_dir / f"{basename}.pdf"
        section_pages: dict[str, int] | None = None
        for _ in range(3):
            write_exports(articles, txt_path, md_path, html_path=html_path, section_pages=section_pages)
            build_pdf_from_html(html_path, pdf_path, args.pdf_engine)
            detected_pages = detect_pdf_section_pages(pdf_path)
            if not detected_pages or detected_pages == section_pages:
                break
            section_pages = detected_pages
        if section_pages:
            write_exports(articles, txt_path, md_path, html_path=html_path, section_pages=section_pages)
            build_pdf_from_html(html_path, pdf_path, args.pdf_engine)
        print(f"Wrote {txt_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {html_path}")
        print(f"Wrote {pdf_path}")
    else:
        write_exports(articles, txt_path, md_path)
        print(f"Wrote {txt_path}")
        print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
