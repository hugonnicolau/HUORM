"""
Testes da avaliação de tabelas.

As tabelas dos RCMs eram removidas do `content` pelo MarkdownProcessor e
depois nunca lidas pelo avaliador. Medido no subset de 17 documentos: das 497
linhas de tabela do markdown, 10 continham termos farmacogenómicos e nove
delas eram do siponimod — os seis diplótipos CYP2C9*1*1 a *3*3, com
frequências populacionais e impacto na exposição sistémica.

O siponimod exige genotipagem CYP2C9 antes de prescrever. O pipeline detetava
o gene pelo texto corrido, mas perdia os diplótipos, que são a informação
acionável.

    python RCMprocessor/tests/test_table_evaluation.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "pharmacogenomics_evaluator.py"


def _load(names: tuple[str, ...]) -> dict:
    """Extrai métodos puros sem importar o módulo (que precisa de ollama)."""
    text = SOURCE.read_text(encoding="utf-8")
    namespace: dict = {
        "re": re,
        "html": __import__("html"),
        "unicodedata": unicodedata,
        "PharmacogenomicsEvaluator": type(
            "Stub", (), {"_INVISIBLE": dict.fromkeys(map(ord, "­​‌‍﻿"), None)}
        ),
    }
    lines = text.split("\n")
    blocks, i = [], 0
    while i < len(lines):
        if any(lines[i].strip().startswith(f"def {n}(") for n in names):
            start = i - 1 if lines[i - 1].strip().startswith("@") else i
            indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) <= indent:
                    break
                j += 1
            blocks.append("\n".join(l[indent:] if l[:indent].isspace() or not l.strip()
                                    else l.lstrip() for l in "\n".join(lines[start:j]).split("\n")))
            i = j
            continue
        i += 1
    src = "\n\n".join(b.replace("@staticmethod\n", "") for b in blocks)
    src = src.replace("self.REASSEMBLY_MIN_COVERAGE", "0.85")
    src = src.replace("cls.BLOCK_MAX_CHARS", "6000").replace("cls, ", "")
    src = src.replace("@classmethod\n", "")
    src = src.replace("self._", "_").replace("self, ", "").replace("(self)", "()")
    exec(compile(src, "extracted", "exec"), namespace)
    return namespace


NS = _load((
    "_table_units",
    "_normalise_for_verbatim_check",
    "_fidelity",
    "_canonical_text_for_counting",
    "_is_token_boundary",
    "_count_non_overlapping",
))
table_units = NS["_table_units"]
fidelity = NS["_fidelity"]
canonical = NS["_canonical_text_for_counting"]
count = NS["_count_non_overlapping"]


# A tabela real do RCM do siponimod, tal como o docling a produz.
SIPONIMOD = {
    "numero": "4",
    "titulo": ("Efeito do genótipo CYP2C9 na depuração sistémica (CL/F) e "
               "exposição sistémica de siponimod"),
    "texto": (
        "|-----------------------------|--------|---------|--------|-----|\n"
        "| Metabolizadores extensos    | Metabolizadores extensos | | | |\n"
        "| CYP2C9*1*1                  | 62-65  | 3,1-3,3 | 100    | -   |\n"
        "| CYP2C9*1*2                  | 20-24  | 3,1-3,3 | 99-100 | -   |\n"
        "| Metabolizadores intermédios | | | | |\n"
        "| CYP2C9*2*2                  | 1-2    | 2,5-2,6 | 80     | 25  |\n"
        "| CYP2C9*1*3                  | 9-12   | 1,9-2,1 | 62-65  | 61  |\n"
        "| Metabolizadores lentos      | | | | |\n"
        "| CYP2C9*2*3                  | 1,4-1,7| 1,6-1,8 | 52-55  | 91  |\n"
        "| CYP2C9*3*3                  | 0,3-0,4| 0,9     | 26     | 284 |"
    ),
}


# ==========================================================================
def test_table_becomes_its_own_unit():
    units = table_units([SIPONIMOD])
    assert len(units) == 1
    origem, texto = units[0]
    assert origem == "tabela_4"
    assert "CYP2C9*3*3" in texto


def test_caption_travels_with_the_body():
    """Sem a legenda, o modelo vê uma grelha de números sem significado."""
    _, texto = table_units([SIPONIMOD])[0]
    assert "Efeito do genótipo CYP2C9" in texto
    assert texto.index("Efeito do genótipo") < texto.index("CYP2C9*1*1")


def test_all_six_diplotypes_present_in_the_unit():
    """Os seis diplótipos são o núcleo PGx do siponimod."""
    _, texto = table_units([SIPONIMOD])[0]
    for d in ("CYP2C9*1*1", "CYP2C9*1*2", "CYP2C9*2*2",
              "CYP2C9*1*3", "CYP2C9*2*3", "CYP2C9*3*3"):
        assert d in texto, f"{d} em falta"


def test_diplotypes_are_countable_in_the_table():
    """A contagem por origem tem de os encontrar, com fronteiras de token."""
    _, texto = table_units([SIPONIMOD])[0]
    alvo = canonical(texto)
    for d in ("CYP2C9*1*1", "CYP2C9*2*2", "CYP2C9*3*3"):
        assert count(alvo, canonical(d)) == 1, d
    # *1*2 não pode ser contado dentro de nada mais longo
    assert count(alvo, canonical("CYP2C9*1*2")) == 1


def test_excerpt_from_table_is_verbatim_against_the_table():
    """O ponto central: a fidelidade compara-se com a ORIGEM certa."""
    _, texto = table_units([SIPONIMOD])[0]
    excerto = "| CYP2C9*2*3 | 1,4-1,7| 1,6-1,8 | 52-55  | 91  |"
    assert fidelity(excerto, texto) == "verbatim"


def test_same_excerpt_against_content_would_fail():
    """Prova de que a origem importa.

    Se um excerto de tabela fosse verificado contra o `content` — de onde a
    tabela foi removida — seria marcado como invenção. Seria um falso alarme
    sistemático em todas as entidades vindas de tabelas.
    """
    content = ("Siponimod é extensamente metabolizado, principalmente pela "
               "CYP2C9 polimórfica, e a sua contribuição depende do genótipo.")
    excerto = "| CYP2C9*2*3 | 1,4-1,7| 1,6-1,8 | 52-55  | 91  |"
    assert fidelity(excerto, content) == "nao_encontrado"


def test_empty_and_malformed_tables_are_skipped():
    assert table_units(None) == []
    assert table_units([]) == []
    assert table_units([{"numero": "1", "titulo": "Sem corpo", "texto": ""}]) == []
    assert table_units(["não é dict"]) == []


def test_table_without_caption_still_works():
    units = table_units([{"numero": "7", "titulo": "", "texto": "| A | B |\n| 1 | 2 |"}])
    assert len(units) == 1
    assert units[0][0] == "tabela_7"
    assert units[0][1].startswith("Tabela 7")


def test_multiple_tables_keep_distinct_origins():
    units = table_units([
        SIPONIMOD,
        {"numero": "2", "titulo": "Reações adversas", "texto": "| X | Y |\n| 1 | 2 |"},
    ])
    assert [u[0] for u in units] == ["tabela_4", "tabela_2"]


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
