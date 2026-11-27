import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_web_fulltext_index as exporter


def test_export_index_writes_compact_search_records(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "fulltext"
    manifest_path = tmp_path / "fulltext_manifest.json"
    chunks_path.write_text(
        "\n".join(
            [
                json.dumps({"chunk_id": "a000001-c000-test", "article_id": 1, "journal_id": "spravodaj_sss", "year": 1970, "text": "Objav jaskyne v plnom texte."}),
                json.dumps({"chunk_id": "a000002-c000-test", "article_id": 2, "journal_id": "aragonit", "year": 2024, "text": "Mapa a plán podzemia."}),
                json.dumps({"chunk_id": "", "article_id": 3, "text": "Tento riadok sa preskočí."}),
            ]
        ),
        encoding="utf-8",
    )

    manifest = exporter.export_index(chunks_path, output_dir, manifest_path)

    spravodaj_records = json.loads((output_dir / "spravodaj_sss" / "1970.json").read_text(encoding="utf-8"))
    aragonit_records = json.loads((output_dir / "aragonit" / "2024.json").read_text(encoding="utf-8"))
    assert spravodaj_records == [
        {"id": "a000001-c000-test", "a": 1, "t": "Objav jaskyne v plnom texte."},
    ]
    assert aragonit_records == [
        {"id": "a000002-c000-test", "a": 2, "t": "Mapa a plán podzemia."},
    ]
    assert manifest["chunks"] == 2
    assert manifest["articles"] == 2
    assert manifest["version"] == 2
    assert {shard["path"] for shard in manifest["shards"]} == {
        "fulltext/aragonit/2024.json",
        "fulltext/spravodaj_sss/1970.json",
    }
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["bytes"] == sum(
        shard["bytes"] for shard in manifest["shards"]
    )


def test_export_replaces_stale_chunks_with_curated_text(tmp_path, monkeypatch):
    text = "Opravený obsah jaskyne. " * 220
    override = {"text": text, "journal_id": "spravodaj_sss", "year": 1970, "pdf_url": "https://example.test/a.pdf"}
    monkeypatch.setattr(exporter, "load_fulltext_overrides", lambda: {1: override})
    chunks_path = tmp_path / "chunks.jsonl"
    records = [
        {"chunk_id": "old-1", "article_id": 1, "journal_id": "spravodaj_sss", "year": 1970, "pdf_url": "https://example.test/a.pdf#page=3", "text": "chybný obsah"},
        {"chunk_id": "old-2", "article_id": 1, "journal_id": "spravodaj_sss", "year": 1970, "pdf_url": "https://example.test/a.pdf#page=4", "text": "ďalší chybný obsah"},
        {"chunk_id": "other", "article_id": 2, "journal_id": "spravodaj_sss", "year": 1970, "text": "iný článok"},
    ]
    chunks_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records), encoding="utf-8")
    manifest = exporter.export_index(chunks_path, tmp_path / "fulltext", tmp_path / "manifest.json")
    output = json.loads((tmp_path / "fulltext" / "spravodaj_sss" / "1970.json").read_text(encoding="utf-8"))
    corrected = [row for row in output if row["a"] == 1]
    assert len(corrected) > 1
    assert all("chybný obsah" not in row["t"] for row in corrected)
    assert "Opravený obsah jaskyne" in corrected[0]["t"]
    assert [row["t"] for row in output if row["a"] == 2] == ["iný článok"]
    assert manifest["chunks"] == len(output)
    assert manifest["articles"] == 2


def test_export_does_not_apply_override_to_different_source(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "load_fulltext_overrides", lambda: {
        1: {"text": "nesprávna náhrada", "journal_id": "spravodaj_sss", "year": 1970, "pdf_url": "https://example.test/a.pdf"}
    })
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps({
        "chunk_id": "original", "article_id": 1, "journal_id": "spravodaj_sss",
        "year": 1970, "pdf_url": "https://example.test/other.pdf", "text": "pôvodný text",
    }), encoding="utf-8")
    exporter.export_index(chunks_path, tmp_path / "fulltext", tmp_path / "manifest.json")
    output = json.loads((tmp_path / "fulltext" / "spravodaj_sss" / "1970.json").read_text(encoding="utf-8"))
    assert output[0]["t"] == "pôvodný text"


def test_export_adds_verified_override_when_no_chunks_exist(tmp_path, monkeypatch):
    override = {"text": "Overený text článku", "journal_id": "spravodaj_sss", "year": 1970, "pdf_url": "https://example.test/a.pdf"}
    monkeypatch.setattr(exporter, "load_fulltext_overrides", lambda: {1: override, 2: override})
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("", encoding="utf-8")
    articles = tmp_path / "articles.json"
    articles.write_text(json.dumps([
        {"id": 1, "year": 1970, "pdf_url": "https://example.test/a.pdf"},
        {"id": 2, "year": 1970, "pdf_url": "https://example.test/other.pdf"},
    ]), encoding="utf-8")

    manifest = exporter.export_index(chunks, tmp_path / "fulltext", tmp_path / "manifest.json", articles)

    output = json.loads((tmp_path / "fulltext" / "spravodaj_sss" / "1970.json").read_text(encoding="utf-8"))
    assert [(row["a"], row["t"]) for row in output] == [(1, "Overený text článku")]
    assert manifest["articles"] == 1


def test_published_index_keeps_corrected_text_and_article_boundaries():
    overrides = exporter.load_fulltext_overrides()
    ids = [289, 290, 291, 292, 1502, 2579, 2598, 2803, *range(2806, 2815),
           3993, 3994, 4133, 4134, 4135, 4136]
    for article_id in ids:
        override = overrides[article_id]
        path = ROOT / "web" / "public" / "data" / "fulltext" / override["journal_id"] / f'{override["year"]}.json'
        records = json.loads(path.read_text(encoding="utf-8"))
        chunks = [row["t"] for row in records if row["a"] == article_id]
        expected = exporter.chunk_text(exporter.clean_fulltext(override["text"]), 3200, 350)
        assert chunks == [chunk["text"] for chunk in expected]

    assert "ZATOPENÁ PRIEPASŤ MORSKÉ OKO" not in overrides[4133]["text"]
    assert "International Relations of the Speleologists" not in overrides[289]["text"]
    assert "BOCNA PRITOKOVA CHODBA DO RIECISKA" not in overrides[3994]["text"]
