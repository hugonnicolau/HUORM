"""
Detection of image-only (scanned) PDFs.

OCR was evaluated and discarded: the results on RCM layouts were unreliable
enough that bad text is worse than no text — it produces entities that do not
exist. The alternative adopted here is to identify these documents up front and
flag them, so they are excluded from the analysis instead of silently
contributing zeros.

Without this flag a scanned RCM is indistinguishable from an RCM that genuinely
contains no pharmacogenomic information. Both yield "no PGx", and the
denominator of every percentage is quietly wrong.

In the 17-document subset, 4 sections produced no extractable text.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Below this, a page carries no meaningful prose. RCM pages average several
# thousand characters; a scanned page yields only stray OCR-less artefacts.
MIN_CHARS_PER_PAGE = 120

# A document may legitimately open with a cover page. Judge on the whole file.
MIN_TOTAL_CHARS = 400

# --------------------------------------------------------------------------
# Corrupt text layers
#
# A second failure mode, distinct from a scan and invisible to the character
# count. Some PDFs embed a font without a usable ToUnicode map: extraction
# returns the raw glyph codes rather than letters. The document looks healthy
# (tramadol_oral yields 41 705 characters) but the text is unreadable, so the
# pipeline finds no sections, sends nothing useful to the model, and records
# "no PGx" — the same silent zero a scan would produce.
#
# Two signals separate it, measured on the 71 documents available:
#
#                       Portuguese words / 1000 chars    letters    control
#   tramadol_oral                       0.00              0.15       0.342
#   the other 70                     9.25 – 21.99      0.50 – 0.78    0.000
#
# The gap is wide enough that the thresholds are not finely tuned. They are
# set nearer the healthy side so a borderline document is inspected rather
# than discarded: false negatives cost processing time, false positives cost
# a document.
# --------------------------------------------------------------------------

# Function words that appear in every Portuguese RCM. Counted per 1000
# characters so document length does not influence the verdict.
_COMMON_WORDS = (
    "de", "que", "para", "não", "com", "dose", "doentes",
    "medicamento", "utilização", "efeitos",
)
MIN_WORD_DENSITY = 3.0

# Glyph codes land in the C0 control range, which real prose never contains
# beyond newlines and tabs.
MAX_CONTROL_FRACTION = 0.05

# Prose is mostly letters. Tables and dosage figures lower this, hence the
# margin below the observed minimum of 0.50.
MIN_LETTER_FRACTION = 0.35

_WORD_PATTERNS = tuple(
    re.compile(r"\b" + w + r"\b", re.IGNORECASE) for w in _COMMON_WORDS
)


def _readability(body: str) -> dict:
    """Measure whether extracted text is readable Portuguese prose."""
    if not body:
        return {"word_density": 0.0, "letter_fraction": 0.0,
                "control_fraction": 0.0}

    length = len(body)
    words = sum(len(p.findall(body)) for p in _WORD_PATTERNS)
    letters = sum(ch.isalpha() for ch in body)
    control = sum(1 for ch in body if ord(ch) < 32 and ch not in "\n\r\t")

    return {
        "word_density": round(words / length * 1000, 2),
        "letter_fraction": round(letters / length, 3),
        "control_fraction": round(control / length, 3),
    }


def _pdftotext(pdf_path: Path) -> str | None:
    """Extract the text layer. None when the tool is unavailable."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=120,
        )
        return result.stdout
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return ""


def _page_count(pdf_path: Path) -> int:
    """Número de páginas, com o pypdfium2 como alternativa ao pdfinfo.

    O `pdfinfo` vem do poppler, que existe no macOS e no Linux mas não no
    Windows sem instalação à parte. Sem ele esta função devolvia 0, e com 0
    páginas a verificação de caracteres por página em `inspect` é saltada — o
    mesmo documento seria classificado de maneira diferente conforme a máquina
    onde a corrida decorresse. Num corpus processado em duas máquinas isso
    torna o resultado irreprodutível.

    O pypdfium2 já é dependência do projecto, porque é o backend do docling.
    Tentando-o primeiro, a contagem deixa de depender de ferramentas externas.
    """
    try:
        import pypdfium2

        documento = pypdfium2.PdfDocument(str(pdf_path))
        try:
            return len(documento)
        finally:
            documento.close()
    except Exception:  # noqa: BLE001
        pass

    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=30
        )
        match = re.search(r"Pages:\s+(\d+)", result.stdout)
        return int(match.group(1)) if match else 0
    except Exception:  # noqa: BLE001
        return 0


def inspect(pdf_path: str | Path, markdown: str | None = None) -> dict:
    """Classify a PDF as digital, scanned, or unreadable.

    Args:
        pdf_path: file to inspect.
        markdown: optional docling output. When supplied it takes precedence,
            since it reflects what the pipeline actually received.

    Returns:
        dict with `is_scanned`, `status`, `chars`, `pages`, `chars_per_page`
        and a human-readable `reason`.

        status is one of:
          "digital"     usable text layer
          "scanned"     no usable text — image-only, needs OCR to be usable
          "corrupt"     text layer present but unreadable (broken ToUnicode)
          "unreadable"  file could not be read at all
    """
    path = Path(pdf_path)
    body = markdown if markdown is not None else _pdftotext(path)

    if body is None:
        return {
            "is_scanned": False,
            "is_usable": True,
            "status": "unknown",
            "chars": 0,
            "pages": 0,
            "chars_per_page": 0.0,
            "word_density": 0.0,
            "letter_fraction": 0.0,
            "control_fraction": 0.0,
            "reason": "pdftotext indisponível; classificação não efetuada",
        }

    chars = len(re.sub(r"\s+", " ", body).strip())
    pages = _page_count(path)
    per_page = chars / pages if pages else float(chars)
    metrics = _readability(body)

    if chars == 0:
        status, reason = "scanned", "sem qualquer camada de texto"
    elif chars < MIN_TOTAL_CHARS:
        status, reason = "scanned", f"apenas {chars} caracteres no documento inteiro"
    elif pages and per_page < MIN_CHARS_PER_PAGE:
        status, reason = "scanned", f"{per_page:.0f} caracteres por página"

    # Only reached when the document has plenty of text. The question is no
    # longer whether text exists but whether it means anything.
    elif metrics["control_fraction"] > MAX_CONTROL_FRACTION:
        status = "corrupt"
        reason = (f"{metrics['control_fraction']:.0%} de caracteres de controlo "
                  f"— camada de texto sem mapa de caracteres utilizável")
    elif metrics["word_density"] < MIN_WORD_DENSITY:
        status = "corrupt"
        reason = (f"{metrics['word_density']:.2f} palavras comuns por 1000 "
                  f"caracteres — texto extraído não é português legível")
    elif metrics["letter_fraction"] < MIN_LETTER_FRACTION:
        status = "corrupt"
        reason = (f"apenas {metrics['letter_fraction']:.0%} do texto são letras "
                  f"— extração provavelmente corrompida")
    else:
        status, reason = "digital", ""

    return {
        # Kept for callers written against the previous contract.
        "is_scanned": status == "scanned",
        # What the pipeline should branch on: both failure modes are equally
        # unusable, and both must be excluded from the denominators.
        "is_usable": status in ("digital", "unknown"),
        "status": status,
        "chars": chars,
        "pages": pages,
        "chars_per_page": round(per_page, 1),
        **metrics,
        "reason": reason,
    }


def scan_folder(folder: str | Path) -> list[dict]:
    """Classify every PDF in a folder. Useful before launching a large batch."""
    results = []
    for pdf in sorted(Path(folder).glob("*.pdf")):
        if pdf.name.startswith("._"):
            continue
        results.append({"file": pdf.name, **inspect(pdf)})
    return results


if __name__ == "__main__":
    import argparse
    import csv
    import sys

    parser = argparse.ArgumentParser(
        description="Identify image-only PDFs before processing a batch."
    )
    parser.add_argument("folder")
    parser.add_argument("--csv", help="write the full classification to this file")
    args = parser.parse_args()

    rows = scan_folder(args.folder)
    if not rows:
        sys.exit(f"No PDFs found in {args.folder}")

    scanned = [r for r in rows if r["status"] == "scanned"]
    corrupt = [r for r in rows if r["status"] == "corrupt"]
    unusable = scanned + corrupt

    print(f"  PDFs inspected : {len(rows)}")
    print(f"  digital        : {len(rows) - len(unusable)}")
    print(f"  scanned        : {len(scanned)}  ({100 * len(scanned) / len(rows):.1f}%)")
    print(f"  corrupt text   : {len(corrupt)}  ({100 * len(corrupt) / len(rows):.1f}%)")

    if unusable:
        print("\n  Unusable documents (exclude from the analysis):")
        for r in unusable[:30]:
            print(f"    [{r['status']:<7}] {r['file'][:46]:<46} {r['reason']}")
        if len(unusable) > 30:
            print(f"    … and {len(unusable) - 30} more")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  {args.csv}")
