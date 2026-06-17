import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_web_fulltext_index as exporter


def test_export_index_writes_compact_search_records(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    output_path = tmp_path / "fulltext_index.json"
    manifest_path = tmp_path / "fulltext_manifest.json"
    chunks_path.write_text(
        "\n".join(
            [
                json.dumps({"chunk_id": "a000001-c000-test", "article_id": 1, "text": "Objav jaskyne v plnom texte."}),
                json.dumps({"chunk_id": "a000002-c000-test", "article_id": 2, "text": "Mapa a plán podzemia."}),
                json.dumps({"chunk_id": "", "article_id": 3, "text": "Tento riadok sa preskočí."}),
            ]
        ),
        encoding="utf-8",
    )

    manifest = exporter.export_index(chunks_path, output_path, manifest_path)

    records = json.loads(output_path.read_text(encoding="utf-8"))
    assert records == [
        {"id": "a000001-c000-test", "a": 1, "t": "Objav jaskyne v plnom texte."},
        {"id": "a000002-c000-test", "a": 2, "t": "Mapa a plán podzemia."},
    ]
    assert manifest["chunks"] == 2
    assert manifest["articles"] == 2
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["bytes"] == output_path.stat().st_size
