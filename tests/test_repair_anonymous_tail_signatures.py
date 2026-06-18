import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repair_anonymous_tail_signatures as repair


def bbox_line(order: int, text: str, page: int = 1) -> repair.BboxLine:
    return repair.BboxLine(
        page=page,
        order=order,
        page_order=order,
        x_min=0,
        y_min=order * 10,
        x_max=100,
        y_max=order * 10 + 8,
        text=text,
    )


def test_parse_signature_strips_role_suffix_and_formats_name():
    parsed = repair.parse_signature_line("Igor Balciar, podpredseda")

    assert parsed is not None
    authors, signature_line, reasons = parsed
    assert authors == ["Balciar, I."]
    assert signature_line == "Igor Balciar"
    assert "role_suffix:podpredseda" in reasons


def test_parse_signature_strips_senior_suffix_before_role():
    parsed = repair.parse_signature_line("Pavol Pokrievka ml., predseda")

    assert parsed is not None
    authors, signature_line, reasons = parsed
    assert authors == ["Pokrievka, P."]
    assert signature_line == "Pavol Pokrievka ml."
    assert "role_suffix:predseda" in reasons


def test_parse_signature_handles_napisali_initial_names():
    parsed = repair.parse_signature_line("Napísali Z. Hochmuth a A. Gessert")

    assert parsed is not None
    authors, _signature_line, reasons = parsed
    assert authors == ["Hochmuth, Z.", "Gessert, A."]
    assert "signature_prefix" in reasons


def test_parse_signature_handles_main_authors_with_contributions():
    parsed = repair.parse_signature_line("J. Psotka a P. Belanský s príspevkami")

    assert parsed is not None
    authors, _signature_line, reasons = parsed
    assert authors == ["Psotka, J.", "Belanský, P."]
    assert "with_contributions" in reasons


def test_normalize_gemma_authors_splits_two_surname_initial_authors():
    authors = repair.normalize_gemma_authors(["Hochmuth, Z. a Gessert, A."])

    assert authors == ["Hochmuth, Z.", "Gessert, A."]


def test_parse_signature_rejects_photo_caption():
    parsed = repair.parse_signature_line("Pseudokrasová jaskyňa Béza Bori. Foto: Ľ. Gaál")

    assert parsed is None


def test_parse_signature_rejects_uppercase_place_abbreviation():
    parsed = repair.parse_signature_line("OO Tatranská Javorina .")

    assert parsed is None


def test_tail_signature_uses_region_before_next_title_on_same_page():
    lines = [
        bbox_line(0, "OBLaStná SkupIna Veľká Fatra"),
        bbox_line(1, "V roku 2025 skupina pokračovala v prieskume."),
        bbox_line(2, "František Vacek"),
        bbox_line(3, "žILInSký jaSkynIarSky kLuB"),
        bbox_line(4, "ktorú zdokumentoval člen klubu Ján Majko . Tibor Pajtina, predseda"),
    ]

    current = repair.find_title_match(lines, "Oblastná skupina Veľká Fatra")
    assert current is not None
    next_title = repair.find_title_match(lines, "Žilinský jaskyniarsky klub", min_index=current.end_index)
    assert next_title is not None

    region = lines[current.end_index : next_title.start_index]
    candidate = repair.find_tail_signature(region)

    assert candidate is not None
    assert candidate.authors == ["Vacek, F."]
    assert candidate.signature_line == "František Vacek"


def test_tail_signature_can_extract_signature_after_sentence_on_same_line():
    lines = [
        bbox_line(0, "žILInSký jaSkynIarSky kLuB"),
        bbox_line(1, "ktorú zdokumentoval člen klubu Ján Majko . Tibor Pajtina, predseda"),
    ]

    current = repair.find_title_match(lines, "Žilinský jaskyniarsky klub")
    assert current is not None
    region = lines[current.end_index :]
    candidate = repair.find_tail_signature(region)

    assert candidate is not None
    assert candidate.authors == ["Pajtina, T."]
    assert candidate.signature_line == "Tibor Pajtina"


def test_tail_signature_scores_standalone_final_name_high_enough_for_apply():
    lines = [
        bbox_line(0, "SPELEO BRATISLAVA"),
        bbox_line(1, "Podieľame sa na monitoringu výskytu netopierov ."),
        bbox_line(2, "Peter Magdolen"),
    ]

    region = lines[1:]
    candidate = repair.find_tail_signature(region)

    assert candidate is not None
    assert candidate.authors == ["Magdolen, P."]
    assert candidate.confidence >= 0.88


def test_tail_signature_handles_role_suffix_on_next_line_in_wider_tail():
    lines = [
        bbox_line(index, f"riadok {index}") for index in range(35)
    ] + [
        bbox_line(35, "Ing. Štefan Mlynárik,"),
        bbox_line(36, "predseda speleoklubu"),
        bbox_line(37, "text z druhého stĺpca"),
        bbox_line(38, "ďalší text z druhého stĺpca"),
    ]

    candidate = repair.find_tail_signature(lines)

    assert candidate is not None
    assert candidate.authors == ["Mlynárik, Š."]
    assert candidate.signature_line == "Ing. Štefan Mlynárik"
    assert candidate.confidence >= 0.88


def test_tail_signature_accepts_group_signature_at_article_end():
    lines = [
        bbox_line(0, "Špeciálne poďakovanie patrí členom skupiny ."),
        bbox_line(1, "Členovia OS Čachtice"),
    ]

    candidate = repair.find_tail_signature(lines)

    assert candidate is not None
    assert candidate.authors == ["Členovia OS Čachtice"]
    assert candidate.signature_line == "Členovia OS Čachtice"
    assert "group_signature" in candidate.reasons


def test_group_signature_rejects_running_sentence():
    parsed = repair.parse_group_signature_line("Členovia klubu sa zúčastnili rôznych podu-")

    assert parsed is None


def test_tail_signature_scores_bottom_column_name_even_when_text_order_continues():
    bottom_signature = repair.BboxLine(
        page=1,
        order=1,
        page_order=1,
        x_min=350,
        y_min=590,
        x_max=420,
        y_max=602,
        text="Karol Kýška",
    )
    lines = [bbox_line(0, "Text článku."), bottom_signature]
    lines.extend(bbox_line(index + 2, f"pokračovanie druhého stĺpca {index}") for index in range(50))

    candidate = repair.find_tail_signature(lines)

    assert candidate is not None
    assert candidate.authors == ["Kýška, K."]
    assert candidate.confidence >= 0.88


def test_tail_signature_uses_role_context_for_standalone_name():
    lines = [
        bbox_line(0, "V súčasnosti vykonáva funkciu predsedu Marián Grúz ."),
        bbox_line(1, "Aktivity pokračovali počas celého roka ."),
        bbox_line(2, "Marián Grúz"),
    ]
    lines.extend(bbox_line(index + 3, f"ďalší text {index}") for index in range(30))

    candidate = repair.find_tail_signature(lines)

    assert candidate is not None
    assert candidate.authors == ["Grúz, M."]
    assert candidate.confidence >= 0.88
    assert "role_context" in candidate.reasons


def test_resolve_printed_page_range_interpolates_missing_footer_page():
    start, end, error = repair.resolve_printed_page_range(59, 60, {58: 60, 60: 62})

    assert error is None
    assert (start, end) == (61, 62)


def test_title_window_score_does_not_match_single_body_word_inside_long_title():
    score = repair.title_window_score("Najdlhšie jaskyne Slovenska, stav k 1. 3. 2026", "jaskyne .")

    assert score < 0.72


def test_next_title_match_ignores_body_mentions_of_later_articles():
    lines = [
        bbox_line(0, "SPELEOKLUB BANSKÁ BYSTRICA"),
        bbox_line(1, "Zúčastnil sa potápačskej expedície Speleodiveru na Sardínii ."),
        bbox_line(2, "Dziẹkuję . Účastníci Iveta a Števo Mlynárikovci ."),
        bbox_line(3, "SPELEO BRATISLAVA"),
    ]
    following = [
        {"title": "Speleo Bratislava"},
        {"title": "Speleodiver"},
    ]

    match, title = repair.find_next_title_match(lines, following, min_index=1)

    assert match is not None
    assert title == "Speleo Bratislava"
    assert match.start_index == 3
