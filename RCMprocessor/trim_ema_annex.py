"""
Trim EMA multi-annex PDFs down to Annex I (the SmPC).

Why this is needed
------------------
Infomed publishes the RCM as a standalone document. The EMA does not: for a
centrally authorised medicine the published PDF is the full decision annex,

    Annex I    Resumo das Características do Medicamento   <- the RCM
    Annex II   Manufacturing and supply conditions
    Annex III  Rotulagem e Folheto Informativo             <- labelling + PIL

Feeding the whole file to the pipeline mixes two registers of text. Measured
on the two documents added to the 78-compound set:

    Brexpiprazol   118 023 chars   Annex I = 65%   35% is annex/leaflet
    Dolutegravir   289 364 chars   Annex I = 77%   23% is annex/leaflet

Three concrete consequences:

1. The package leaflet restates the same information in lay language. A gene
   named there would be counted as a mention, and the text/table origin
   metrics would attribute it to the RCM.
2. The leaflet is numbered independently ("1. O que é X"), so its headings can
   collide with the RCM's own numbering during section extraction.
3. Section 5.3 is the last RCM section; whatever follows it is absorbed by
   that section's boundary, so the analysed 5.3 would carry annex text.

A single EMA file can also contain more than one SmPC (Dolutegravir carries
two: tablets and dispersible tablets). That is reported, not resolved, because
choosing between them is a decision about the study, not about parsing.

Usage
-----
    python -m RCMprocessor.trim_ema_annex <pasta>              # relatório
    python -m RCMprocessor.trim_ema_annex <pasta> --aplicar    # corta
    python -m RCMprocessor.trim_ema_annex <pasta> --aplicar --sufixo _RCM

With --aplicar the untouched download is kept as `<nome>.ANEXO-COMPLETO.pdf`
unless --sufixo is given, in which case the trimmed copy is written alongside
the original instead.

The backup suffix is deliberately not "original": that reads as "the good one",
and the full annex is precisely the version that must NOT be analysed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# "ANEXO II" opens the section that follows the SmPC. Matched on a line of its
# own: the string also appears in cross-references inside the body ("ver Anexo
# II"), which must not be treated as the boundary.
_RE_ANEXO_II = re.compile(r"^\s*ANEXO\s+II\b", re.MULTILINE)

# Markers that identify a file as a full EMA annex rather than a bare RCM.
_RE_FOLHETO = re.compile(r"FOLHETO INFORMATIVO", re.IGNORECASE)
_RE_RCM = re.compile(r"RESUMO DAS CARACTER[IÍ]STICAS", re.IGNORECASE)

# Every SmPC opens with section 1. A second occurrence inside Annex I means the
# annex carries two complete SmPCs — Tivicay ships film-coated tablets and
# dispersible tablets that way, each with its own 4.1 through 5.3. The section
# extractor keeps one and drops the other without saying so, which is the worst
# of the options: the document is neither one RCM nor two.
_RE_NOME_MEDICAMENTO = re.compile(r"^\s*1\.\s+NOME DO MEDICAMENTO",
                                  re.MULTILINE | re.IGNORECASE)


def _page_texts(pdf: Path) -> list[str]:
    """Text of each page, via pdftotext one page at a time."""
    total = _page_count(pdf)
    paginas = []
    for n in range(1, total + 1):
        r = subprocess.run(
            ["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(pdf), "-"],
            capture_output=True, text=True, timeout=60,
        )
        paginas.append(r.stdout)
    return paginas


def _page_count(pdf: Path) -> int:
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                       text=True, timeout=30)
    m = re.search(r"Pages:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else 0


def inspect(pdf: Path) -> dict:
    """Locate Annex I in a PDF, without modifying it."""
    paginas = _page_texts(pdf)
    total = len(paginas)
    inteiro = "\n".join(paginas)

    n_rcm = len(_RE_RCM.findall(inteiro))
    tem_folheto = bool(_RE_FOLHETO.search(inteiro))

    # First page whose own text opens Annex II.
    pagina_anexo_ii = None
    for i, texto in enumerate(paginas, start=1):
        if _RE_ANEXO_II.search(texto):
            pagina_anexo_ii = i
            break

    e_anexo_ema = tem_folheto and pagina_anexo_ii is not None
    fim_anexo_i = (pagina_anexo_ii - 1) if pagina_anexo_ii else total

    # Pages where a new SmPC begins, within Annex I only.
    inicios = [i for i, texto in enumerate(paginas[:fim_anexo_i], start=1)
               if _RE_NOME_MEDICAMENTO.search(texto)]

    return {
        "ficheiro": pdf.name,
        "paginas": total,
        "e_anexo_ema": e_anexo_ema,
        "pagina_anexo_ii": pagina_anexo_ii,
        "ultima_pagina_rcm": fim_anexo_i,
        "n_rcm_no_ficheiro": n_rcm,
        "tem_folheto": tem_folheto,
        "inicios_rcm": inicios,
        "n_rcm_no_anexo_i": len(inicios),
        # Where Annex I would end if only the first SmPC were kept.
        "fim_primeiro_rcm": (inicios[1] - 1) if len(inicios) > 1 else fim_anexo_i,
        "titulo_primeiro": _titulo(paginas, inicios[0]) if inicios else "",
        "titulo_segundo": (_titulo(paginas, inicios[1])
                           if len(inicios) > 1 else ""),
    }


def _titulo(paginas: list[str], pagina: int) -> str:
    """Medicine name that follows the section 1 heading on `pagina`."""
    texto = paginas[pagina - 1]
    m = _RE_NOME_MEDICAMENTO.search(texto)
    if not m:
        return ""
    seguinte = texto[m.end():m.end() + 200]
    seguinte = re.split(r"2\.\s+COMPOSI", seguinte)[0]
    return re.sub(r"\s+", " ", seguinte).strip()[:70]


def trim(pdf: Path, ultima: int, destino: Path) -> None:
    """Write pages 1..ultima of `pdf` to `destino` using qpdf."""
    subprocess.run(
        ["qpdf", str(pdf), "--pages", ".", f"1-{ultima}", "--", str(destino)],
        check=True, capture_output=True, timeout=120,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reduce EMA annex PDFs to Annex I (the RCM)."
    )
    parser.add_argument("pasta")
    parser.add_argument("--aplicar", action="store_true",
                        help="cortar de facto; sem isto só relata")
    parser.add_argument("--sufixo", default=None,
                        help="escrever a cópia cortada como <nome><sufixo>.pdf "
                             "em vez de substituir o original")
    parser.add_argument("--um-rcm", action="store_true",
                        help="quando o anexo I traz vários RCMs, manter só o "
                             "primeiro (um documento por substância ativa)")
    args = parser.parse_args()

    pasta = Path(args.pasta).resolve()
    if not pasta.is_dir():
        sys.exit(f"Pasta não encontrada: {pasta}")

    pdfs = sorted(p for p in pasta.glob("*.pdf")
                  if not p.name.startswith("._")
                  and not p.name.endswith(".ANEXO-COMPLETO.pdf")
                  and not p.name.endswith(".original.pdf"))
    if not pdfs:
        sys.exit(f"Sem PDFs em {pasta}")

    anexos, normais, multiplos = [], [], []
    for pdf in pdfs:
        info = inspect(pdf)
        info["corte"] = (info["fim_primeiro_rcm"] if args.um_rcm
                         else info["ultima_pagina_rcm"])
        if info["e_anexo_ema"]:
            anexos.append(info)
            if info["n_rcm_no_anexo_i"] > 1:
                multiplos.append(info)
        else:
            normais.append(info)

    print("=" * 66)
    print("ANEXOS DA EMA" + ("" if args.aplicar else "  (relatório)"))
    print("=" * 66)
    print(f"  PDFs inspecionados : {len(pdfs)}")
    print(f"  RCM autónomo       : {len(normais)}")
    print(f"  anexo completo EMA : {len(anexos)}")

    if not anexos:
        print("\n  Nada a cortar.")
        return 0

    print(f"\n  {'ficheiro':<26}{'págs':>6}{'anexo I':>9}{'manter':>8}"
          f"{'cortar':>8}{'RCMs':>6}")
    for i in anexos:
        print(f"  {i['ficheiro'][:24]:<26}{i['paginas']:>6}"
              f"{i['ultima_pagina_rcm']:>9}{i['corte']:>8}"
              f"{i['paginas'] - i['corte']:>8}{i['n_rcm_no_anexo_i']:>6}")

    if multiplos:
        print(f"\n  ⚠️ {len(multiplos)} ficheiro(s) com mais de um RCM no anexo I:")
        for i in multiplos:
            print(f"      {i['ficheiro']}  ({i['n_rcm_no_anexo_i']} RCMs, "
                  f"páginas {', '.join(map(str, i['inicios_rcm']))})")
            print(f"          1º: {i['titulo_primeiro']}")
            print(f"          2º: {i['titulo_segundo']}")
        if args.um_rcm:
            print("      --um-rcm activo: fica só o primeiro.")
        else:
            print("      Todas as secções 4.1–5.3 aparecem repetidas, e o")
            print("      extractor guarda uma e descarta a outra sem avisar.")
            print("      Usa --um-rcm para manter só o primeiro.")

    if not args.aplicar:
        print("\n  Nada foi alterado. Acrescenta --aplicar para cortar.")
        return 0

    for i in anexos:
        origem = pasta / i["ficheiro"]
        if args.sufixo:
            destino = origem.with_name(origem.stem + args.sufixo + ".pdf")
            trim(origem, i["corte"], destino)
            print(f"  ✓ {destino.name}")
        else:
            guardado = origem.with_name(origem.stem + ".ANEXO-COMPLETO.pdf")
            temp = origem.with_name(origem.stem + ".tmp.pdf")
            trim(origem, i["corte"], temp)
            origem.rename(guardado)
            temp.rename(origem)
            print(f"  ✓ {origem.name}  (original em {guardado.name})")

    print(f"\n  {len(anexos)} ficheiro(s) cortado(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
