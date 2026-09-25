"""
Rename the RCMs of a one-per-substance folder to the substance name.

`705204_Rosuvastatina_Ezetimiba_Bluepharma.pdf` says which product it is but
not which compound of the study it answers for. With one document per active
substance, naming the file after the substance makes the gaps visible at a
glance — which is the point.

Two things are handled rather than assumed:

**Traceability.** The filename is the only link back to `medicamentos.csv`:
the numeric prefix is the Infomed medicine id. Renaming throws that away, so
the mapping is written to `_selecao/nomes.csv` first. The pipeline also names
each output folder after the PDF stem, so after renaming the outputs are keyed
by substance — which is what makes the analysis readable, but also means the
mapping file is the only remaining provenance.

**Cross-platform filenames.** Accents are dropped. macOS stores filenames as
NFD and Windows as NFC, so `Tacrolímus.pdf` written on one machine may not be
found by name on the other — a problem already hit in this project when the
same folder was used from both. `Tacrolimus.pdf` is the same on both.

    python -m RCMprocessor.rename_by_substance RCMs_78_um
    python -m RCMprocessor.rename_by_substance RCMs_78_um --aplicar
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

from .select_by_substance import PGX_COMPOUNDS, _word_regex
from .substance_utils import normalize


def ascii_safe(nome: str) -> str:
    """Filename-safe ASCII form, keeping the name readable.

    'Peginterferão alfa-2a' -> 'Peginterferao_alfa-2a'
    'Tacrolímus'            -> 'Tacrolimus'
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome)
        if not unicodedata.combining(c)
    )
    limpo = re.sub(r"[^\w\-]+", "_", sem_acento, flags=re.ASCII)
    return re.sub(r"_+", "_", limpo).strip("_")


def compound_for(pdf: Path, ja_conhecidos: dict[str, str]) -> str | None:
    """Which requested compound this file answers for.

    The selection CSV is authoritative when the file came from it. Otherwise
    the filename is matched against the compound list on whole words, so
    `Escitalopram.pdf` cannot be claimed by `Citalopram`.
    """
    if pdf.name in ja_conhecidos:
        return ja_conhecidos[pdf.name]

    # Underscores are word separators in a filename, but the compound matcher
    # only splits on whitespace and hyphens. Without this,
    # 'Peginterferao_alfa-2a.pdf' matches nothing.
    alvo = normalize(pdf.stem.replace("_", " "))
    achados = [pt for pt, en in PGX_COMPOUNDS
               if _word_regex(pt).search(alvo) or _word_regex(en).search(alvo)]
    if len(achados) == 1:
        return achados[0]
    if len(achados) > 1:
        # Prefer the longest name: 'Peginterferão alfa-2a' over a bare stem
        # that also matches a shorter compound.
        return max(achados, key=len)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename RCMs to their active substance."
    )
    parser.add_argument("pasta")
    parser.add_argument("--aplicar", action="store_true",
                        help="renomear de facto; sem isto só mostra o plano")
    args = parser.parse_args()

    pasta = Path(args.pasta).resolve()
    if not pasta.is_dir():
        sys.exit(f"Pasta não encontrada: {pasta}")

    relatorio = pasta / "_selecao"
    conhecidos: dict[str, str] = {}
    detalhe: dict[str, dict] = {}
    sel = relatorio / "selecao.csv"
    if sel.exists():
        for r in csv.DictReader(sel.open(encoding="utf-8")):
            conhecidos[r["ficheiro"]] = r["composto"]
            detalhe[r["ficheiro"]] = r

    pdfs = sorted(p for p in pasta.glob("*.pdf") if not p.name.startswith("._"))
    if not pdfs:
        sys.exit(f"Sem PDFs em {pasta}")

    planos: list[dict] = []
    sem_composto: list[str] = []
    destinos: dict[str, str] = {}

    for pdf in pdfs:
        # '<nome>.original.pdf' segue o mesmo destino do seu par, com o sufixo
        # preservado, para o original ficar ao lado do ficheiro cortado.
        e_original = pdf.name.endswith(".original.pdf")
        base = pdf.name[:-len(".original.pdf")] if e_original else pdf.stem
        chave = Path(base + ".pdf")

        composto = compound_for(chave, conhecidos)
        if not composto:
            sem_composto.append(pdf.name)
            continue

        novo = ascii_safe(composto) + (".original.pdf" if e_original else ".pdf")
        if novo == pdf.name:
            continue

        if novo in destinos and not e_original:
            print(f"⚠️ colisão: {pdf.name} e {destinos[novo]} querem "
                  f"chamar-se {novo}")
            continue
        destinos[novo] = pdf.name

        info = detalhe.get(chave.name, {})
        planos.append({
            "nome_novo": novo,
            "nome_antigo": pdf.name,
            "composto": composto,
            "medicamento": info.get("medicamento", ""),
            "substancia_infomed": info.get("substancia_infomed", ""),
            "atc": info.get("atc", ""),
            "origem": "seleção" if chave.name in conhecidos else "acrescentado",
        })

    print("=" * 68)
    print("RENOMEAR PARA A SUBSTÂNCIA ATIVA"
          + ("" if args.aplicar else "   (plano)"))
    print("=" * 68)
    print(f"  PDFs na pasta   : {len(pdfs)}")
    print(f"  a renomear      : {len(planos)}")
    print(f"  já com o nome   : {len(pdfs) - len(planos) - len(sem_composto)}")

    if sem_composto:
        print(f"\n  ⚠️ sem composto atribuído ({len(sem_composto)}) — "
              f"não são tocados:")
        for n in sem_composto:
            print(f"      {n}")

    if planos:
        print(f"\n  {'novo':<28}{'antigo'}")
        for p in planos:
            if p["nome_antigo"].endswith(".original.pdf"):
                continue
            print(f"  {p['nome_novo'][:26]:<28}{p['nome_antigo'][:38]}")

    if not args.aplicar:
        print("\n  Nada foi alterado. Acrescenta --aplicar.")
        return 0

    # O mapeamento é gravado ANTES de renomear: se algo falhar a meio, a
    # correspondência entre substância e medicamento não se perde.
    relatorio.mkdir(exist_ok=True)
    if planos:
        with (relatorio / "nomes.csv").open("w", newline="",
                                            encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(planos[0].keys()))
            w.writeheader()
            w.writerows(planos)
        print(f"\n  mapeamento -> {relatorio / 'nomes.csv'}")

    renomeados = 0
    for p in planos:
        origem = pasta / p["nome_antigo"]
        destino = pasta / p["nome_novo"]
        if destino.exists():
            print(f"  ⚠️ existe já, saltado: {destino.name}")
            continue
        origem.rename(destino)
        renomeados += 1

    print(f"  {renomeados} ficheiro(s) renomeado(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
