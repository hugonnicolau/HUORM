#!/usr/bin/env python3
"""Resolve TODAS as substâncias contra o MRCONSO em três varrimentos, não dois por substância.

Porquê
------
O `_resolve_mrconso_one` varre o MRCONSO de ponta a ponta duas vezes por cada
substância. São 2,3 GB e cerca de 31 s por varrimento. Com ~1 200 substâncias
distintas no corpus nacional, isso são 2 400 varrimentos — dias de trabalho, e
com vários processos a disputar o mesmo ficheiro é pior ainda.

Este script faz o mesmo trabalho em três varrimentos no total. A lógica de
correspondência é copiada linha a linha do `_resolve_mrconso_one`, incluindo o
limite de 25 candidatos, o mínimo de 5 caracteres para correspondências
parciais, a preferência por candidatos com DrugBank ID e a ordenação dos termos
ingleses por comprimento. O resultado tem de ser idêntico, e o
`validar_indice.py` prova-o contra as saídas que o pipeline já produziu.

Uso
---
    python3 construir_indice_mrconso.py <ficheiro_com_substancias.txt> [saida.json]

Uma substância por linha. Produz `indice_mrconso.json`.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from RCMprocessor.substance_utils import normalize as _norm  # noqa: E402

MRCONSO = BASE / "RCMprocessor" / "data" / "umls" / "MRCONSO.RRF"
MAX_CANDIDATES = 25
MIN_PARTIAL_LENGTH = 5


def _drugbank_code(code: str) -> str:
    code = (code or "").strip()
    if not code:
        return ""
    return code.upper() if code.upper().startswith("DB") else code


def construir(queries: list[str]) -> dict:
    # query original -> forma normalizada
    norm_de = {q: _norm(q) for q in queries}
    normalizadas = {n for n in norm_de.values() if n}
    print(f"substâncias     : {len(queries)}")
    print(f"normalizadas    : {len(normalizadas)}")

    # Substrings de cada consulta, com 5 caracteres ou mais. Serve o ramo
    # `string_norm in query_norm` do código original sem ter de comparar cada
    # linha com cada consulta.
    sub_para_query: dict[str, set[str]] = {}
    for n in normalizadas:
        for i in range(len(n)):
            for j in range(i + MIN_PARTIAL_LENGTH, len(n) + 1):
                sub_para_query.setdefault(n[i:j], set()).add(n)

    exatos: dict[str, dict[str, dict]] = {n: {} for n in normalizadas}
    parciais: dict[str, dict[str, dict]] = {n: {} for n in normalizadas}
    cheios: set[str] = set()

    # ---------------------------------------------------------------- 1
    t0 = time.time()
    linhas = 0
    with MRCONSO.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            linhas += 1
            f = line.rstrip("\n").split("|")
            if len(f) < 15:
                continue
            cui = f[0]
            valor = f[14]
            if not cui or not valor:
                continue
            sn = _norm(valor)
            if not sn:
                continue

            if sn in exatos and sn not in cheios:
                d = exatos[sn]
                if cui not in d:
                    d[cui] = {"cui": cui, "matched_term": valor, "match_type": "exact"}
                    if len(d) >= MAX_CANDIDATES:
                        cheios.add(sn)

            if len(sn) >= MIN_PARTIAL_LENGTH:
                for n in sub_para_query.get(sn, ()):
                    parciais[n].setdefault(
                        cui, {"cui": cui, "matched_term": valor, "match_type": "partial"}
                    )
    print(f"varrimento 1/3  : {time.time()-t0:5.1f}s  ({linhas:,} linhas)")

    # ---------------------------------------------------------------- 2
    # Ramo `query_norm in string_norm`, só para as consultas que ainda não têm
    # correspondência exacta. Indexa-se por janelas de 5 caracteres para não
    # comparar cada linha com cada consulta pendente.
    pendentes = {n for n in normalizadas if not exatos[n]}
    print(f"sem exacto      : {len(pendentes)}")
    if pendentes:
        por_prefixo: dict[str, list[str]] = {}
        for n in pendentes:
            por_prefixo.setdefault(n[:MIN_PARTIAL_LENGTH], []).append(n)

        t0 = time.time()
        with MRCONSO.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                f = line.rstrip("\n").split("|")
                if len(f) < 15:
                    continue
                cui = f[0]
                valor = f[14]
                if not cui or not valor:
                    continue
                sn = _norm(valor)
                if len(sn) < MIN_PARTIAL_LENGTH:
                    continue
                vistos = set()
                for i in range(len(sn) - MIN_PARTIAL_LENGTH + 1):
                    jan = sn[i:i + MIN_PARTIAL_LENGTH]
                    if jan in vistos:
                        continue
                    vistos.add(jan)
                    for n in por_prefixo.get(jan, ()):
                        if n in sn:
                            parciais[n].setdefault(
                                cui,
                                {"cui": cui, "matched_term": valor, "match_type": "partial"},
                            )
        print(f"varrimento 2/3  : {time.time()-t0:5.1f}s")

    # candidatos finais, pela mesma regra do original
    candidatos: dict[str, dict[str, dict]] = {}
    for n in normalizadas:
        if exatos[n]:
            candidatos[n] = dict(exatos[n])
        else:
            candidatos[n] = dict(list(parciais[n].items())[:MAX_CANDIDATES])

    cuis_todos = {c for d in candidatos.values() for c in d}
    print(f"CUI a enriquecer: {len(cuis_todos)}")

    # ---------------------------------------------------------------- 3
    ingleses: dict[str, set[str]] = {}
    drugbank: dict[str, tuple[str, str]] = {}
    t0 = time.time()
    with MRCONSO.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if len(f) < 15:
                continue
            cui = f[0]
            if cui not in cuis_todos:
                continue
            if f[1] == "ENG":
                termo = f[14].strip()
                if termo:
                    ingleses.setdefault(cui, set()).add(termo)
            if (f[11] or "").strip().upper() == "DRUGBANK":
                db = _drugbank_code(f[13]) or _drugbank_code(f[9]) or _drugbank_code(f[10])
                if db and cui not in drugbank:
                    drugbank[cui] = (db, f[14])
    print(f"varrimento 3/3  : {time.time()-t0:5.1f}s")

    # ---------------------------------------------------------------- montar
    indice = {}
    for q, n in norm_de.items():
        if not n:
            indice[q] = {"found": False, "query": q, "status": "empty_query",
                         "matches": [], "best_match": {}}
            continue
        matches = []
        for cui, item in candidatos[n].items():
            db, db_termo = drugbank.get(cui, ("", ""))
            ing = sorted(ingleses.get(cui, set()), key=len)
            matches.append({
                "query": q,
                "match_type": item["match_type"],
                "cui": cui,
                "drugbank_id": db,
                "preferred_term": db_termo or item["matched_term"],
                "matched_term": item["matched_term"],
                "english_terms": ing[:12],
            })
        matches.sort(key=lambda x: (not bool(x["drugbank_id"]),
                                    x["match_type"] != "exact",
                                    x["preferred_term"]))
        indice[q] = {
            "found": bool(matches),
            "query": q,
            "status": "ok" if matches else "not_found",
            "matches": matches,
            "best_match": matches[0] if matches else {},
        }
    return indice


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    entrada = Path(sys.argv[1])
    saida = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "indice_mrconso.json"

    queries = [l.strip() for l in entrada.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not MRCONSO.exists():
        print(f"MRCONSO não encontrado: {MRCONSO}")
        return 1

    t0 = time.time()
    indice = construir(queries)
    saida.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")

    achou = sum(1 for v in indice.values() if v["found"])
    print()
    print(f"resolvidas      : {achou} de {len(indice)}  ({100*achou/max(len(indice),1):.1f}%)")
    print(f"tempo total     : {time.time()-t0:.1f}s")
    print(f"escrito em      : {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
