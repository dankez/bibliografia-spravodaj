import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import import_smopaj_cave_register as smopaj


def test_parse_geomorphology_entries_extracts_region_number_and_aliases():
    text = """
Zoznam jaskýň k 31.12.2017
podľa geomorfologických jednotiek

Nízke Tatry, Ďumbierske Tatry, Demänovské vrchy
1509. Demänovský jaskynný systém - k. ú. Demänovská Dolina, okr. Liptovský Mikuláš, dl. 41 463 m, hl. 196
m, r. č. 1509 [2217]
   1509. 1. Demänovská jaskyňa mieru - k. ú. Demänovská Dolina, okr. Liptovský Mikuláš, 812 m n. m.,
fluviokrasová, z.j.07= 1188, r. č. 1509.1. [2217]
   1509. 2. Demänovská jaskyňa slobody (Chrám slobody) - k. ú. Demänovská Dolina, okr. Liptovský Mikuláš,
fluviokrasová, z.j.07= 1189, r. č. 1509.2. [2217]

Slovenský kras, Silická planina
3483. Domica - Čertova diera - Stará Domica - k. ú. Kečovo, okr. Rožňava, dl. 6603 m, hl. 70 m, NPP, z.j.07=
2380, r. č. 3483 [68,2272]
"""

    entries = smopaj.parse_geomorphology_entries(text)
    by_number = {entry["registry_number"]: entry for entry in entries}

    assert by_number["1509"]["official_name"] == "Demänovský jaskynný systém"
    assert by_number["1509"]["geomorph_celok"] == "Nízke Tatry"
    assert by_number["1509"]["geomorph_podcelok"] == "Ďumbierske Tatry"
    assert by_number["1509"]["geomorph_cast"] == "Demänovské vrchy"

    assert by_number["1509.2"]["official_name"] == "Demänovská jaskyňa slobody"
    assert by_number["1509.2"]["aliases"] == ["Chrám slobody"]

    assert by_number["3483"]["official_name"] == "Domica - Čertova diera - Stará Domica"
    assert by_number["3483"]["geomorph_celok"] == "Slovenský kras"
    assert by_number["3483"]["geomorph_podcelok"] == "Silická planina"


def test_parse_name_register_and_merge_aliases_by_registry_number():
    register_text = """
REGISTER JASKÝŇ
Názov                                 Číslo jaskyne
Demänovský jaskynný systém                           1 509
   Demänovská jaskyňa slobody             1509.2.
Domica - Čertova diera - Stará Domica                      3 483
    Domica                                       3483.1.
Jasovská jaskyňa - Okno                          633
   Jasovská jaskyňa                   633.1.
"""
    entries = [
        {
            "registry_number": "1509.2",
            "official_name": "Demänovská jaskyňa slobody",
            "aliases": ["Chrám slobody"],
        },
        {
            "registry_number": "3483",
            "official_name": "Domica - Čertova diera - Stará Domica",
            "aliases": [],
        },
    ]

    names_by_number = smopaj.parse_name_register(register_text)
    merged = smopaj.merge_name_register(entries, names_by_number)
    by_number = {entry["registry_number"]: entry for entry in merged}

    assert by_number["1509.2"]["names"] == ["Demänovská jaskyňa slobody", "Chrám slobody"]
    assert by_number["3483"]["names"] == ["Domica - Čertova diera - Stará Domica"]
    assert names_by_number["3483.1"] == ["Domica"]
    assert names_by_number["633.1"] == ["Jasovská jaskyňa"]


def test_build_output_merges_name_register_by_cave_number_not_internal_registry_number():
    geomorphology_text = """
Slovenský raj, Dobšinské predhorie
4503. Dobšinská ľadová jaskyňa - k. ú. Dobšiná, okr. Rožňava, dl. 1483 m, r. č. 105 [12]
4504. Hubekova jaskyňa - k. ú. Dobšiná, okr. Rožňava, dl. 32 m, r. č. 4503 [12]
"""
    register_text = """
REGISTER JASKÝŇ
Názov                                 Číslo jaskyne
Dobšinská ľadová jaskyňa                         4 503
Hubekova jaskyňa                                  4 504
"""

    output = smopaj.build_output(geomorphology_text, register_text)
    by_cave_number = {entry["cave_number"]: entry for entry in output["entries"]}

    assert by_cave_number["4503"]["registry_number"] == "105"
    assert by_cave_number["4503"]["official_name"] == "Dobšinská ľadová jaskyňa"
    assert by_cave_number["4503"]["names"] == ["Dobšinská ľadová jaskyňa"]
    assert by_cave_number["4504"]["official_name"] == "Hubekova jaskyňa"
    assert by_cave_number["4504"]["names"] == ["Hubekova jaskyňa"]


def test_parse_geomorphology_entries_ignores_dangling_reference_bracket_lines():
    text = """
Nízke Tatry, Ďumbierske Tatry, Demänovské vrchy
1790. Malá jaskyňa pod Baštou - k. ú. Demänovská Dolina, okr. Liptovský Mikuláš, dl. 108 m, r. č. 19
[120,319,324,332,393
6]
]
1791. Malá jaskyňa pod Beníkovou - k. ú. Demänovská Dolina, okr. Liptovský Mikuláš, dl. 4 m, r. č. 3674 [324]
"""

    entries = smopaj.parse_geomorphology_entries(text)
    by_cave_number = {entry["cave_number"]: entry for entry in entries}

    assert by_cave_number["1791"]["geomorph_celok"] == "Nízke Tatry"
    assert by_cave_number["1791"]["geomorph_podcelok"] == "Ďumbierske Tatry"
    assert by_cave_number["1791"]["geomorph_cast"] == "Demänovské vrchy"
