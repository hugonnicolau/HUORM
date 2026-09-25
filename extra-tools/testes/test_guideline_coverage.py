"""
Testes da cobertura de guidelines.

Definição sob teste: uma guideline do ClinPGx é um par FÁRMACO-GENE. Não é uma
anotação em genes.tsv (relevância abstrata do gene) nem em clinicalVariants.tsv
(evidência de variante). Só `guidelineAnnotations` conta.

    python extra-tools/testes/test_guideline_coverage.py
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "RCMprocessor" / "pgx_global_analysis.py"


def _load_class():
    """Carrega PGxGlobalAnalysis sem exigir openpyxl."""
    fake = types.ModuleType("openpyxl")
    fake.Workbook = object
    sys.modules.setdefault("openpyxl", fake)

    # Um substituto por cada módulo que o pgx_global_analysis importa. Se lá
    # for acrescentado outro import do openpyxl, tem de vir para aqui também,
    # senão este teste morre com "'openpyxl' is not a package" — foi o que
    # aconteceu quando o ILLEGAL_CHARACTERS_RE e o Worksheet entraram.
    for sub, names in (("styles", ("Font", "PatternFill", "Alignment")),
                       ("utils", ("get_column_letter",)),
                       ("cell", ()),
                       ("cell.cell", ("ILLEGAL_CHARACTERS_RE",)),
                       ("worksheet", ()),
                       ("worksheet.worksheet", ("Worksheet",))):
        mod = types.ModuleType(f"openpyxl.{sub}")
        for n in names:
            if n.endswith("_RE"):
                # tem de ser uma expressão regular a sério: o módulo faz
                # .sub() com ela. (?!) nunca casa, que é o que queremos.
                valor = re.compile(r"(?!)")
            elif n == "Worksheet":
                # o módulo substitui Worksheet.append por uma versão que
                # limpa caracteres de controlo, e guarda a original antes —
                # por isso o substituto tem de ter um append para guardar.
                valor = type("Worksheet", (), {"append": lambda self, linha: None})
            else:
                valor = type(n, (), {})
            setattr(mod, n, valor)
        sys.modules.setdefault(f"openpyxl.{sub}", mod)

    namespace: dict = {}
    exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), namespace)
    return namespace["PGxGlobalAnalysis"]


Analysis = _load_class()


def make() -> object:
    """Instância sem passar pelo __init__ (que exige uma pasta de outputs)."""
    return Analysis.__new__(Analysis)


def guideline(gid: str, genes: list[str], source: str = "CPIC") -> dict:
    return {
        "guideline_id": gid,
        "guideline_name": f"Annotation of {source} Guideline",
        "source": source,
        "related_genes": [{"symbol": g, "name": g} for g in genes],
    }


def extended(matches: list[dict]) -> dict:
    return {
        "active_substance_external_references": {
            "clinpgx": {"found": bool(matches), "matches": matches}
        }
    }


def unique(genes=(), stars=(), diplos=(), rsids=()) -> dict:
    return {
        "entidades": {
            "genes": [{"entity": g} for g in genes],
            "star_alleles": [{"entity": e, "gene": g} for e, g in stars],
            "diplotypes": [{"entity": e, "genes": gs} for e, gs in diplos],
            "rsids": [{"entity": e, "gene": g} for e, g in rsids],
        }
    }


def rows(u, e):
    return make()._guideline_coverage_rows("DOC", "substância", u, e)


# ==========================================================================
def test_single_gene_guideline_covered():
    r = rows(unique(genes=["CYP2C19"]), extended([guideline("PA1", ["CYP2C19"])]))
    assert len(r) == 1
    assert r[0]["status"] == "coberta"
    assert r[0]["covered_genes"] == ["CYP2C19"]
    assert r[0]["missing_genes"] == []


def test_single_gene_guideline_absent():
    """A substância tem guideline mas o RCM não menciona o gene."""
    r = rows(unique(genes=["CYP3A4"]), extended([guideline("PA1", ["CYP2C19"])]))
    assert r[0]["status"] == "ausente"
    assert r[0]["missing_genes"] == ["CYP2C19"]
    assert r[0]["n_covered"] == 0


def test_multi_gene_guideline_partial():
    """27 das 217 guidelines do snapshot têm mais de um gene."""
    g = guideline("PA166341522", ["ADRA2C", "ADRB1", "GRK4", "GRK5"])
    r = rows(unique(genes=["ADRB1"]), extended([g]))
    assert r[0]["status"] == "parcial"
    assert r[0]["covered_genes"] == ["ADRB1"]
    assert r[0]["n_expected"] == 4
    assert r[0]["n_covered"] == 1


def test_multi_gene_guideline_fully_covered():
    g = guideline("PA1", ["CYP2C9", "VKORC1"])
    r = rows(unique(genes=["VKORC1", "CYP2C9"]), extended([g]))
    assert r[0]["status"] == "coberta"


# --- o ponto importante: o alelo implica o gene ---------------------------
def test_star_allele_implies_its_gene():
    """Um RCM que diz CYP2D6*4 está a referenciar CYP2D6.

    Contar apenas genes isolados subestimaria a cobertura exactamente nos
    documentos mais informativos — os que dão o alelo concreto.
    """
    r = rows(unique(stars=[("CYP2D6*4", "CYP2D6")]),
             extended([guideline("PA1", ["CYP2D6"])]))
    assert r[0]["status"] == "coberta"


def test_star_allele_without_gene_field_uses_prefix():
    r = rows(unique(stars=[("CYP2C9*3", "")]),
             extended([guideline("PA1", ["CYP2C9"])]))
    assert r[0]["status"] == "coberta"


def test_diplotype_genes_counted():
    r = rows(unique(diplos=[("CYP2C19*1*2", ["CYP2C19"])]),
             extended([guideline("PA1", ["CYP2C19"])]))
    assert r[0]["status"] == "coberta"


def test_rsid_gene_counted():
    r = rows(unique(rsids=[("rs4149056", "SLCO1B1")]),
             extended([guideline("PA1", ["SLCO1B1"])]))
    assert r[0]["status"] == "coberta"


# --- guardas -------------------------------------------------------------
def test_no_guideline_no_rows():
    assert rows(unique(genes=["CYP2D6"]), extended([])) == []


def test_guideline_without_genes_is_skipped():
    """Uma guideline sem relatedGenes não é um par fármaco-gene."""
    assert rows(unique(genes=["CYP2D6"]), extended([guideline("PA1", [])])) == []


def test_symbol_normalisation():
    r = rows(unique(genes=[" cyp2c19 "]), extended([guideline("PA1", ["CYP2C19"])]))
    assert r[0]["status"] == "coberta"


def test_multiple_guidelines_per_substance():
    """Uma substância pode ter guidelines de fontes diferentes e genes diferentes."""
    r = rows(
        unique(genes=["CYP2C19"]),
        extended([
            guideline("PA1", ["CYP2C19"], "CPIC"),
            guideline("PA2", ["CYP2D6"], "DPWG"),
        ]),
    )
    assert len(r) == 2
    by_id = {x["guideline_id"]: x["status"] for x in r}
    assert by_id == {"PA1": "coberta", "PA2": "ausente"}


# --- genes.tsv NÃO é guideline -------------------------------------------
def test_genes_tsv_evidence_is_not_a_guideline():
    """Presença em genes.tsv / clinicalVariants.tsv não conta como guideline."""
    item = {
        "entity": "CYP2D6",
        "source_matches": {"genes_tsv": True, "clinicalVariants_tsv": True,
                           "clinpgx_guideline_json": False},
        "evidence_flags": {"is_known_pgx_gene": True,
                           "has_clinical_variant_evidence": True,
                           "has_guideline": False},
    }
    assert make()._entity_has_guideline(item) is False


def test_guideline_annotation_evidence_counts():
    item = {"entity": "CYP2D6", "ids": {"guideline_ids": ["PA166104931"]}}
    assert make()._entity_has_guideline(item) is True


def test_missing_genes_are_reported():
    """"Tem guideline mas faltam genes" tem de ser legível no output."""
    g = guideline("PA166104949", ["CYP2C9", "CYP4F2", "VKORC1"])
    r = rows(unique(genes=["CYP2C9", "VKORC1"]), extended([g]))
    assert r[0]["status"] == "parcial"
    assert r[0]["covered_genes"] == ["CYP2C9", "VKORC1"]
    assert r[0]["missing_genes"] == ["CYP4F2"], "o gene omitido tem de ser nomeado"
    assert r[0]["n_expected"] == 3 and r[0]["n_covered"] == 2


def test_sheet_columns_match_row_values():
    """Cabeçalhos e valores das folhas têm de ter o mesmo nº de colunas.

    Acrescentar uma coluna e esquecer o valor correspondente desalinha a folha
    inteira em silêncio — o Excel não se queixa.
    """
    import ast
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    def append_sizes(fn_name):
        sizes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "append"
                            and sub.args and isinstance(sub.args[0], ast.List)):
                        sizes.append(len(sub.args[0].elts))
        return sizes

    for fn in ("_write_documents", "_write_guideline_coverage_detail",
               "_write_guideline_gene_coverage", "_write_farmaco_entidades",
               "_write_group_summary"):
        sizes = set(append_sizes(fn))
        assert len(sizes) == 1, f"{fn}: colunas inconsistentes {sorted(sizes)}"


def test_document_has_guideline_requires_gene_in_label():
    """A substância ter guideline não basta — foi o bug dos 49 documentos."""
    a = make()
    e = extended([guideline("PA1", ["CYP2C19"])])
    assert a._substance_has_guideline(e) is True
    assert a._has_guideline(unique(genes=["CYP3A4"]), e) is False
    assert a._has_guideline(unique(genes=["CYP2C19"]), e) is True


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
