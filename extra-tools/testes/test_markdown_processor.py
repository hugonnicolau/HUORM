"""
Testes da extração do grupo farmacoterapêutico.

O regex anterior exigia a grafia literal "Grupo farmacoterapêutico" e cortava o
valor na primeira quebra de linha. Medido nos 632 RCMs da pasta RCMs2:

    regex antigo    590/632 documentos  — e 77% dos apanhados vinham truncados
    regex corrigido 626/632

A truncagem era o problema maior: fragmentava 121 grupos reais do Infarmed em
473 rótulos textuais distintos, inflacionando a folha de análise por grupo.

    python extra-tools/testes/test_markdown_processor.py
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "RCMprocessor" / "markdown_processor.py"


def _load_class():
    """Carrega MarkdownProcessor sem exigir langchain_text_splitters."""
    stub = types.ModuleType("langchain_text_splitters")

    class MarkdownHeaderTextSplitter:  # noqa: D401
        def __init__(self, *a, **k):
            pass

        def split_text(self, text):
            return []

    stub.MarkdownHeaderTextSplitter = MarkdownHeaderTextSplitter
    sys.modules.setdefault("langchain_text_splitters", stub)

    namespace: dict = {}
    exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), namespace)
    return namespace["MarkdownProcessor"]


MarkdownProcessor = _load_class()


def extract(text: str):
    return MarkdownProcessor(text)._extrair_grupo_farmacoterapeutico()


# ==========================================================================
# Variantes de grafia observadas no corpus real
# ==========================================================================
def test_canonical_spelling():
    grupo, codigo = extract("Grupo farmacoterapêutico: 2.9.3 Antidepressores.")
    assert grupo.startswith("2.9.3")
    assert codigo == "2.9.3"


def test_plural_form():
    """Atarax, Aspirina GR, Diltiem: "Grupos farmacoterapêuticos"."""
    grupo, codigo = extract(
        "Grupos farmacoterapêuticos: 2.9.1 – Sistema nervoso central."
    )
    assert grupo is not None and codigo == "2.9.1"


def test_classificacao_instead_of_grupo():
    """Eutirox, Mirena, Xalatan: "Classificação farmacoterapêutica"."""
    grupo, codigo = extract(
        "Classificação farmacoterapêutica: 8.3 - Hormonas da tiroide."
    )
    assert grupo is not None and codigo == "8.3"


def test_classe_and_categoria():
    for label in ("Classe farmacoterapêutica", "Categoria farmacoterapêutica"):
        grupo, codigo = extract(f"{label}: 6.6 - Suplementos enzimáticos.")
        assert grupo is not None, label
        assert codigo == "6.6", label


def test_accent_and_hyphen_variant():
    """Acalka, NEBILET, Varfine: "Grupo fármaco-terapêutico"."""
    grupo, codigo = extract(
        "Grupo fármaco-terapêutico: 4.3.1.2 antivitaminicos K"
    )
    assert grupo is not None and codigo == "4.3.1.2"


def test_hyphen_with_spaces():
    """Tansulosina: "Grupo Fármaco - Terapêutico"."""
    grupo, codigo = extract(
        "Grupo Fármaco - Terapêutico: 7.4.2.1 Aparelho geniturinário."
    )
    assert grupo is not None and codigo == "7.4.2.1"


def test_without_colon():
    """Varfine escreve o grupo sem dois-pontos."""
    grupo, codigo = extract("Grupo Fármaco-Terapêutico 4.3.1.2 antivitaminicos K")
    assert grupo is not None and codigo == "4.3.1.2"


# ==========================================================================
# Truncagem — o problema de maior impacto
# ==========================================================================
def test_multiline_group_is_not_truncated():
    """Os nomes do Infarmed ocupam 2-3 linhas; cortar na primeira fragmentava-os."""
    text = (
        "5.1 Propriedades farmacodinâmicas\n\n"
        "Classificação farmacoterapêutica: 8.5.1.2 - Hormonas e medicamentos\n"
        "usados no tratamento das doenças endócrinas. Hormonas sexuais.\n"
        "Estrogénios e progestagénios.\n"
        "Código ATC: G03AA10\n"
    )
    grupo, codigo = extract(text)
    assert codigo == "8.5.1.2"
    assert "Estrogénios e progestagénios" in grupo, "o valor foi truncado"


def test_stops_before_atc_code():
    grupo, _ = extract(
        "Grupo farmacoterapêutico: 2.9.3 Antidepressores. Código ATC: N06AB06"
    )
    assert "N06AB06" not in grupo
    assert "ATC" not in grupo


def test_stops_before_atc_even_when_glued():
    """Dorzolamida: a extração cola as palavras — "dorzolamidaCódigo ATC"."""
    grupo, _ = extract(
        "Classificação Farmacoterapêutica: Preparações antiglaucomatosas, "
        "dorzolamidaCódigo ATC: S01EC03"
    )
    assert "ATC" not in grupo
    assert "S01EC03" not in grupo


def test_atc_before_group_is_handled():
    """Acalka escreve o código ATC ANTES do grupo."""
    text = (
        "5.1 Propriedades farmacodinâmicas\n"
        "Código ATC: G04B\n"
        "Grupo fármaco-terapêutico: VIII-4 Acidificantes e alcalinizantes\n"
    )
    grupo, _ = extract(text)
    assert "Acidificantes" in grupo


def test_line_break_hyphenation_is_repaired():
    """Actifed: "Anti-\\nhistamínicos" tem de voltar a "Anti-histamínicos"."""
    text = (
        "Grupo farmacoterapêutico: 10.1.1 – Medicação antialérgica. Anti-\n"
        "histamínicos H1 sedativos.\n"
    )
    grupo, _ = extract(text)
    assert "Anti-histamínicos" in grupo


def test_stops_at_paragraph_end():
    text = (
        "Grupo farmacoterapêutico: 2.9.3 Antidepressores.\n\n"
        "A sertralina é um inibidor selectivo da recaptação da serotonina.\n"
    )
    grupo, _ = extract(text)
    assert "sertralina" not in grupo.lower()


# ==========================================================================
# Código hierárquico — a chave de agrupamento
# ==========================================================================
def test_hierarchical_code_extracted():
    for text, expected in [
        ("Grupo farmacoterapêutico: 2.9.3 Antidepressores", "2.9.3"),
        ("Grupo farmacoterapêutico: 8.5.1.2 Hormonas", "8.5.1.2"),
        ("Grupo farmacoterapêutico: 3.7 Antidislipidémicos", "3.7"),
    ]:
        _, codigo = extract(text)
        assert codigo == expected, text


def test_group_without_code():
    """Nem todos os RCMs numeram o grupo (ex. Forlax: "Laxantes osmóticos")."""
    grupo, codigo = extract("Classe farmacoterapêutica: Laxantes osmóticos")
    assert grupo == "Laxantes osmóticos"
    assert codigo is None


def test_absent_label_returns_none():
    grupo, codigo = extract("5.1 Propriedades farmacodinâmicas\n\nA substância…")
    assert grupo is None and codigo is None


def test_empty_text():
    assert extract("") == (None, None)


# ==========================================================================
# Normalização do código hierárquico
#
# O código é a chave de agrupamento. Quando a conversão do PDF deixa espaços
# a rodear os pontos, o regex ancorado em ^\d+(\.\d+)* só apanha o primeiro
# dígito: o Ácido Fólico ficava em "4" em vez de "4.1.2", isto é, no topo da
# hierarquia (Sangue) em vez do grupo real. Medido em 71 documentos: 1 caso.
# ==========================================================================

def test_spaced_code_is_compacted():
    """Valor real do RCM do Ácido Fólico."""
    grupo, codigo = extract(
        "Grupo farmacoterapêutico: 4 . 1 . 2 -Sangue . Antianémicos . "
        "Medicamentos para tratamento das anemias megaloblásticas\n\n"
        "Código ATC: B03BB01"
    )
    assert codigo == "4.1.2", f"código truncado no primeiro nível: {codigo!r}"
    assert grupo.startswith("4.1.2")
    assert "anemias megaloblásticas" in grupo


def test_spacing_variants_of_the_code():
    for texto, esperado in [
        ("Grupo farmacoterapêutico: 8 .5 .1 .2 Hormonas", "8.5.1.2"),
        ("Grupo farmacoterapêutico: 2. 9. 3 Psicofármacos", "2.9.3"),
        ("Grupo farmacoterapêutico: 4 .1. 2 Sangue", "4.1.2"),
    ]:
        _, codigo = extract(texto)
        assert codigo == esperado, f"{texto!r} deu {codigo!r}"


def test_clean_codes_are_untouched():
    """A correção não pode alterar os códigos que já vinham bem."""
    for texto, esperado in [
        ("Grupo farmacoterapêutico: 2.9.3 Antidepressores", "2.9.3"),
        ("Grupo farmacoterapêutico: 6.2.2.3 Aparelho digestivo", "6.2.2.3"),
        ("Grupo farmacoterapêutico: 2.12 Analgésicos estupefacientes", "2.12"),
        ("Classificação farmacoterapêutica: 8.3 - Hormonas da tiroide", "8.3"),
    ]:
        _, codigo = extract(texto)
        assert codigo == esperado, f"{texto!r} deu {codigo!r}"


def test_roman_numeral_group_still_has_no_code():
    """Não inventar um código onde a numeração não é decimal."""
    grupo, codigo = extract(
        "Grupo fármaco-terapêutico: VIII-4 Acidificantes e alcalinizantes"
    )
    assert codigo is None
    assert "Acidificantes" in grupo


def test_label_spacing_before_punctuation_is_cleaned():
    """Valor real do RCM do omeprazol: espaço antes do ponto."""
    grupo, codigo = extract(
        "Grupo farmacoterapêutico: 6.2.2.3. Aparelho Digestivo . "
        "Antiácidos e antiulcerosos. Inibidores da bomba de protões"
    )
    assert codigo == "6.2.2.3"
    assert " ." not in grupo, f"espaço antes do ponto persiste: {grupo!r}"
    assert "Aparelho Digestivo. Antiácidos" in grupo


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
