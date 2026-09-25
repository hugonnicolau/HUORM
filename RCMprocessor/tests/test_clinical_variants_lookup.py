"""
Testes do ClinicalVariantsLookup.

Dois problemas corrigidos neste módulo:

  1. não partia combinações — ao contrário do resolver externo, que partia.
     A substância "paracetamol + tiocolquicosido" entrava inteira como
     candidato e era comparada como um bloco contra o campo `chemicals`;
  2. o match parcial usava substring nua nos dois sentidos, o que ligava
     fármacos distintos com nomes sobrepostos.

    python RCMprocessor/tests/test_clinical_variants_lookup.py
"""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent


def _load_module():
    """Carrega o módulo resolvendo o import relativo de substance_utils."""
    pkg = type(sys)("rcmpkg")
    pkg.__path__ = [str(PACKAGE_DIR)]
    sys.modules["rcmpkg"] = pkg

    for name in ("substance_utils", "clinical_variants_lookup"):
        spec = importlib.util.spec_from_file_location(
            f"rcmpkg.{name}", PACKAGE_DIR / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"rcmpkg.{name}"] = module
        spec.loader.exec_module(module)

    return sys.modules["rcmpkg.clinical_variants_lookup"]


mod = _load_module()
ClinicalVariantsLookup = mod.ClinicalVariantsLookup

ROWS = [
    # variant, gene, type, level of evidence, chemicals, phenotypes
    ("rs1801133", "MTHFR", "SNP", "1A", "methotrexate", "toxicity"),
    ("CYP2C19*2", "CYP2C19", "Haplotype", "1A", "clopidogrel,omeprazole", "efficacy"),
    ("rs4149056", "SLCO1B1", "SNP", "1A", "simvastatin", "toxicity"),
    ("G6PD A-", "G6PD", "Haplotype", "1A",
     "sulfamethoxazole / trimethoprim", "toxicity"),
    ("rs1057910", "CYP2C9", "SNP", "1A", "warfarin,acenocoumarol", "dosage"),
    ("rs12248560", "CYP2C19", "SNP", "2A", "escitalopram", "efficacy"),
]


def build_lookup() -> ClinicalVariantsLookup:
    tmp = Path(tempfile.mkdtemp()) / "clinicalVariants.tsv"
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(
            ["variant", "gene", "type", "level of evidence", "chemicals", "phenotypes"]
        )
        writer.writerows(ROWS)
    return ClinicalVariantsLookup(tmp)


LOOKUP = build_lookup()


# ==========================================================================
def test_loads_all_variants():
    assert LOOKUP.has_term("rs1801133")
    assert LOOKUP.has_term("CYP2C19*2")


def test_match_on_single_substance():
    matches = LOOKUP.get_all_matches("rs4149056", active_substance="sinvastatina",
                                     aliases=["simvastatin"])
    assert matches, "simvastatina devia corresponder a simvastatin"


def test_combination_substance_is_split():
    """O problema principal: "varfarina + ácido acetilsalicílico".

    Sem split, a string combinada nunca corresponde ao campo `chemicals`, que
    lista os fármacos individualmente.
    """
    matches = LOOKUP.get_all_matches(
        "rs1057910",
        active_substance="varfarina + ácido acetilsalicílico",
        aliases=["warfarin + acetylsalicylic acid"],
    )
    assert matches, "a combinação devia corresponder por via do componente warfarin"


def test_combination_in_the_reference_is_still_found():
    """O ClinPGx tem um químico que é ele próprio uma combinação."""
    matches = LOOKUP.get_all_matches(
        "G6PD A-",
        active_substance="sulfametoxazol + trimetoprim",
        aliases=["sulfamethoxazole + trimethoprim"],
    )
    assert matches


def test_comma_separated_chemicals_are_split():
    matches = LOOKUP.get_all_matches("CYP2C19*2", active_substance="omeprazol",
                                     aliases=["omeprazole"])
    assert matches, "chemicals separados por vírgula devem ser considerados"


# --- fronteiras de palavra ------------------------------------------------
def test_escitalopram_does_not_match_citalopram_entry():
    """São guidelines CPIC distintas; confundi-las é um erro de conteúdo."""
    matches = LOOKUP.get_all_matches("rs12248560", active_substance="citalopram",
                                     aliases=["citalopram"])
    assert not matches, "citalopram não deve corresponder ao registo de escitalopram"


def test_escitalopram_matches_its_own_entry():
    matches = LOOKUP.get_all_matches("rs12248560", active_substance="escitalopram",
                                     aliases=["escitalopram"])
    assert matches


def test_unrelated_substance_does_not_match():
    matches = LOOKUP.get_all_matches("rs4149056", active_substance="paracetamol",
                                     aliases=["paracetamol"])
    assert not matches


def test_no_substance_context_returns_all():
    """Sem contexto de substância, devolve todos os registos da variante."""
    everything = LOOKUP.get_all("rs4149056")
    assert everything


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
