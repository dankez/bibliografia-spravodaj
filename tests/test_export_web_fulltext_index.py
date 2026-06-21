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
