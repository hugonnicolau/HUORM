"""
Testes da segmentação de blocos enviados ao modelo.

O corte cego `texto[i:i + 6000]` partia a meio de frase e a meio de palavra.
Uma afirmação farmacogenómica que atravessasse a fronteira era separada em
duas metades, e cada metade ia ao modelo sem o contexto da outra — o que
contradiz a instrução do prompt de "continua a extrair enquanto o texto
mantiver relação com a mesma informação farmacogenómica".

    python RCMprocessor/tests/test_text_blocks.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "pharmacogenomics_evaluator.py"
ENDS_WITH_PUNCTUATION = re.compile(r"[.!?;:]\s*$")


def _load_splitter():
    """Extrai _split_into_blocks sem importar o módulo (que precisa de ollama)."""
    src = SOURCE.read_text(encoding="utf-8")
    start = src.index("    def _split_into_blocks")
    end = src.index("    def _invoke_with_backoff")
    body = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in src[start:end].split("\n")
    )
    body = (body.replace("@classmethod\n", "")
                .replace("cls, ", "")
                .replace("cls.BLOCK_MAX_CHARS", "6000"))
    namespace = {"re": re}
    exec(compile(body, "extracted", "exec"), namespace)
    return namespace["_split_into_blocks"]


split_into_blocks = _load_splitter()

PARAGRAPHS = (
    "Parágrafo um sobre posologia e administração. " * 100
    + "\n\n"
    + "Parágrafo dois: metabolizadores lentos de CYP2D6 requerem ajuste de dose. "
      "Esta frase continua o mesmo tema e não deve ser separada da anterior. " * 40
)


def test_blocks_end_on_sentence_boundaries():
    blocks = split_into_blocks(PARAGRAPHS, 2000)
    broken = [b for b in blocks if b.strip() and not ENDS_WITH_PUNCTUATION.search(b.strip())]
    assert not broken, f"{len(broken)} blocos acabam a meio de frase"


def test_old_blind_slicing_did_break_sentences():
    """Prova que o problema existia — se este teste falhar, o corte cego mudou."""
    old = [PARAGRAPHS[i:i + 2000] for i in range(0, len(PARAGRAPHS), 2000)]
    broken = [b for b in old if b.strip() and not ENDS_WITH_PUNCTUATION.search(b.strip())]
    assert broken, "o corte cego devia partir frases"


def test_no_content_lost_or_duplicated():
    """Sem sobreposição: cada carácter aparece exatamente uma vez.

    Sobrepor daria mais contexto ao modelo, mas o mesmo excerto seria extraído
    duas vezes e a contagem de menções — que corre sobre a concatenação dos
    excertos — ficaria inflacionada.
    """
    blocks = split_into_blocks(PARAGRAPHS, 2000)
    original = re.sub(r"\s+", "", PARAGRAPHS)
    rebuilt = re.sub(r"\s+", "", "".join(blocks))
    assert original == rebuilt


def test_blocks_respect_the_size_limit():
    for limit in (500, 1000, 2000, 6000):
        for block in split_into_blocks(PARAGRAPHS, limit):
            assert len(block) <= limit, f"bloco de {len(block)} excede {limit}"


def test_oversized_paragraph_splits_by_sentence():
    giant = "Frase sobre CYP2C19 e o alelo *2. " * 300
    blocks = split_into_blocks(giant, 1000)
    assert len(blocks) > 1
    assert all(len(b) <= 1000 for b in blocks)
    assert all(ENDS_WITH_PUNCTUATION.search(b.strip()) for b in blocks)


def test_single_sentence_longer_than_limit_is_hard_split():
    """Último recurso: uma frase única maior que o limite tem de ser partida."""
    monster = "palavra " * 2000  # sem pontuação nenhuma
    blocks = split_into_blocks(monster, 500)
    assert blocks
    assert all(len(b) <= 500 for b in blocks)


def test_paragraphs_are_packed_not_one_per_block():
    """Parágrafos pequenos devem ser agrupados, não gerar um bloco cada."""
    text = "\n\n".join(f"Parágrafo {i} curto." for i in range(50))
    blocks = split_into_blocks(text, 6000)
    assert len(blocks) == 1, f"esperado 1 bloco, obtidos {len(blocks)}"


def test_degenerate_inputs():
    assert split_into_blocks("", 6000) == []
    assert split_into_blocks("   \n\n  ", 6000) == []
    assert split_into_blocks("CYP2D6.", 6000) == ["CYP2D6."]


def test_pgx_statement_not_split_across_blocks():
    """O caso que motivou a correção.

    Uma afirmação PGx colocada exatamente na fronteira dos 2000 caracteres tem
    de ficar inteira num bloco.
    """
    filler = "Texto de enchimento sobre excipientes. " * 50
    statement = ("Os doentes com genótipo CYP2C19*2/*2 são metabolizadores "
                 "lentos e requerem redução da dose em 50%.")
    text = filler + "\n\n" + statement + "\n\n" + filler

    blocks = split_into_blocks(text, 2000)
    assert any(statement in b for b in blocks), (
        "a afirmação PGx foi partida entre blocos"
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
