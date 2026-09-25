"""
Testes do reconhecimento de secções por título e da tradução de símbolos.

Dois problemas observados no lote de anestésicos (54 RCM):

  * O RCM da cetamina numera as subsecções de 4.x como secções de topo:
    "5. Interações medicamentosas", "8. Efeitos indesejáveis". Existiam dois
    "5." no mesmo documento. As secções 4.2, 4.5 e 4.8 nunca eram encontradas,
    apesar de o texto estar presente — três das secções onde a farmacogenómica
    mais aparece.

  * PDFs com a fonte Symbol produzem códigos da Private Use Area em vez dos
    caracteres reais: "16-160 [U+F06D]g/ml" em vez de "16-160 µg/ml".

    python extra-tools/testes/test_section_fallback.py
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "RCMprocessor" / "markdown_processor.py"


def _load():
    stub = types.ModuleType("langchain_text_splitters")

    class MarkdownHeaderTextSplitter:
        def __init__(self, *a, **k):
            pass

        def split_text(self, text):
            return []

    stub.MarkdownHeaderTextSplitter = MarkdownHeaderTextSplitter
    sys.modules.setdefault("langchain_text_splitters", stub)
    ns: dict = {}
    exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), ns)
    return ns["MarkdownProcessor"]


MP = _load()


# ==========================================================================
# Reconhecimento por título — o que DEVE ser apanhado
# ==========================================================================
def test_normative_titles_are_recognised():
    esperado = {
        "Posologia e modo de administração": "4.2",
        "Posologia": "4.2",
        "Contraindicações": "4.3",
        "Contra-indicações": "4.3",
        "Advertências e precauções especiais de utilização": "4.4",
        "Interações medicamentosas e outras formas de interação": "4.5",
        "Interações com outros medicamentos": "4.5",
        "Efeitos indesejáveis": "4.8",
        "Propriedades farmacodinâmicas": "5.1",
        "Propriedades farmacocinéticas": "5.2",
    }
    for titulo, numero in esperado.items():
        assert MP._numero_por_titulo(titulo) == numero, titulo


def test_recognition_is_case_insensitive():
    assert MP._numero_por_titulo("EFEITOS INDESEJÁVEIS") == "4.8"
    assert MP._numero_por_titulo("propriedades farmacocinéticas") == "5.2"


# ==========================================================================
# O que NÃO pode ser apanhado
# ==========================================================================
def test_other_sections_are_not_captured():
    """As restantes secções do RCM não interessam à análise PGx."""
    fora = [
        "Indicações terapêuticas",
        "Fertilidade, gravidez e aleitamento",
        "Sobredosagem",
        "Efeitos sobre a capacidade de conduzir e utilizar máquinas",
        "Lista dos excipientes",
        "Incompatibilidades",
        "Prazo de validade",
        "Precauções especiais de conservação",
        "Natureza e conteúdo do recipiente",
        "Precauções especiais de eliminação e manuseamento",
        "Dados de segurança pré-clínica",
        "Titular da Autorização de Introdução no Mercado",
        "Nome do medicamento",
        "Composição qualitativa e quantitativa",
        "Forma farmacêutica",
    ]
    for titulo in fora:
        assert MP._numero_por_titulo(titulo) is None, f"capturou {titulo!r}"


def test_subheadings_are_not_mistaken_for_sections():
    """Subtítulos dentro de uma secção não são a secção.

    "Posologia pediátrica recomendada" vive dentro de 4.2; capturá-la como
    sendo 4.2 truncaria a secção verdadeira.
    """
    for titulo in ["Posologia pediátrica recomendada",
                   "Posologia em doentes idosos",
                   "Advertências gerais",
                   "Interações com alimentos",
                   "Propriedades organoléticas"]:
        assert MP._numero_por_titulo(titulo) is None, f"capturou {titulo!r}"


def test_empty_and_noise():
    for titulo in ["", "   ", "|", "3.", "..."]:
        assert MP._numero_por_titulo(titulo) is None


# ==========================================================================
# Símbolos da Private Use Area
# ==========================================================================
def test_symbol_font_characters_are_translated():
    """Casos reais retirados do lote de anestésicos."""
    casos = [
        ("incidência de  5%", "≥"),
        ("concentrações de 16-160 g/ml", "µ"),
        ("24 horas a 25 C", "°"),
        ("2,5  1 l/kg", "±"),
        ("até  10 kg", "≤"),
        (" primeiro item", "•"),
        ("1-(-metilbenzilo)", "α"),
    ]
    for original, esperado in casos:
        assert esperado in MP._traduzir_simbolos(original), original


def test_no_private_use_characters_survive():
    """Códigos sem equivalente conhecido não podem ficar no texto."""
    texto = MP._traduzir_simbolos("antes   depois")
    assert not re.search(r"[-]", texto)


def test_translation_preserves_normal_text():
    original = "O CYP2C9*3 reduz a depuração em 26% (ver secção 5.2)."
    assert MP._traduzir_simbolos(original) == original


def test_translation_handles_empty():
    assert MP._traduzir_simbolos("") == ""
    assert MP._traduzir_simbolos(None) is None


# ==========================================================================
# Numeração com ponto final, e remissões promovidas a título
#
# Casos reais do RCM do lornoxicam (formato de 2007). Sem estas duas
# correções perdiam-se a 4.5 e a 5.1 — as duas secções onde a
# farmacogenómica aparece com mais frequência.
# ==========================================================================

def _norm(linha: str) -> str:
    """Normalised form of a single line, as _normalizar_titulos produces it."""
    return MP(linha).get_markdown_normalizado().strip()


def test_trailing_dot_in_section_number():
    """'4.2. Posologia' e '4.5.Interacções' são grafias correntes."""
    for linha, esperado in [
        ("4.2. Posologia e modo de administração", "4.2"),
        ("4.5.Interacções medicamentosas e outras formas de interação", "4.5"),
        ("5.1.Propriedades farmacodinâmicas", "5.1"),
        ("5.2. Propriedades farmacocinéticas", "5.2"),
    ]:
        out = _norm(linha)
        assert out.startswith(f"### {esperado} "), f"{linha!r} deu {out!r}"


def test_cross_reference_is_not_promoted():
    """'5.2 Biotransformação).' é o fim de '(ver secção 5.2 Biotransformação)'.

    Promovê-lo substituía a 5.2 real por um fragmento de frase, e o conteúdo
    analisado passava a ser o texto que vinha depois da remissão — pior do que
    perder a secção, porque parece completa.
    """
    for linha in ["5.2 Biotransformação).",
                  "4.5). Recomenda-se a vigilância clínica.",
                  "4.8) e da 4.9."]:
        out = _norm(linha)
        assert not out.startswith("###"), f"{linha!r} foi promovido: {out!r}"


def test_balanced_parentheses_in_title_survive():
    """Um título legítimo pode ter parênteses, desde que equilibrados."""
    out = _norm("4.4 Advertências (ver secção 4.8) e precauções especiais")
    assert out.startswith("### 4.4 "), out


def test_duplicated_section_number_from_docling_list():
    """"2. 2.COMPOSIÇÃO" tem de dar secção 2, não secção 2.2.

    O RCM do Fludex (indapamida, INFARMED 28-01-2022) imprime
    "2.COMPOSIÇÃO QUALITATIVA E QUANTITATIVA" sem espaço a seguir ao ponto.
    O Docling trata os títulos de topo como lista ordenada, acrescenta o seu
    próprio marcador e o resultado é "2. 2.COMPOSIÇÃO". Lido como "2.2", a
    secção 2 deixa de existir — e é dela que sai a substância ativa, que
    ancora todos os cruzamentos externos. O documento saiu INCOMPLETO nos
    três modelos testados: a causa é a conversão, não o modelo.
    """
    out = _norm("2. 2.COMPOSIÇÃO QUALITATIVA E QUANTITATIVA")
    assert out.startswith("# 2. COMPOSIÇÃO"), out
    assert "2.2" not in out, out


def test_real_subsection_after_marker_is_untouched():
    """O colapso só actua quando o número se repete igual."""
    assert _norm("5. 5.2 Propriedades farmacocinéticas").startswith("### 5.2 ")
    assert _norm("4. 4.5 Interações medicamentosas").startswith("### 4.5 ")


def test_number_followed_by_digit_is_not_collapsed():
    """"2. 2,5 mg" e "2. 2.5 mg" são dose, não numeração."""
    for linha in ("2. 2.5 mg de indapamida", "2. 2,5 mg de indapamida"):
        out = _norm(linha)
        assert "mg" in out, out


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
