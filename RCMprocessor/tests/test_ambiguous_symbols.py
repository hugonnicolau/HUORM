"""
Testes dos símbolos de gene que colidem com palavras portuguesas.

Medido sobre 3,5 milhões de caracteres de RCM real (71 documentos): 29
símbolos de gene do ClinPGx coincidem com palavras comuns. Os piores:

    POR   2 572 ocorrências no corpus, 3 em maiúsculas
    AR    1 577 ocorrências, 1 em maiúsculas
    TES   4 461 ocorrências, 0 do gene
    ADA   1 120 ocorrências, 0 do gene

O risco não é o modelo extraí-los — o prompt de extração exige contexto
farmacogenómico. É a CONTAGEM: bastaria uma identificação legítima num
documento para lhe atribuir todas as preposições do texto.

Exigir maiúsculas não resolve. As três ocorrências de "POR" em maiúsculas do
corpus são "INJEÇÃO POR BÓLUS", cabeçalho de tabela; a única de "AR" é
"artrite reumatoide (AR)". Zero verdadeiros positivos em ambos.

    python RCMprocessor/tests/test_ambiguous_symbols.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "pharmacogenomics_evaluator.py"


def _load() -> dict:
    src = SOURCE.read_text(encoding="utf-8")
    ns: dict = {"re": re}

    for nome in ("AMBIGUOUS_GENE_SYMBOLS", "GENETIC_CONTEXT", "GENETIC_CONTEXT_WINDOW"):
        i = src.index(f"    {nome} ")
        j = src.index("\n\n", i)
        exec(compile("\n".join(l[4:] for l in src[i:j].split("\n")), "x", "exec"), ns)

    for metodo in ("_mention_has_genetic_context", "_count_ambiguous_symbol"):
        i = src.index(f"    def {metodo}(")
        rest = src[i + 10:]
        j = i + 10 + min(
            (rest.index(m) for m in ("\n    @", "\n    def ") if m in rest),
            default=len(rest),
        )
        body = "\n".join(l[4:] if l.startswith("    ") else l
                         for l in src[i:j].split("\n"))
        body = body.replace("cls.", "").replace("cls, ", "").replace("@classmethod\n", "")
        exec(compile(body, "x", "exec"), ns)

    return ns


NS = _load()
count = NS["_count_ambiguous_symbol"]
AMBIGUOUS = NS["AMBIGUOUS_GENE_SYMBOLS"]


# ==========================================================================
# Casos retirados do corpus real — todos devem dar zero
# ==========================================================================
def test_por_as_preposition_in_table_header():
    """As três ocorrências de POR em maiúsculas do corpus são esta."""
    texto = "| INDICAÇÃO | INJEÇÃO POR BÓLUS (micrograma/kg) | PERFUSÃO CONTÍNUA |"
    assert count(texto, "POR") == 0


def test_ar_as_clinical_abbreviation():
    """A única ocorrência de AR em maiúsculas do corpus é esta."""
    texto = ("doentes com osteoartrite (OA) ou artrite reumatoide (AR) com ou em "
             "risco elevado de doença cardiovascular")
    assert count(texto, "AR") == 0


def test_lowercase_never_counts():
    """Mesmo com vocabulário genético por perto."""
    texto = "administrado por via oral e metabolizado pela enzima CYP2C9"
    assert count(texto, "POR") == 0


def test_uppercase_without_genetic_context_does_not_count():
    texto = "A dose de manutenção é administrada POR PERFUSÃO CONTÍNUA."
    assert count(texto, "POR") == 0


# ==========================================================================
# Menções legítimas — têm de contar
# ==========================================================================
def test_gene_with_explicit_context_counts():
    casos = [
        ("A atividade da enzima POR (P450 oxidoreductase) influencia o metabolismo",
         "POR"),
        ("Doentes com polimorfismo do gene POR apresentam menor depuração", "POR"),
        ("O genótipo AR está associado a variabilidade na resposta", "AR"),
        ("variantes do gene ADA associadas a deficiência enzimática", "ADA"),
        ("a expressão génica de TES não foi estudada", "TES"),
    ]
    for texto, simbolo in casos:
        assert count(texto, simbolo) >= 1, f"{simbolo}: {texto}"


def test_repeated_legitimate_mentions_are_all_counted():
    texto = ("O gene POR codifica a P450 oxidoreductase. Variantes de POR "
             "alteram a atividade enzimática.")
    assert count(texto, "POR") == 2


def test_mixed_text_is_over_inclusive_within_the_window():
    """Limitação conhecida, e deliberadamente aceite.

    Quando uma preposição e uma menção genética estão a menos de 160
    caracteres uma da outra, a janela de contexto não as distingue e ambas
    contam. O texto abaixo dá 2 em vez de 1.

    É um compromisso assumido: reduzir a janela pouparia estes casos mas
    perderia menções legítimas em que o vocabulário genético está no início
    do parágrafo e o símbolo mais à frente — que são mais frequentes.

    Escala do que se ganha: sem qualquer regra, "POR" contava 2 572
    ocorrências no corpus de 71 documentos, das quais nenhuma era o gene. Com
    a regra, contam-se apenas as que têm maiúsculas E contexto genético.
    Sobrecontar num parágrafo misto é ordens de grandeza melhor.
    """
    texto = ("Administrado POR via intravenosa. Separadamente, o polimorfismo "
             "do gene POR influencia a depuração.")
    assert count(texto, "POR") >= 1

    # Afastadas, a preposição deixa de ser contada.
    afastado = ("Administrado POR via intravenosa. " + "Texto clínico. " * 20 +
                "O polimorfismo do gene POR influencia a depuração.")
    assert count(afastado, "POR") == 1


# ==========================================================================
# Guardas
# ==========================================================================
def test_unambiguous_pgx_genes_are_not_in_the_list():
    """Genes PGx curtos mas inequívocos não podem ser afetados pela regra."""
    for gene in ("TPMT", "DPYD", "COMT", "CFTR", "MTHFR", "NAT2", "RYR1",
                 "CYP2D6", "SLCO1B1", "VKORC1", "G6PD", "ABCG2"):
        assert gene not in AMBIGUOUS, f"{gene} não devia exigir contexto"


def test_the_measured_colliders_are_listed():
    for gene in ("POR", "AR", "TES", "ADA", "ADO", "INA", "PELO", "GEM"):
        assert gene in AMBIGUOUS, f"{gene} foi medido como colidente"


def test_empty_inputs():
    assert count("", "POR") == 0
    assert count("texto qualquer", "") == 0


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
