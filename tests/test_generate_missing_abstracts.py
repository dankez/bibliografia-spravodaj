import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_missing_abstracts as abstracts


GENERIC_ABSTRACT = "Obsahový záznam z čísla Aragonit 29/2 (2024) importovaný z obsahu čísla."


def test_detects_generic_import_abstracts():
    assert abstracts.is_generic_import_abstract(GENERIC_ABSTRACT)
    assert abstracts.is_generic_import_abstract(
        "Obsahový záznam z čísla Slovenský kras 61/2 (2023) importovaný z obsahu čísla."
    )
    assert not abstracts.is_generic_import_abstract("Opis výskumu jaskyne a výsledkov merania teploty vzduchu.")
    assert not abstracts.is_generic_import_abstract("")


def test_selects_only_imported_records_with_missing_or_generic_abstracts():
    articles = [
        {"id": 1, "created_by": abstracts.SAMPLE_IMPORT_CREATED_BY, "abstract": GENERIC_ABSTRACT},
        {"id": 2, "created_by": abstracts.SAMPLE_IMPORT_CREATED_BY, "abstract": ""},
        {"id": 3, "created_by": abstracts.SAMPLE_IMPORT_CREATED_BY, "abstract": "Vecná anotácia."},
        {"id": 4, "created_by": "other", "abstract": GENERIC_ABSTRACT},
    ]

    selected = abstracts.select_candidate_articles(articles)

    assert [article["id"] for article in selected] == [1, 2]


def test_safe_title_abstract_is_specific_without_inventing_details():
    article = {
        "title": "Teplota vzduchu v Malužinskej a Modrej jaskyni v Nízkych Tatrách",
        "caves": ["Malužinská jaskyňa", "Modrá jaskyňa"],
    }

    assert abstracts.safe_title_abstract(article) == (
        "Príspevok sa venuje téme „Teplota vzduchu v Malužinskej a Modrej jaskyni v Nízkych Tatrách“."
    )

    project = {"title": "Projekt inovácie a ochrany Demänovských jaskýň a jaskyne Zápoľná"}
    assert abstracts.safe_title_abstract(project).startswith("Príspevok informuje o projekte")


def test_normalize_generated_abstract_removes_labels_and_rejects_bad_output():
    assert (
        abstracts.normalize_generated_abstract("Anotácia: Článok opisuje meranie teploty vzduchu v dvoch jaskyniach.")
        == "Článok opisuje meranie teploty vzduchu v dvoch jaskyniach."
    )
    assert abstracts.normalize_generated_abstract(GENERIC_ABSTRACT) == ""
    assert abstracts.normalize_generated_abstract("neviem") == ""
    assert abstracts.normalize_generated_abstract("") == ""


def test_normalize_generated_abstract_strips_thinking_scaffold():
    raw = """Thinking...
    interný postup nemá byť v anotácii
    ...done thinking.
    ANOTACIA: Článok opisuje Zlepencovú jaskyňu v Zubereckej brázde, jej geologické pomery a morfológiu pri kontakte karbonatických zlepencov a slieňovcov.
    """

    assert abstracts.normalize_generated_abstract(raw) == (
        "Článok opisuje Zlepencovú jaskyňu v Zubereckej brázde, jej geologické pomery "
        "a morfológiu pri kontakte karbonatických zlepencov a slieňovcov."
    )


def test_normalize_generated_abstract_keeps_two_concise_sentences():
    raw = (
        "ANOTACIA: Prvá veta opisuje predmet článku a konkrétnu jaskyňu. "
        "Druhá veta stručne zhŕňa metódy a výsledky výskumu. "
        "Tretia veta už nemá byť v bibliografickej anotácii."
    )

    assert abstracts.normalize_generated_abstract(raw) == (
        "Prvá veta opisuje predmet článku a konkrétnu jaskyňu. "
        "Druhá veta stručne zhŕňa metódy a výsledky výskumu."
    )


def test_apply_abstract_result_sets_ai_metadata_or_clears_generic():
    article = {"id": 1, "abstract": GENERIC_ABSTRACT}
    changed = abstracts.apply_abstract_result(
        article,
        "Článok sumarizuje výsledky prieskumu Zlepencovej jaskyne a geologické podmienky jej vzniku.",
        model="gemma4:e2b-it-qat",
        generated_at="2026-06-19T00:00:00+00:00",
    )

    assert changed is True
    assert article["abstract"].startswith("Článok sumarizuje")
    assert article["abstract_source"] == "ai_pdf_text"
    assert article["abstract_generated_by"] == "gemma4:e2b-it-qat"
    assert article["abstract_generated_at"] == "2026-06-19T00:00:00+00:00"

    failed = {"id": 2, "abstract": GENERIC_ABSTRACT}
    changed = abstracts.apply_abstract_result(
        failed,
        "",
        model="gemma4:e2b-it-qat",
        generated_at="2026-06-19T00:00:00+00:00",
    )

    assert changed is True
    assert failed["abstract"] == ""
    assert failed["abstract_source"] == "missing"
    assert "abstract_generated_by" not in failed


def test_apply_abstract_result_counts_source_change_as_update():
    article = {
        "id": 3,
        "abstract": "Príspevok sa venuje téme „Jaskyňa“. ",
        "abstract_source": "ai_pdf_text",
    }

    changed = abstracts.apply_abstract_result(
        article,
        "Príspevok sa venuje téme „Jaskyňa“. ",
        model="title-fallback",
        generated_at="2026-06-19T00:00:00+00:00",
        source="title_fallback",
    )

    assert changed is True
    assert article["abstract_source"] == "title_fallback"


def test_sync_articles_updates_main_and_frontend_files(tmp_path):
    main_path = tmp_path / "articles.json"
    frontend_path = tmp_path / "frontend.json"
    articles = [{"id": 1, "created_by": abstracts.SAMPLE_IMPORT_CREATED_BY, "abstract": GENERIC_ABSTRACT}]
    main_path.write_text(json.dumps(articles), encoding="utf-8")
    frontend_path.write_text(json.dumps(articles), encoding="utf-8")

    updated = abstracts.sync_generated_abstracts(
        articles_path=main_path,
        frontend_path=frontend_path,
        generator=lambda article: "Článok približuje výskum jaskynnej lokality a hlavné odborné výsledky.",
        model="test-model",
        limit=None,
    )

    assert updated["processed"] == 1
    assert updated["updated"] == 1
    synced = json.loads(main_path.read_text(encoding="utf-8"))
    synced_frontend = json.loads(frontend_path.read_text(encoding="utf-8"))
    assert synced == synced_frontend
    assert synced[0]["abstract_source"] == "ai_pdf_text"


def test_force_mode_reprocesses_imported_records_with_existing_abstracts(tmp_path):
    main_path = tmp_path / "articles.json"
    frontend_path = tmp_path / "frontend.json"
    articles = [
        {
            "id": 1,
            "created_by": abstracts.SAMPLE_IMPORT_CREATED_BY,
            "abstract": "Pôvodná anotácia.",
            "abstract_source": "ai_pdf_text",
        }
    ]
    main_path.write_text(json.dumps(articles), encoding="utf-8")
    frontend_path.write_text(json.dumps(articles), encoding="utf-8")

    updated = abstracts.sync_generated_abstracts(
        articles_path=main_path,
        frontend_path=frontend_path,
        generator=lambda article: "Nová vecná anotácia k článku o jaskyni.",
        model="test-model",
        limit=None,
        force=True,
        source="title_fallback",
    )

    synced = json.loads(main_path.read_text(encoding="utf-8"))
    assert updated["processed"] == 1
    assert synced[0]["abstract"] == "Nová vecná anotácia k článku o jaskyni."
    assert synced[0]["abstract_source"] == "title_fallback"
