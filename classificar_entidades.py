#!/usr/bin/env python3
"""Classifica cada alelo e diplotipo do Excel global pela forma como esta escrito.

Porque existe: as categorias do esquema de extraccao sao genes, alelos,
diplotipos e rsIDs. Nao ha categoria para genotipo. O resultado e que a
categoria dos diplotipos acaba ocupada por genotipos, e a dos alelos por duas
grafias diferentes do mesmo alelo HLA. Isto conta quanto, por classe, para que
o numero va para a tese em vez de uma impressao.

NAO normaliza nada. So classifica e conta. A normalizacao e um passo a seguir,
e deve ser feita sabendo o que se esta a fundir.

Escreve:
    entidades_classificadas.csv   uma linha por entrada, com a classe
    entidades_resumo.csv          agregado por classe

Uso:
    python classificar_entidades.py
    python classificar_entidades.py out_nacional/Analise_Global_PGx.xlsx
"""
import csv
import re
import sys
from collections import Counter

import openpyxl

XLSX = sys.argv[1] if len(sys.argv) > 1 else "out_nacional/Analise_Global_PGx.xlsx"

HLA_COM = re.compile(r"^HLA-[A-Z]+\*\d+:\d+$")          # HLA-B*57:01, forma actual
HLA_SEM = re.compile(r"^HLA-[A-Z]+\*\d{4,}$")           # HLA-B*5701, forma antiga
HLA_CURTO = re.compile(r"^HLA-[A-Z]+\*\d{1,2}$")        # HLA-B*27, serotipo
STAR = re.compile(r"^[A-Z0-9]+\*\d+[A-Z]?$")            # CYP2C9*3
LETRA = re.compile(r"^[A-Z0-9]+\*[A-Z]$")               # SLCO1B1*C, invalido
HGVS = re.compile(r"C\.\d+", re.I)                      # c.521
BASES = re.compile(r"^[ACGT]{2}$")                      # CC, TT
GENE_BASES = re.compile(r"^[A-Z0-9]+[ACGT]{2}$")        # SLCO1B1CC
DIP = re.compile(r"^[A-Z0-9]+\*\d+[A-Z]?\*\d+[A-Z]?$")  # CYP2C9*1*3
IMPROV = re.compile(r"^[A-Z0-9]+\*[A-Z]\*[A-Z]$")       # SLCO1B1*C*C


def classe_alelo(e: str) -> str:
    if HGVS.search(e):        return "variante HGVS, nao alelo"
    if LETRA.match(e):        return "letra em vez de numero (invalido)"
    if HLA_COM.match(e):      return "HLA com dois pontos (forma actual)"
    if HLA_SEM.match(e):      return "HLA sem dois pontos (forma antiga)"
    if HLA_CURTO.match(e):    return "HLA incompleto (serotipo)"
    if STAR.match(e):         return "alelo estrela valido"
    return "outro"


def classe_diplotipo(e: str) -> str:
    u = e.upper()
    if HGVS.search(u):        return "genotipo em HGVS (c.NNN + bases)"
    if BASES.match(u):        return "bases soltas, sem gene"
    if IMPROV.match(u):       return "improvisacao (*base*base)"
    if GENE_BASES.match(u):   return "gene + bases (sem c.)"
    if DIP.match(u):          return "diplotipo valido"
    return "outro"


def ler(wb, folha):
    ws = wb[folha]
    linhas = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not r or r[0] is None:
            continue
        linhas.append((str(r[0]), int(r[1] or 0), int(r[2] or 0)))
    return linhas


def main() -> int:
    wb = openpyxl.load_workbook(XLSX, read_only=True)

    registos = []
    for folha, categoria, fn in (
        ("Alelos frequentes", "alelo", classe_alelo),
        ("Diplótipos frequentes", "diplotipo", classe_diplotipo),
    ):
        for entidade, docs, mencoes in ler(wb, folha):
            registos.append({
                "categoria": categoria,
                "entidade": entidade,
                "classe": fn(entidade),
                "documentos": docs,
                "mencoes": mencoes,
            })

    with open("entidades_classificadas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(registos[0].keys()))
        w.writeheader()
        w.writerows(registos)

    resumo = []
    for categoria in ("alelo", "diplotipo"):
        sub = [r for r in registos if r["categoria"] == categoria]
        tot_m = sum(r["mencoes"] for r in sub)
        ent = Counter(r["classe"] for r in sub)
        men = Counter()
        for r in sub:
            men[r["classe"]] += r["mencoes"]
        print(f"\n=== {categoria.upper()}S: {len(sub)} entradas, {tot_m} mencoes ===")
        for k in sorted(men, key=lambda x: -men[x]):
            pct = 100 * men[k] / tot_m if tot_m else 0
            print(f"   {k:36} {ent[k]:3} entradas {men[k]:5} mencoes  {pct:5.1f}%")
            resumo.append({"categoria": categoria, "classe": k,
                           "entradas": ent[k], "mencoes": men[k],
                           "pct_mencoes": round(pct, 1)})

    with open("entidades_resumo.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resumo[0].keys()))
        w.writeheader()
        w.writerows(resumo)

    print("\nguardado: entidades_classificadas.csv, entidades_resumo.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
