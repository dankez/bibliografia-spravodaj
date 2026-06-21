import sys
from pathlib import Path
from types import SimpleNamespace
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_match_smopaj_caves as matcher


def test_shortlist_prefers_same_name_with_context_region():
    cave = {
        "name": "Medvedia jaskyňa",
        "slug": "medvedia-jaskyna",
        "articles": [
            {
                "id": 1,
                "title": "Medvedia jaskyňa v Jánskej doline",
                "abstract": "Poloha Medvedej jaskyne v Jánskej doline v Nízkych Tatrách.",
            }
        ],
    }
    entries = [
        {
            "cave_number": "4692",
            "official_name": "Medvedia jaskyňa",
            "names": ["Medvedia jaskyňa"],
            "geomorph_celok": "Spišsko-gemerský kras",
            "geomorph_podcelok": "Slovenský raj",
        },
        {
            "cave_number": "1810",
            "official_name": "Medvedia jaskyňa",
            "names": ["Medvedia jaskyňa", "Zimná jaskyňa"],
            "geomorph_celok": "Nízke Tatry",
            "geomorph_podcelok": "Ďumbierske Tatry",
            "geomorph_cast": "Demänovské vrchy",
        },
    ]

    candidates = matcher.shortlist_smopaj_candidates(cave, entries, max_candidates=2)

    assert candidates[0]["cave_number"] == "1810"
    assert candidates[0]["context_score"] > candidates[1]["context_score"]


def test_heuristic_decision_rejects_foreign_cave_not_in_smopaj():
    cave = {
        "name": "Jaskyňa Velika klisura",
        "slug": "jaskyna-velika-klisura",
        "articles": [
            {
                "id": 1,
                "title": "Zimná expedícia do jaskyne Velika klisura - Prokletije",
                "abstract": "Expedícia do Kosova a jaskyne Velika klisura.",
            }
        ],
    }

    decision = matcher.heuristic_decision(cave, [])

    assert decision["decision"] == "defer"
    assert "zahrani" in decision["reason"].casefold()


def test_process_caves_defers_when_selected_ai_backend_fails(tmp_path, monkeypatch):
    caves_path = tmp_path / "caves.json"
    register_path = tmp_path / "register.json"
    caves_path.write_text(
        json.dumps(
            [
                {
                    "name": "Jaskyňa Okno",
                    "slug": "jaskyna-okno",
                    "article_count": 1,
                    "articles": [
                        {
                            "id": 1,
                            "title": "Jaskyňa Okno v Demänovskej doline",
                            "abstract": "Správa o jaskyni Okno v Demänovskej doline.",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    register_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "cave_number": "1519",
                        "official_name": "Okno",
                        "names": ["Okno", "Jaskyňa Okno"],
                        "geomorph_celok": "Nízke Tatry",
                        "geomorph_podcelok": "Demänovské vrchy",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_ollama(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(matcher, "run_ollama_decision", fail_ollama)

    output = matcher.process_caves(
        SimpleNamespace(
            caves=caves_path,
            register=register_path,
            fulltext=tmp_path / "missing.jsonl",
            output=tmp_path / "out.json",
            backend="ollama",
            model="gemma4:e2b-it-qat",
            codex_model="gpt-5.5",
            codex_fallback=False,
            fulltext_context=False,
            limit=0,
            min_articles=1,
            max_candidates=12,
            min_confidence=0.82,
            timeout=1,
            slug=[],
            dry_run=True,
            resume=False,
        )
    )

    assert output["stats"]["matched"] == 0
    assert output["stats"]["deferred"] == 1
    assert output["stats"]["errors"] == 1
    assert "AI backend error" in output["deferred"][0]["reason"]


def test_process_caves_writes_checkpoint_output(tmp_path):
    caves_path = tmp_path / "caves.json"
    register_path = tmp_path / "register.json"
    output_path = tmp_path / "matches.json"
    caves_path.write_text(
        json.dumps(
            [
                {
                    "name": "Jaskyňa Okno",
                    "slug": "jaskyna-okno",
                    "article_count": 1,
                    "articles": [
                        {
                            "id": 1,
                            "title": "Jaskyňa Okno v Demänovskej doline",
                            "abstract": "Správa o jaskyni Okno v Demänovskej doline.",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    register_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "cave_number": "1519",
                        "official_name": "Okno",
                        "names": ["Okno", "Jaskyňa Okno"],
                        "geomorph_celok": "Nízke Tatry",
                        "geomorph_podcelok": "Demänovské vrchy",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    matcher.process_caves(
        SimpleNamespace(
            caves=caves_path,
            register=register_path,
            fulltext=tmp_path / "missing.jsonl",
            output=output_path,
            backend="heuristic",
            model="gemma4:e2b-it-qat",
            codex_model="gpt-5.5",
            codex_fallback=False,
            fulltext_context=False,
            limit=0,
            min_articles=1,
            max_candidates=12,
            min_confidence=0.82,
            timeout=1,
            slug=[],
            dry_run=False,
            resume=False,
        )
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["stats"]["selected"] == 1
    assert saved["matches"][0]["cave_slug"] == "jaskyna-okno"


def test_process_caves_resume_preserves_existing_output(tmp_path):
    caves_path = tmp_path / "caves.json"
    register_path = tmp_path / "register.json"
    output_path = tmp_path / "matches.json"
    caves_path.write_text(
        json.dumps(
            [
                {
                    "name": "Jaskyňa Okno",
                    "slug": "jaskyna-okno",
                    "article_count": 1,
                    "articles": [{"id": 1, "title": "Jaskyňa Okno", "abstract": ""}],
                },
                {
                    "name": "Snežná diera",
                    "slug": "snezna-diera",
                    "article_count": 1,
                    "articles": [{"id": 2, "title": "Snežná diera", "abstract": ""}],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    register_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "cave_number": "3004",
                        "official_name": "Snežná diera",
                        "names": ["Snežná diera"],
                        "geomorph_celok": "Slovenský kras",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path.write_text(
        json.dumps(
            {
                "matches": [{"cave_slug": "jaskyna-okno", "cave_number": "1519"}],
                "deferred": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    matcher.process_caves(
        SimpleNamespace(
            caves=caves_path,
            register=register_path,
            fulltext=tmp_path / "missing.jsonl",
            output=output_path,
            backend="heuristic",
            model="gemma4:e2b-it-qat",
            codex_model="gpt-5.5",
            codex_fallback=False,
            fulltext_context=False,
            limit=0,
            min_articles=1,
            max_candidates=12,
            min_confidence=0.82,
            timeout=1,
            slug=[],
            dry_run=False,
            resume=True,
        )
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["cave_slug"] for item in saved["matches"]] == ["jaskyna-okno", "snezna-diera"]
    assert saved["stats"]["resumed_matches"] == 1
