import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import enrich_articles


def test_enrich_article_requires_direct_cave_phrase_for_stratenska_jaskyna():
    false_positive = enrich_articles.enrich_article(
        {
            "title": "Speleoexpedície do vnútra masívu Chimantá",
            "abstract": "Stratený svet Guayanskej vysočiny a Cueva Charles Brewer.",
        }
    )
    true_positive = enrich_articles.enrich_article(
        {
            "title": "Stopovacia skúška v Stratenskej jaskyni",
            "abstract": "Priebeh a výsledky stopovacej skúšky z augusta 2008.",
        }
    )

    assert "Stratenská jaskyňa" not in false_positive["caves"]
    assert "Stratenská jaskyňa" in true_positive["caves"]
