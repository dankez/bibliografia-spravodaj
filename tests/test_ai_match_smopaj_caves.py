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


def test_heuristic_decision_rejects_generic_plural_cave_cards():
    cave = {
        "name": "Pseudokrasové jaskyne",
        "slug": "pseudokrasove-jaskyne",
        "article_count": 2,
        "articles": [
            {
                "id": 1,
                "title": "Pseudokrasové jaskyne pohoria Burda",
                "abstract": "Prehľad viacerých pseudokrasových jaskýň a puklinových priestorov.",
            }
        ],
    }
    candidates = [
        {
            "cave_number": "848",
            "official_name": "Pseudokrasová jaskyňa",
            "names": ["Pseudokrasová jaskyňa"],
            "geomorph_celok": "Biele Karpaty",
            "name_score": 0.97,
            "context_score": 0.0,
            "score": 0.97,
        }
    ]

    decision = matcher.heuristic_decision(cave, candidates)

    assert decision["decision"] == "defer"
    assert "generick" in decision["reason"].casefold() or "skupin" in decision["reason"].casefold()


def test_heuristic_decision_rejects_ambiguous_same_name_without_area_evidence():
    cave = {
        "name": "Diablova diera",
        "slug": "diablova-diera",
        "article_count": 4,
        "articles": [{"id": 1, "title": "Diablova diera", "abstract": "Správa o jaskynnom systéme Diablova diera."}],
    }
    candidates = [
        {
            "cave_number": "81",
            "official_name": "Diablova diera",
            "names": ["Diablova diera"],
            "geomorph_celok": "Branisko",
            "geomorph_podcelok": "Smrekovica",
            "name_score": 1.0,
            "context_score": 0.0,
            "score": 1.0,
        },
        {
            "cave_number": "82",
            "official_name": "Diablova diera",
            "names": ["Diablova diera"],
            "geomorph_celok": "Branisko",
            "geomorph_podcelok": "Smrekovica",
            "name_score": 1.0,
            "context_score": 0.0,
            "score": 1.0,
        },
    ]

    decision = matcher.heuristic_decision(cave, candidates)

    assert decision["decision"] == "defer"
    assert "viac" in decision["reason"].casefold() or "nejednoznac" in matcher.normalize(decision["reason"])


def test_audit_decision_rejects_foreign_or_generic_defer():
    cave = {
        "name": "Jaskyňa Velika klisura",
        "slug": "jaskyna-velika-klisura",
        "article_count": 1,
        "articles": [
            {
                "id": 1,
                "title": "Zimná expedícia do jaskyne Velika klisura - Prokletije",
                "abstract": "Expedícia do Kosova a jaskyne Velika klisura.",
            }
        ],
    }
    decision = matcher.heuristic_decision(cave, [])

    audit = matcher.audit_decision(cave, [], decision, backend="heuristic", model="test")

    assert audit["status"] == "rejected"
    assert audit["allow_match"] is False
    assert "zahrani" in audit["reason"].casefold()


def test_audit_decision_downgrades_ambiguous_same_name_match():
    cave = {
        "name": "Diablova diera",
        "slug": "diablova-diera",
        "article_count": 2,
        "articles": [{"id": 1, "title": "Diablova diera v pohorí Branisko", "abstract": "Branisko, Smrekovica."}],
    }
    candidates = [
        {
            "cave_number": "81",
            "official_name": "Diablova diera",
            "names": ["Diablova diera"],
            "geomorph_celok": "Branisko",
            "geomorph_podcelok": "Smrekovica",
            "name_score": 1.0,
            "context_score": 1.0,
            "score": 1.12,
        },
        {
            "cave_number": "82",
            "official_name": "Diablova diera",
            "names": ["Diablova diera"],
            "geomorph_celok": "Branisko",
            "geomorph_podcelok": "Smrekovica",
            "name_score": 1.0,
            "context_score": 1.0,
            "score": 1.12,
        },
    ]
    decision = {
        "decision": "match",
        "cave_number": "81",
        "confidence": 0.9,
        "reason": "názov a kontext sedia",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="heuristic", model="test")

    assert audit["status"] == "uncertain"
    assert audit["allow_match"] is False
    assert "viac" in audit["reason"].casefold() or "nejednoznac" in matcher.normalize(audit["reason"])


def test_audit_decision_downgrades_same_name_candidates_even_with_context_margin():
    cave = {
        "name": "Zbojnícka diera",
        "slug": "zbojnicka-diera",
        "article_count": 2,
        "articles": [{"id": 1, "title": "Zbojnícka diera v Čergove", "abstract": "Čergovský kras."}],
    }
    candidates = [
        {
            "cave_number": "211",
            "official_name": "Zbojnícka diera",
            "names": ["Lipovce", "Zbojnícka diera"],
            "geomorph_celok": "Čergov",
            "name_score": 1.0,
            "context_score": 5.0,
            "score": 1.48,
        },
        {
            "cave_number": "867",
            "official_name": "Zbojnícka diera",
            "names": ["Zbojnícka diera"],
            "geomorph_celok": "Levočské vrchy",
            "name_score": 1.0,
            "context_score": 0.0,
            "score": 1.0,
        },
    ]
    decision = {
        "decision": "match",
        "cave_number": "211",
        "confidence": 0.94,
        "reason": "názov a kontext sedia",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="heuristic", model="test")

    assert audit["status"] == "uncertain"
    assert audit["allow_match"] is False
    assert "rovnak" in audit["reason"].casefold()


def test_audit_decision_downgrades_single_stem_multiple_candidate_match():
    cave = {
        "name": "Suchej",
        "slug": "suchej",
        "article_count": 2,
        "articles": [{"id": 1, "title": "Správa zo Suchej", "abstract": "Krátka správa bez presnej lokality."}],
    }
    candidates = [
        {
            "cave_number": "5888",
            "official_name": "Suchá jaskyňa",
            "names": ["Suchá jaskyňa"],
            "geomorph_celok": "Tatry",
            "name_score": 1.0,
            "context_score": 1.0,
            "score": 1.12,
        },
        {
            "cave_number": "2198",
            "official_name": "Suchá jaskyňa",
            "names": ["Suchá jaskyňa"],
            "geomorph_celok": "Nízke Tatry",
            "name_score": 1.0,
            "context_score": 0.8,
            "score": 1.096,
        },
    ]
    decision = {
        "decision": "match",
        "cave_number": "5888",
        "confidence": 0.9,
        "reason": "názov sedí",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="heuristic", model="test")

    assert audit["status"] == "uncertain"
    assert audit["allow_match"] is False
    reason = audit["reason"].casefold()
    assert "jednoslovn" in reason or "viac" in reason or "fuzzy" in reason


def test_audit_decision_downgrades_stem_only_collision():
    cave = {
        "name": "Silická radnica",
        "slug": "silicka-radnica",
        "article_count": 1,
        "articles": [{"id": 1, "title": "Silická radnica", "abstract": "Správa zo Silickej planiny."}],
    }
    candidates = [
        {
            "cave_number": "3710",
            "official_name": "Silická ľadnica",
            "names": ["Silická ľadnica"],
            "geomorph_celok": "Slovenský kras",
            "geomorph_podcelok": "Silická planina",
            "name_score": 0.96,
            "context_score": 3.0,
            "score": 1.32,
        }
    ]
    decision = {
        "decision": "match",
        "cave_number": "3710",
        "confidence": 0.9,
        "reason": "stemová podobnosť a región",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="heuristic", model="test")

    assert audit["status"] == "uncertain"
    assert audit["allow_match"] is False
    assert "fuzzy" in audit["reason"].casefold() or "alias" in audit["reason"].casefold()


def test_audit_decision_allows_strict_alias_match():
    cave = {
        "name": "Jaskyňa Okno",
        "slug": "jaskyna-okno",
        "article_count": 1,
        "articles": [{"id": 1, "title": "Jaskyňa Okno v Demänovskej doline", "abstract": ""}],
    }
    candidates = [
        {
            "cave_number": "1519",
            "official_name": "Okno",
            "names": ["Okno", "Jaskyňa Okno"],
            "geomorph_celok": "Nízke Tatry",
            "name_score": 1.0,
            "context_score": 2.0,
            "score": 1.24,
        }
    ]
    decision = {
        "decision": "match",
        "cave_number": "1519",
        "confidence": 0.9,
        "reason": "prísna aliasová zhoda",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="heuristic", model="test")

    assert audit["status"] == "confirmed"
    assert audit["allow_match"] is True


def test_audit_decision_downgrades_ai_match_when_reason_says_card_mixes_locations():
    cave = {
        "name": "Zbojnícka diera",
        "slug": "zbojnicka-diera",
        "article_count": 3,
        "articles": [
            {"id": 1, "title": "Jaskyňa Oltárkameň", "abstract": "Čergov."},
            {"id": 2, "title": "Zbojnícka diera pri Švošove", "abstract": "Veľká Fatra."},
        ],
    }
    candidates = [
        {
            "cave_number": "211",
            "official_name": "Zbojnícka diera",
            "names": ["Oltárkameň", "Zbojnícka diera"],
            "geomorph_celok": "Čergov",
            "name_score": 1.0,
            "context_score": 5.0,
            "score": 1.48,
        },
        {
            "cave_number": "6796",
            "official_name": "Zbojnícka diera",
            "names": ["Zbojnícka diera"],
            "geomorph_celok": "Veľká Fatra",
            "name_score": 1.0,
            "context_score": 1.0,
            "score": 1.12,
        },
    ]
    decision = {
        "decision": "match",
        "cave_number": "211",
        "confidence": 0.94,
        "reason": "Ostatné články uvádzajú samostatné rovnomenné lokality pri Švošove a Sulíne.",
    }

    audit = matcher.audit_decision(cave, candidates, decision, backend="codex", model="gpt-5.5")

    assert audit["status"] == "uncertain"
    assert audit["allow_match"] is False
    assert "spája" in audit["reason"] or "lokalit" in matcher.normalize(audit["reason"])


def test_heuristic_decision_rejects_foreign_name_even_with_slovak_expedition_context():
    cave = {
        "name": "Jaskyňa Velika klisura",
        "slug": "jaskyna-velika-klisura",
        "article_count": 1,
        "articles": [
            {
                "id": 1,
                "title": "Slovenská expedícia do jaskyne Velika klisura - Prokletije",
                "abstract": "Slovenskí jaskyniari skúmali Kosovo a pohorie Prokletije.",
            }
        ],
    }

    decision = matcher.heuristic_decision(cave, [])

    assert decision["decision"] == "defer"
    assert "zahrani" in decision["reason"].casefold()


def test_process_caves_does_not_write_ambiguous_heuristic_match(tmp_path):
    caves_path = tmp_path / "caves.json"
    register_path = tmp_path / "register.json"
    output_path = tmp_path / "matches.json"
    caves_path.write_text(
        json.dumps(
            [
                {
                    "name": "Diablova diera",
                    "slug": "diablova-diera",
                    "article_count": 2,
                    "articles": [
                        {
                            "id": 1,
                            "title": "Diablova diera v pohorí Branisko",
                            "abstract": "Prieskum v oblasti Branisko, Smrekovica.",
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
                        "cave_number": "81",
                        "official_name": "Diablova diera",
                        "names": ["Diablova diera"],
                        "geomorph_celok": "Branisko",
                        "geomorph_podcelok": "Smrekovica",
                    },
                    {
                        "cave_number": "82",
                        "official_name": "Diablova diera",
                        "names": ["Diablova diera"],
                        "geomorph_celok": "Branisko",
                        "geomorph_podcelok": "Smrekovica",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = matcher.process_caves(
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
            dry_run=True,
            resume=False,
        )
    )

    assert output["matches"] == []
    assert output["stats"]["matched"] == 0
    assert output["stats"]["uncertain"] == 1
    assert output["audit"]["uncertain"][0]["cave_slug"] == "diablova-diera"


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


def test_process_caves_retry_deferred_replaces_old_deferred(tmp_path):
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
    output_path.write_text(
        json.dumps(
            {
                "matches": [],
                "deferred": [{"cave_slug": "jaskyna-okno", "cave_name": "Jaskyňa Okno", "reason": "old"}],
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
            retry_deferred=True,
        )
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert [item["cave_slug"] for item in saved["matches"]] == ["jaskyna-okno"]
    assert saved["deferred"] == []
    assert saved["stats"]["retried_deferred"] == 1


def test_process_caves_retry_matches_can_downgrade_existing_match(tmp_path, monkeypatch):
    caves_path = tmp_path / "caves.json"
    register_path = tmp_path / "register.json"
    output_path = tmp_path / "matches.json"
    caves_path.write_text(
        json.dumps(
            [
                {
                    "name": "Zbojnícka diera",
                    "slug": "zbojnicka-diera",
                    "article_count": 2,
                    "articles": [{"id": 1, "title": "Zbojnícka diera", "abstract": "Čergov aj Veľká Fatra."}],
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
                        "cave_number": "211",
                        "official_name": "Zbojnícka diera",
                        "names": ["Oltárkameň", "Zbojnícka diera"],
                        "geomorph_celok": "Čergov",
                    },
                    {
                        "cave_number": "6796",
                        "official_name": "Zbojnícka diera",
                        "names": ["Zbojnícka diera"],
                        "geomorph_celok": "Veľká Fatra",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path.write_text(
        json.dumps(
            {
                "matches": [{"cave_slug": "zbojnicka-diera", "cave_name": "Zbojnícka diera", "cave_number": "211"}],
                "deferred": [],
                "audit": {
                    "confirmed": [{"cave_slug": "zbojnicka-diera", "status": "confirmed"}],
                    "uncertain": [],
                    "rejected": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def mixed_codex_decision(*args, **kwargs):
        return {
            "decision": "match",
            "cave_number": "211",
            "confidence": 0.94,
            "reason": "Karta spája názvy a ostatné články odkazujú na samostatné lokality.",
        }

    monkeypatch.setattr(matcher, "run_codex_decision", mixed_codex_decision)

    matcher.process_caves(
        SimpleNamespace(
            caves=caves_path,
            register=register_path,
            fulltext=tmp_path / "missing.jsonl",
            output=output_path,
            backend="codex",
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
            retry_deferred=False,
            retry_matches=True,
        )
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["matches"] == []
    assert [item["cave_slug"] for item in saved["deferred"]] == ["zbojnicka-diera"]
    assert saved["audit"]["confirmed"] == []
    assert [item["cave_slug"] for item in saved["audit"]["uncertain"]] == ["zbojnicka-diera"]
    assert saved["stats"]["retried_matches"] == 1
