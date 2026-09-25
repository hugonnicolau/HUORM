"""
Testes de regressão das correções de comportamento (passagem 1).

Não precisam de rede, de Ollama, nem dos ficheiros de dados: as funções
testadas são puras. Correm em segundo.

    python -m pytest RCMprocessor/tests/test_pipeline_fixes.py -v
    python extra-tools/testes/test_pipeline_fixes.py          # sem pytest

Cada teste documenta o bug que motivou a correção, com o caso concreto que o
demonstrou. Se algum destes falhar no futuro, a regressão é conhecida.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------
# As funções sob teste são estáticas/puras, mas vivem num módulo que importa
# ollama, dotenv e docling. Para não exigir essas dependências, extraem-se as
# implementações reais do ficheiro fonte.
# --------------------------------------------------------------------------
SOURCE = (Path(__file__).resolve().parents[2] / "RCMprocessor" / "pharmacogenomics_evaluator.py")


def _load_functions() -> dict:
    """Compila apenas os métodos puros, sem importar o módulo inteiro."""
    text = SOURCE.read_text(encoding="utf-8")
    namespace: dict = {
        "re": re,
        "html": __import__("html"),
        "unicodedata": unicodedata,
        "json": __import__("json"),
        # Constantes de classe referidas pelos métodos extraídos.
        "PharmacogenomicsEvaluator": type(
            "Stub", (), {"_INVISIBLE": dict.fromkeys(map(ord, "­​‌‍﻿"), None)}
        ),
    }

    wanted = (
        "_is_affirmative",
        "_iter_balanced_spans",
        "_extract_json_object",
        "_is_token_boundary",
        "_count_non_overlapping",
        "_canonical_text_for_counting",
        "_normalise_for_verbatim_check",
        "_fidelity",
        "_is_verbatim",
    )

    lines = text.split("\n")
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if any(stripped.startswith(f"def {name}(") for name in wanted):
            start = i
            # inclui o decorador imediatamente acima, se existir
            if start and lines[start - 1].strip().startswith("@"):
                start -= 1
            indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) <= indent:
                    break
                j += 1
            block = "\n".join(lines[start:j])
            blocks.append("\n".join(l[indent:] if l[:indent].isspace() or not l.strip()
                                    else l.lstrip() for l in block.split("\n")))
            i = j
            continue
        i += 1

    src = "\n\n".join(b.replace("@staticmethod\n", "") for b in blocks)
    src = src.replace("self.REASSEMBLY_MIN_COVERAGE", "0.85")
    src = src.replace("self._", "_").replace("self, ", "").replace("(self)", "()")
    exec(compile(src, "extracted", "exec"), namespace)
    return namespace


NS = _load_functions()
is_affirmative = NS["_is_affirmative"]
extract_json_object = NS["_extract_json_object"]
count_non_overlapping = NS["_count_non_overlapping"]
canonical = NS["_canonical_text_for_counting"]
is_verbatim = NS["_is_verbatim"]
fidelity = NS["_fidelity"]


# ==========================================================================
# Integridade dos excertos — texto_original tem de ser literal do RCM
# ==========================================================================
def test_verbatim_excerpt_is_accepted():
    block = ("Os doentes metabolizadores lentos de CYP2D6 apresentam "
             "concentrações plasmáticas superiores.")
    assert is_verbatim("metabolizadores lentos de CYP2D6", block) is True


def test_paraphrased_excerpt_is_rejected():
    """O prompt proíbe reformular; isto verifica em vez de assumir.

    Um excerto que não conste do bloco foi parafraseado ou inventado, e não
    pode ser citado como texto do RCM nem alimentar a contagem de menções.
    """
    block = ("Os doentes metabolizadores lentos de CYP2D6 apresentam "
             "concentrações plasmáticas superiores.")
    assert fidelity("Doentes com CYP2D6 lento têm níveis mais altos", block) \
        == "nao_encontrado"


# ==========================================================================
# Artefactos da extração — medidos nos 17 RCMs do subset
# ==========================================================================
def test_html_entities_do_not_break_verbatim():
    """O docling deixa &gt; e &lt; por converter; o modelo devolve > e <."""
    block = "Portadores do alelo c.521T &gt; C do gene SLCO1B1 têm menor atividade."
    assert fidelity("alelo c.521T > C do gene SLCO1B1", block) == "verbatim"


def test_soft_hyphen_is_ignored():
    """A extração injeta U+00AD ('di­a' em vez de 'dia')."""
    block = "A rifampicina 600 mg por dia reduziu a exposição."
    assert fidelity("rifampicina 600 mg por di­a reduziu", block) == "verbatim"


def test_lost_hyphen_is_tolerated():
    """O docling cola palavras: 'recémnascidos'. O modelo restaura o hífen."""
    block = "a formação via CYP2D6 aumenta continuamente em recémnascidos."
    assert fidelity("aumenta continuamente em recém-nascidos", block) == "verbatim"


def test_reassembled_excerpt_is_distinguished():
    """Conteúdo real, mas de partes não contíguas — não é invenção.

    Acontece quando o docling emite tabelas fora da ordem de leitura. Dois dos
    39 excertos do subset caíram neste caso; nenhum foi inventado.
    """
    block = ("Primeira parte relevante sobre o metabolismo do CYP2D6 e a "
             "necessidade de ajuste da dose em metabolizadores lentos. "
             "TEXTO INTERMÉDIO IRRELEVANTE QUE O MODELO SALTOU POR COMPLETO. "
             "Segunda parte sobre os exemplos de fármacos que podem interagir "
             "com esta via metabólica e alterar a exposição sistémica.")
    excerpt = ("Primeira parte relevante sobre o metabolismo do CYP2D6 e a "
               "necessidade de ajuste da dose em metabolizadores lentos. "
               "Segunda parte sobre os exemplos de fármacos que podem interagir "
               "com esta via metabólica e alterar a exposição sistémica.")
    assert fidelity(excerpt, block) == "recomposto"


def test_reassembly_does_not_mask_invention():
    """Metade real e metade inventada tem de continuar a ser rejeitada."""
    block = "Os doentes metabolizadores lentos de CYP2D6 requerem ajuste da dose."
    excerpt = ("Os doentes metabolizadores lentos de CYP2D6 requerem ajuste da dose. "
               "O gene CYP2C19 também influencia esta via de forma determinante.")
    assert fidelity(excerpt, block) == "nao_encontrado"


def test_verbatim_tolerates_whitespace_differences():
    block = "Os doentes\n  metabolizadores   lentos de CYP2D6 requerem ajuste."
    assert is_verbatim("metabolizadores lentos de CYP2D6", block) is True


def test_verbatim_tolerates_line_break_hyphenation():
    block = "Recomenda-se precaução em doentes anti-\ncoagulados com varfarina."
    assert is_verbatim("doentes anti-coagulados com varfarina", block) is True


def test_verbatim_is_case_insensitive():
    block = "O gene CYP2C19 influencia a resposta."
    assert is_verbatim("o gene cyp2c19 influencia", block) is True


def test_verbatim_rejects_empty():
    assert is_verbatim("", "bloco qualquer") is False
    assert is_verbatim("excerto", "") is False


# ==========================================================================
# BUG 1 — classificação PGx por substring "sim"
# ==========================================================================
def test_negative_answers_containing_sim_substring():
    """"Não ... simplesmente" era classificado como Sim.

    O teste antigo era `"sim" in answer.lower()`, que dá positivo dentro de
    "simplesmente", "similar", "assim" e "simultaneamente".
    """
    negatives = [
        "Não. O texto refere-se simplesmente ao metabolismo hepático.",
        "Não, trata-se de uma interação similar à descrita acima.",
        "Não. Assim sendo, não há informação farmacogenómica.",
        "Não existem menções simultâneas a genes.",
        "Não",
        "não.",
        "",
    ]
    for answer in negatives:
        assert is_affirmative(answer) is False, f"falso positivo: {answer!r}"


def test_affirmative_answers():
    for answer in ["Sim", "sim", "Sim.", "SIM", "Sim, existe informação PGx."]:
        assert is_affirmative(answer) is True, f"falso negativo: {answer!r}"


def test_negation_takes_precedence_on_first_line():
    assert is_affirmative("Não, embora exista algo similar a PGx.") is False


# ==========================================================================
# BUG 2 — parser de JSON guloso
# ==========================================================================
def test_two_json_objects_in_response():
    """re.search(r"\\{.*\\}", DOTALL) apanhava do primeiro '{' ao último '}'."""
    raw = 'Aqui está: {"excertos": []}\n\nEspero ter ajudado. {"nota": "fim"}'
    assert extract_json_object(raw) == {"excertos": []}


def test_json_inside_markdown_fence():
    assert extract_json_object('```json\n{"excertos": []}\n```') == {"excertos": []}


def test_json_with_trailing_prose():
    raw = '{"excertos": [{"texto_original": "CYP2D6"}]}\nNota final.'
    assert extract_json_object(raw)["excertos"][0]["texto_original"] == "CYP2D6"


def test_braces_inside_strings_do_not_break_parsing():
    raw = '{"texto_original": "o valor {x} aparece no RCM"}'
    assert extract_json_object(raw)["texto_original"] == "o valor {x} aparece no RCM"


def test_invalid_json_returns_none():
    assert extract_json_object("não é json nenhum") is None


# ==========================================================================
# BUG 3 — contagem de star alleles por substring
# ==========================================================================
def test_short_allele_not_counted_inside_longer_allele():
    """CYP2D6*1 era contado dentro de *10, *17 e *100.

    Caso real: o alelo selvagem CYP2D6*1 e os alelos *10/*17 estão entre os
    mais frequentes em RCMs, logo o erro atingia as entidades mais comuns.
    """
    text = canonical("CYP2D6*10, CYP2D6*17, CYP2D6*1, CYP2D6*100")
    assert count_non_overlapping(text, canonical("CYP2D6*1")) == 1
    assert count_non_overlapping(text, canonical("CYP2D6*10")) == 1
    assert count_non_overlapping(text, canonical("CYP2D6*17")) == 1


def test_repeated_allele_counted_once_per_occurrence():
    text = canonical("CYP2D6*10 e mais tarde CYP2D6*10 outra vez")
    assert count_non_overlapping(text, canonical("CYP2D6*10")) == 2


def test_duplication_allele_is_distinct():
    """CYP2D6*2 não deve ser contado dentro de CYP2D6*2xN."""
    text = canonical("O doente tem CYP2D6*2xN.")
    assert count_non_overlapping(text, canonical("CYP2D6*2")) == 0


def test_spacing_variants_still_match():
    """A normalização tem de continuar a unir 'CYP2D6 *1' e 'CYP2D6*1'."""
    for variant in ["CYP2D6 *1.", "CYP2D6*1.", "cyp2d6 * 1."]:
        assert count_non_overlapping(canonical(variant), canonical("CYP2D6*1")) == 1


def test_neighbouring_tokens_are_not_glued():
    """Antes removiam-se todos os espaços, colando tokens vizinhos."""
    text = canonical("CYP2D6*1 e CYP2C19*2")
    assert count_non_overlapping(text, canonical("CYP2D6*1")) == 1
    assert count_non_overlapping(text, canonical("CYP2C19*2")) == 1


def test_hla_hyphen_preserved():
    text = canonical("HLA-B*1502 confirmado")
    assert count_non_overlapping(text, canonical("HLA-B*1502")) == 1


def _hla_forms(canonical_allele: str) -> list[str]:
    """Réplica de _star_allele_count_forms para o caso HLA."""
    forms = [canonical_allele]
    if canonical_allele.startswith("HLA-") and "*" in canonical_allele:
        forms.append("HLA" + canonical_allele[4:])
        forms.append("HLA " + canonical_allele[4:])
    out, seen = [], set()
    for f in forms:
        k = canonical(f)
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def test_hla_spelling_variants_all_counted():
    """As três grafias de HLA-B*1502 têm de contar, sem duplicar.

    A forma com espaço passou a ser precisa quando a normalização deixou de
    remover todos os espaços — antes "HLA B*1502" colapsava sozinho.
    """
    forms = _hla_forms("HLA-B*1502")
    for text, expected in [
        ("Alelo HLA-B*1502 presente.", 1),
        ("Alelo HLAB*1502 presente.", 1),
        ("Alelo HLA B*1502 presente.", 1),
        ("HLA-B*1502, HLAB*1502 e HLA B*1502.", 3),
    ]:
        total = sum(count_non_overlapping(canonical(text), f) for f in forms)
        assert total == expected, f"{text!r}: {total} != {expected}"


def test_different_hla_alleles_not_confused():
    text = canonical("HLA-B*1502 e HLA-B*5801")
    assert sum(count_non_overlapping(text, f) for f in _hla_forms("HLA-B*1502")) == 1
    assert sum(count_non_overlapping(text, f) for f in _hla_forms("HLA-B*5801")) == 1


# ==========================================================================
# BUG 4 — genes sem guideline_ids no output compacto
# ==========================================================================
def test_compact_genes_include_guideline_ids():
    """Genes eram a única categoria sem guideline_ids no Document_Unique.

    Consequência medida no corpus de 643 RCMs: 222 de 222 linhas de gene
    saíam com "Tem informação ClinPGx? = Não" e a métrica "Menções de genes
    com guidelines" dava 0, apesar de CYP2D6 aparecer em 42 documentos.
    """
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("compact_genes.append(")
    block = source[start:start + 2000]
    assert '"guideline_ids"' in block, (
        "compact_genes voltou a perder guideline_ids"
    )


def test_all_compact_categories_expose_guideline_ids():
    source = SOURCE.read_text(encoding="utf-8")
    for name in ("compact_genes", "compact_star_alleles",
                 "compact_diplotypes", "compact_rsids"):
        start = source.index(f"{name}.append(")
        assert '"guideline_ids"' in source[start:start + 2000], (  # noqa: E501
            f"{name} não expõe guideline_ids"
        )


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
