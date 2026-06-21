#!/usr/bin/env python3
"""Import preview records from the newest Aragonit and Slovensky kras issues.

This is an intentionally small, reviewable bridge import. It adds article-level
records from the table of contents of the two newest checked issues so the web UI
can be tested with multiple journals before building the full importer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_FRONTEND_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
CREATED_BY = "codex_journal_sample_import"
SOURCE_ISSUE_KEYS = {"aragonit:29_2", "slovensky_kras:61_2023_2"}


ISSUES: list[dict[str, Any]] = [
    {
        "source_issue_key": "aragonit:29_2",
        "journal_id": "aragonit",
        "journal_title": "Aragonit",
        "journal_short_title": "Aragonit",
        "year": 2024,
        "volume": "29",
        "issue": "2",
        "pdf_url": "http://www.ssj.sk/user_files/Aragon_29_2_web.pdf",
        "pdf_page_delta": -46,
        "tags": ["Aragonit", "Výskum krasu a jaskýň"],
        "entries": [
            {
                "authors": ["Littva, J.", "Bella, P.", "Herich, P.", "Soták, J.", "Danielčáková, I."],
                "title": "Jaskyňa vytvorená na rozhraní karbonatických zlepencov a slieňovcov, Zuberecká brázda na úpätí Západných Tatier",
                "page": 51,
                "caves": ["Zlepencová jaskyňa"],
            },
            {
                "authors": ["Pristašová, L."],
                "title": "Teplota vzduchu v Malužinskej a Modrej jaskyni v Nízkych Tatrách",
                "page": 61,
                "caves": ["Malužinská jaskyňa", "Modrá jaskyňa"],
            },
            {
                "authors": ["Višňovská, Z.", "Pribišová, D.", "Manko, P.", "Rendoš, M."],
                "title": "Prvé poznatky o akvatickej faune jaskynného systému Diablova diera v pohorí Branisko",
                "page": 68,
                "caves": ["Diablova diera"],
            },
            {
                "authors": ["Littva, J."],
                "title": "Odber vzoriek materskej horniny v jaskyni - odporúčania na zníženie vplyvu na morfológiu skalných stien",
                "page": 84,
                "caves": [],
            },
            {
                "authors": ["Bella, P."],
                "title": "15. vedecká konferencia \"Výskum, využívanie a ochrana jaskýň\"",
                "page": 89,
                "caves": [],
            },
            {
                "authors": ["Herich, P."],
                "title": "NSS Convention 2024 - výročná konferencia Národnej speleologickej spoločnosti USA v Tennessee a poznávacia cesta po krase východnej časti Spojených štátov",
                "page": 91,
                "caves": [],
            },
            {
                "authors": ["Bella, P.", "Gažík, P."],
                "title": "Mulu 2024 - konferencia Medzinárodnej asociácie sprístupnených jaskýň",
                "page": 93,
                "caves": [],
            },
            {
                "authors": ["Gaál, Ľ."],
                "title": "V ktorej jaskyni bola Brožkova pustovňa?",
                "page": 96,
                "caves": [],
            },
            {
                "authors": [
                    "Krasnocvetová, M.",
                    "Dušeková, L.",
                    "Haviarová, D.",
                    "Littva, J.",
                    "Melega, M.",
                    "Papáč, V.",
                    "Pristašová, L.",
                    "Višňovská, Z.",
                ],
                "title": "Projekt zameraný na ochranu a starostlivosť o nesprístupnené jaskyne",
                "page": 98,
                "caves": [],
            },
            {
                "authors": ["Drobúlová, M.", "Herich, P.", "Labaška, P.", "Stankoviansky, P."],
                "title": "Projekt inovácie a ochrany Demänovských jaskýň a jaskyne Zápoľná",
                "page": 100,
                "caves": ["Demänovské jaskyne", "Zápoľná jaskyňa"],
            },
            {
                "authors": ["Kudla, M.", "Gažík, P."],
                "title": "K 70. výročiu objavenia Ochtinskej aragonitovej jaskyne",
                "page": 101,
                "caves": ["Ochtinská aragonitová jaskyňa"],
            },
            {
                "authors": ["Kudla, M."],
                "title": "Demänovská jaskyňa slobody sprístupnená pred 100 rokmi",
                "page": 102,
                "caves": ["Demänovská jaskyňa slobody"],
            },
        ],
    },
    {
        "source_issue_key": "slovensky_kras:61_2023_2",
        "journal_id": "slovensky_kras",
        "journal_title": "Slovenský kras",
        "journal_short_title": "Slovenský kras",
        "year": 2023,
        "volume": "61",
        "issue": "2",
        "pdf_url": "https://www.smopaj.sk/sk/documentloader.php?id=5336&filename=zborník 61_2_2023.pdf",
        "pdf_page_delta": -96,
        "tags": ["Slovenský kras"],
        "entries": [
            {
                "authors": ["Čeklovský, T.", "Farkašovská, E.", "Obuch, J."],
                "title": "Fosílne, subfosílne až recentné nálezy stavovcov (Vertebrata) z jaskynných lokalít na Slovensku",
                "page": 101,
                "caves": [],
            },
            {
                "authors": ["Bella, P.", "Holúbek, P.", "Littva, J."],
                "title": "Bobrie nory v ústí Váhu do Liptovskej Mary",
                "page": 119,
                "caves": [],
            },
            {
                "authors": ["Obuch, J."],
                "title": "Potrava sovy obyčajnej (Strix aluco) v jaskyni Maštaľná na Plešivskej planine",
                "page": 129,
                "caves": ["Maštaľná jaskyňa"],
            },
            {
                "authors": ["Jerg, Z."],
                "title": "Rukopisné mapy v Maďarskom národnom archíve a jaskyne Slovenského krasu",
                "page": 139,
                "caves": [],
                "has_map_plan": True,
            },
            {
                "authors": ["Jerg, Z."],
                "title": "Nové poznatky z najstaršej histórie Kysackej jaskyne",
                "page": 159,
                "caves": ["Kysacká jaskyňa"],
            },
            {
                "authors": ["Bosák, P."],
                "title": "Vzpomínka na Andreje Kranjce",
                "page": 175,
                "caves": [],
            },
            {
                "authors": ["Jerg, Z."],
                "title": "Székely Kinga: RAISZ KERESZTÉLY földmérő - a Baradla kutatója",
                "page": 183,
                "end_page": 191,
                "caves": ["Baradla"],
            },
        ],
    },
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def issue_page_ranges(entries: list[dict[str, Any]]) -> list[tuple[int, int]]:
    starts = [int(entry["page"]) for entry in entries]
    ranges: list[tuple[int, int]] = []
    for index, entry in enumerate(entries):
        start = starts[index]
        if entry.get("end_page"):
            end = int(entry["end_page"])
        elif index + 1 < len(starts):
            end = starts[index + 1] - 1
        else:
            end = start
        ranges.append((start, end))
    return ranges


def page_label(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def article_abstract(issue: dict[str, Any], entry: dict[str, Any]) -> str:
    return ""


def build_sample_issue_articles(start_id: int = 1, created_at: str | None = None) -> list[dict[str, Any]]:
    created_at = created_at or utc_now()
    articles: list[dict[str, Any]] = []
    next_id = start_id
    for issue in ISSUES:
        ranges = issue_page_ranges(issue["entries"])
        for entry, (start, end) in zip(issue["entries"], ranges, strict=True):
            physical_start = max(1, start + int(issue["pdf_page_delta"]))
            physical_end = max(physical_start, end + int(issue["pdf_page_delta"]))
            tags = list(dict.fromkeys([*issue["tags"], "Speleológia"]))
            article = {
                "id": next_id,
                "authors": entry["authors"],
                "title": entry["title"],
                "pages": page_label(start, end),
                "extras": [],
                "year": issue["year"],
                "volume": issue["volume"],
                "issue": issue["issue"],
                "abstract": article_abstract(issue, entry),
                "abstract_source": "missing",
                "pdf_url": issue["pdf_url"],
                "journal_id": issue["journal_id"],
                "journal_title": issue["journal_title"],
                "journal_short_title": issue["journal_short_title"],
                "source_issue_key": issue["source_issue_key"],
                "created_by": CREATED_BY,
                "created_at": created_at,
                "pdf_page_start": physical_start,
                "pdf_page_end": physical_end,
                "pdf_page_offset": 0,
                "caves": entry.get("caves", []),
                "caves_verified": bool(entry.get("caves")),
                "tags": tags,
                "groups": [],
                "wikidata": [],
            }
            if entry.get("has_map_plan"):
                article["has_map_plan"] = True
                article["map_plan_pages"] = [physical_start]
                article["detected_features"] = {
                    "map_plan": {
                        "present": True,
                        "score": 0.7,
                        "confidence": "medium",
                        "pages": [physical_start],
                        "evidence": ["title: rukopisné mapy"],
                        "methods": ["toc_keyword"],
                        "updated_at": created_at,
                    }
                }
            articles.append(article)
            next_id += 1
    return articles


def merge_sample_articles(existing_articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [
        article
        for article in existing_articles
        if not (
            article.get("created_by") == CREATED_BY
            and str(article.get("source_issue_key") or "") in SOURCE_ISSUE_KEYS
        )
    ]
    max_id = max((int(article.get("id") or 0) for article in kept), default=0)
    imported = build_sample_issue_articles(start_id=max_id + 1)
    return [*kept, *imported]


def read_articles(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_articles(path: Path, articles: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND_PATH)
    parser.add_argument("--check", action="store_true", help="Print planned summary without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = read_articles(args.articles)
    merged = merge_sample_articles(articles)
    imported_count = sum(1 for article in merged if article.get("created_by") == CREATED_BY)
    summary = {
        "source": str(args.articles),
        "articles_before": len(articles),
        "articles_after": len(merged),
        "sample_articles": imported_count,
        "sample_issue_keys": sorted(SOURCE_ISSUE_KEYS),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.check:
        return 0
    write_articles(args.articles, merged)
    write_articles(args.frontend, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
