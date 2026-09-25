"""
Detection of documents whose text cannot be used.

Two failure modes, one consequence. A scan has no text layer; a corrupt
document has one whose font lacks a usable character map, so extraction
returns glyph codes instead of letters. Either way the pipeline finds no
sections, the model receives nothing useful, and the document is recorded as
"no PGx" — indistinguishable from an RCM that genuinely has none. Every
percentage then carries a denominator that is quietly wrong.

The corrupt case was found in tramadol_oral: 41 705 characters extracted, no
readable Portuguese, zero sections, reported as processed. The character count
alone cannot catch it, which is why these thresholds exist.

Measured on the 71 documents available:

                      words/1000 chars    letters      control
  tramadol_oral              0.00          0.15         0.342
  the other 70            9.25 - 21.99   0.50 - 0.78    0.000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from RCMprocessor.scanned_pdf_detector import (  # noqa: E402
    MAX_CONTROL_FRACTION,
    MIN_LETTER_FRACTION,
    MIN_WORD_DENSITY,
    _readability,
    inspect,
)

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

# Excerpt of a real RCM, in the shape docling produces.
PROSA_REAL = """
## 4.5 Interações medicamentosas e outras formas de interação

A administração concomitante com inibidores potentes do CYP2D6 pode aumentar
a exposição ao medicamento. Nos doentes com metabolização diminuída, a dose
não deve exceder os 200 mg por dia. Não é recomendada a utilização em
associação com outros medicamentos que prolonguem o intervalo QT.

Os efeitos indesejáveis foram avaliados em doentes tratados durante 12
semanas. Para a população pediátrica, ver secção 4.2.
""" * 6

# The failure signature of tramadol_oral: glyph codes in the C0 control range
# interleaved with punctuation, which is what a missing ToUnicode map yields.
TEXTO_CORROMPIDO = (
    "\x01\x02\x03 !\"#$%$&'()*+!+$+,% \x0b\x0c\x0e\x0f"
    "\x10\x11\x12\x13 -./012345 \x14\x15\x16\x17\x18\x19"
) * 400


def test_readable_prose_passes():
    m = _readability(PROSA_REAL)
    assert m["word_density"] >= MIN_WORD_DENSITY, m
    assert m["letter_fraction"] >= MIN_LETTER_FRACTION, m
    assert m["control_fraction"] <= MAX_CONTROL_FRACTION, m


def test_corrupt_text_is_flagged():
    m = _readability(TEXTO_CORROMPIDO)
    assert m["control_fraction"] > MAX_CONTROL_FRACTION, m
    assert m["word_density"] < MIN_WORD_DENSITY, m


def test_inspect_classifies_corrupt_as_unusable():
    r = inspect("nao_existe.pdf", markdown=TEXTO_CORROMPIDO)
    assert r["status"] == "corrupt", r
    assert r["is_usable"] is False
    # A corrupt document is not a scan; conflating them would misreport how
    # many documents the corpus actually loses to each cause.
    assert r["is_scanned"] is False
    assert r["reason"]


def test_inspect_classifies_prose_as_digital():
    r = inspect("nao_existe.pdf", markdown=PROSA_REAL)
    assert r["status"] == "digital", r
    assert r["is_usable"] is True
    assert r["reason"] == ""


def test_empty_document_is_scanned_not_corrupt():
    """Order matters: no text is a scan, not an unreadable text layer."""
    r = inspect("nao_existe.pdf", markdown="")
    assert r["status"] == "scanned", r
    assert r["is_usable"] is False


def test_short_document_is_scanned():
    r = inspect("nao_existe.pdf", markdown="Folheto informativo. Ver secção 1.")
    assert r["status"] == "scanned", r


def test_tables_and_figures_do_not_trigger_corrupt():
    """A dosage table is mostly digits, and must still count as usable."""
    tabela = """
| Genótipo CYP2C9 | Dose inicial | Dose máxima |
| --- | --- | --- |
| *1/*1 | 0,25 mg | 2,00 mg |
| *1/*2 | 0,20 mg | 1,50 mg |
| *2/*3 | 0,10 mg | 0,75 mg |
"""
    corpo = PROSA_REAL + tabela * 10
    r = inspect("nao_existe.pdf", markdown=corpo)
    assert r["status"] == "digital", r


def test_metrics_are_reported_for_auditing():
    """The numbers behind the verdict must reach the output, not just the flag."""
    r = inspect("nao_existe.pdf", markdown=PROSA_REAL)
    for chave in ("word_density", "letter_fraction", "control_fraction"):
        assert chave in r, f"{chave} em falta"


def test_unknown_when_extraction_unavailable_is_treated_as_usable():
    """Never discard a document because a tool was missing."""
    r = inspect("nao_existe.pdf", markdown=None)
    if r["status"] == "unknown":
        assert r["is_usable"] is True


# --------------------------------------------------------------------------
# Regression against the real corpus, when it is present.
#
# Skipped rather than failed when the output folders are absent, so the suite
# stays runnable on a machine that only has the code.
# --------------------------------------------------------------------------

def test_against_real_documents():
    raiz = Path(__file__).resolve().parents[2]
    mds = []
    for pasta in ("out_DS+", "out_DT-", "outputs_batch_anestesicos"):
        mds.extend((raiz / pasta).glob("*/md/normalizado.md"))
    if not mds:
        print("      (sem corpus local; verificação real ignorada)")
        return

    corrompidos, legiveis = [], []
    for p in mds:
        texto = p.read_text(encoding="utf-8", errors="replace")
        r = inspect(p, markdown=texto)
        nome = p.parent.parent.name
        (corrompidos if r["status"] == "corrupt" else legiveis).append(nome)

    assert "tramadol_oral" in corrompidos, (
        f"tramadol_oral devia ser detetado; corrompidos={corrompidos}"
    )
    assert len(corrompidos) == 1, (
        f"esperado exactamente 1 corrompido nos {len(mds)} documentos, "
        f"obtidos {len(corrompidos)}: {corrompidos}"
    )
    print(f"      ({len(legiveis)} legíveis, 1 corrompido em {len(mds)})")


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
