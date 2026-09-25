"""
Testes do substance_utils — partilhado pelo resolver externo e pelo lookup de
variantes clínicas.

Importa porque 122 dos 643 RCMs do corpus antigo (19%) tinham substância
combinada, e as guideline annotations do ClinPGx listam os fármacos
individualmente: uma combinação só cruza corretamente se for partida da mesma
maneira nos dois módulos.

    python extra-tools/testes/test_substance_utils.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "RCMprocessor" / "substance_utils.py"
spec = importlib.util.spec_from_file_location("substance_utils", SOURCE)
su = importlib.util.module_from_spec(spec)
spec.loader.exec_module(su)


# ==========================================================================
# normalize
# ==========================================================================
def test_normalize_strips_accents_and_case():
    assert su.normalize("Ácido Acetilsalicílico") == "acido acetilsalicilico"


def test_normalize_collapses_whitespace():
    assert su.normalize("  ácido   fólico \n") == "acido folico"


def test_normalize_handles_empty():
    assert su.normalize("") == ""
    assert su.normalize(None) == ""


# ==========================================================================
# split_substances
# ==========================================================================
def test_combination_is_split_into_components():
    assert su.split_substances("paracetamol + tiocolquicosido") == [
        "paracetamol + tiocolquicosido", "paracetamol", "tiocolquicosido",
    ]


def test_whole_string_is_kept_first():
    """O ClinPGx tem uma substância que é ela própria uma combinação.

    "sulfamethoxazole / trimethoprim" (PA166279741). Se só as partes fossem
    consultadas, esse registo nunca seria encontrado pela string completa.
    """
    parts = su.split_substances("sulfamethoxazole / trimethoprim")
    assert parts[0] == "sulfamethoxazole / trimethoprim"
    assert "sulfamethoxazole" in parts and "trimethoprim" in parts


def test_keep_whole_can_be_disabled():
    parts = su.split_substances("a-longa + b-longa", keep_whole=False)
    assert "a-longa + b-longa" not in parts


def test_stopwords_are_dropped():
    """"Vitamin K and analogues" (PA166279741) produzia a query "analogues"."""
    parts = su.split_substances("Vitamin K and analogues")
    assert "analogues" not in [p.lower() for p in parts]
    assert "Vitamin K" in parts


def test_short_fragments_are_dropped():
    """Fragmentos curtos são perigosos com matching por substring."""
    parts = su.split_substances("aspirina + ab")
    assert "ab" not in parts


def test_single_substance_returns_itself():
    assert su.split_substances("ácido acetilsalicílico") == ["ácido acetilsalicílico"]


def test_empty_input():
    assert su.split_substances("") == []
    assert su.split_substances("   ") == []


def test_deduplication_preserves_order():
    parts = su.split_substances("paracetamol + paracetamol")
    assert parts == ["paracetamol + paracetamol", "paracetamol"]


# ==========================================================================
# build_queries
# ==========================================================================
def test_aliases_come_before_the_portuguese_name():
    """As bases de referência são em inglês; os aliases devem ser tentados primeiro."""
    queries = su.build_queries("varfarina", ["warfarin"])
    assert queries.index("warfarin") < queries.index("varfarina")


def test_build_queries_splits_both_sides():
    queries = su.build_queries(
        "paracetamol + tiocolquicosido", ["paracetamol + thiocolchicoside"]
    )
    lowered = [q.lower() for q in queries]
    assert "thiocolchicoside" in lowered
    assert "tiocolquicosido" in lowered


def test_build_queries_deduplicates():
    queries = su.build_queries("paracetamol", ["paracetamol"])
    assert len(queries) == 1


# ==========================================================================
# matches — fronteiras de palavra
# ==========================================================================
def test_iron_does_not_match_spironolactone():
    """O falso positivo que motivou a correção: sp[iron]olactone."""
    assert su.matches("spironolactone", "Iron") is False


def test_real_substring_matches_are_kept():
    assert su.matches("simvastatin acid", "simvastatin") is True
    assert su.matches("tenofovir disoproxil fumarate", "tenofovir disoproxil") is True
    assert su.matches("fluticasone propionate", "fluticasone") is True
    assert su.matches("sulfamethoxazole / trimethoprim", "sulfamethoxazole") is True


def test_distinct_drugs_with_overlapping_names_do_not_match():
    """Casos medidos no corpus: 76 dos 625 RCMs tinham cruzamentos espúrios."""
    pairs = [
        ("chlorothiazide", "hydrochlorothiazide"),
        ("estradiol", "ethinylestradiol"),
        ("citalopram", "escitalopram"),
        ("omeprazole", "esomeprazole"),
        ("ofloxacin", "ciprofloxacin"),
        ("ephedrine", "pseudoephedrine"),
        ("acetazolamide", "cetazolam"),
        ("imipramine", "trimipramine"),
        ("chloroquine", "hydroxychloroquine"),
        ("progesterone", "medroxyprogesterone"),
        ("temsirolimus", "sirolimus"),
    ]
    for reference, query in pairs:
        assert su.matches(reference, query) is False, f"{query} ~ {reference}"


def test_exact_match_always_wins():
    assert su.matches("warfarin", "warfarin") is True


def test_curated_equivalence_is_applied():
    """Enantiómeros precisam de declaração explícita, não de semelhança textual."""
    assert su.matches("ibuprofen", "dexibuprofen") is True


def test_metabolites_are_not_matched_by_default():
    """Decisão farmacológica deliberada, não acidente de string matching."""
    assert su.matches("norclobazam", "clobazam") is False
    assert su.matches("desmethylnaproxen", "naproxen") is False


def test_matches_any():
    assert su.matches_any("warfarin", ["aspirin", "warfarin"]) is True
    assert su.matches_any("warfarin", ["aspirin"]) is False
    assert su.matches_any("warfarin", []) is False


def test_empty_values_never_match():
    assert su.matches("", "warfarin") is False
    assert su.matches("warfarin", "") is False


# ==========================================================================
if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passaram")
    sys.exit(1 if failures else 0)
