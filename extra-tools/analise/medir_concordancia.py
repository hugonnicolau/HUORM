#!/usr/bin/env python3
"""Concordancia entre execucoes repetidas: TARr@N e TARa@N.

CORRER SO DEPOIS DA CORRIDA NACIONAL TERMINAR. Compete com ela pelas 10
ligacoes concorrentes do plano e atrasa-a.

As metricas sao as de Atil et al. (2025):
  TARr@N  total agreement rate sobre a saida em bruto ao fim de N execucoes
  TARa@N  o mesmo sobre as entidades ja interpretadas

Procedimento:
  1. correr o referencia outra vez, para uma pasta nova
        .\\correr_referencia.ps1            (ou o comando do batch_processor)
  2. correr este script, apontando as duas pastas

Uso:
    python medir_concordancia.py out_referencia_final out_referencia_rep2
    python medir_concordancia.py out_referencia_final out_rep2 out_rep3   (N=3)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def carregar(raiz: Path) -> dict[str, dict]:
    """Por documento: a saida em bruto por seccao e as entidades interpretadas."""
    saida: dict[str, dict] = {}
    for pasta in sorted(p for p in raiz.iterdir() if p.is_dir()):
        ext = pasta / "pgx_outputs" / "Extended_PGx_Analysis.json"
        if not ext.exists():
            continue

        bruto: dict[str, str] = {}
        for sec in sorted(pasta.glob("*.json")):
            try:
                j = json.loads(sec.read_text(encoding="utf-8"))
            except Exception:
                continue
            av = j.get("avaliacao_farmacogenomica")
            if isinstance(av, dict):
                # a saida em bruto do modelo, antes de qualquer interpretacao
                bruto[sec.name] = "\n".join([
                    str(av.get("contem_farmacogenomica", "")),
                    str(av.get("informacao_farmacogenomica", "")),
                ])

        j = json.loads(ext.read_text(encoding="utf-8"))
        ents = set()
        for tipo, chave in (("genes", "symbol"), ("star_alleles", "variant"),
                            ("diplotypes", "variant"), ("rsids", "variant")):
            for e in (j.get("frequencias_entidades", {}) or {}).get(tipo, []) or []:
                v = e.get(chave) or e.get("symbol") or e.get("variant")
                if v:
                    ents.add(f"{tipo}:{v}")

        saida[pasta.name] = {"bruto": bruto, "entidades": frozenset(ents)}
    return saida


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    raizes = [Path(a) for a in sys.argv[1:]]
    for r in raizes:
        if not r.is_dir():
            print(f"pasta inexistente: {r}")
            sys.exit(1)

    execucoes = [carregar(r) for r in raizes]
    n = len(execucoes)
    comuns = set(execucoes[0])
    for e in execucoes[1:]:
        comuns &= set(e)
    comuns = sorted(comuns)

    if not comuns:
        print("Nenhum documento em comum entre as execucoes.")
        sys.exit(1)

    igual_bruto = igual_ents = 0
    divergentes: list[tuple[str, str]] = []

    for doc in comuns:
        brutos = [e[doc]["bruto"] for e in execucoes]
        ents = [e[doc]["entidades"] for e in execucoes]

        if all(b == brutos[0] for b in brutos[1:]):
            igual_bruto += 1
        else:
            seccoes = {s for b in brutos for s in b}
            dif = [s for s in sorted(seccoes)
                   if any(b.get(s) != brutos[0].get(s) for b in brutos[1:])]
            divergentes.append((doc, ", ".join(dif[:3])))

        if all(x == ents[0] for x in ents[1:]):
            igual_ents += 1

    total = len(comuns)
    print(f"execucoes comparadas : {n}")
    print(f"documentos em comum  : {total}")
    print()
    print(f"TARr@{n}  (saida em bruto) : {igual_bruto}/{total} "
          f"= {100 * igual_bruto / total:.1f}%")
    print(f"TARa@{n}  (entidades)      : {igual_ents}/{total} "
          f"= {100 * igual_ents / total:.1f}%")

    if divergentes:
        print(f"\ndocumentos cuja saida em bruto diferiu ({len(divergentes)}):")
        for doc, secs in divergentes:
            print(f"   {doc[:40]:42} {secs}")
    else:
        print("\nNenhuma divergencia na saida em bruto.")


if __name__ == "__main__":
    main()
