#!/usr/bin/env python3
"""Conta retentativas, 429 e chamadas nos logs da corrida.

Correr a partir de ~/Desktop/FINAL:
    python3 onde_esta_o_tempo.py
"""
import glob
import os
import re
from collections import Counter

logs = sorted(glob.glob("log_nac_*.txt"))
if not logs:
    raise SystemExit("sem logs log_nac_*.txt")

docs = 0
avaliar = 0
retentativas = []
esgotadas = 0
nao_repete = 0
motivos = Counter()
esperas = []

RE_TENT = re.compile(r"tentativa (\d+)/(\d+) falhou — (.+?)\. A esperar ([\d.]+)s")

for f in logs:
    for linha in open(f, encoding="utf-8", errors="ignore"):
        if linha.startswith("=== A processar"):
            docs += 1
        elif "A avaliar:" in linha:
            avaliar += 1
        elif "esgotadas as tentativas" in linha:
            esgotadas += 1
        elif "não se repete" in linha:
            nao_repete += 1
        m = RE_TENT.search(linha)
        if m:
            retentativas.append(int(m.group(1)))
            motivos[m.group(3)] += 1
            esperas.append(float(m.group(4)))

print(f"logs lidos              : {len(logs)}")
print(f"documentos iniciados    : {docs}")
print(f"chamadas de classificação: {avaliar}  ({avaliar/max(docs,1):.1f} por documento)")
print()
print(f"retentativas            : {len(retentativas)}")
print(f"tentativas esgotadas    : {esgotadas}")
print(f"erros sem retentativa   : {nao_repete}")
if esperas:
    print(f"tempo total em espera   : {sum(esperas)/60:.1f} min")
    print(f"                          {sum(esperas)/60/max(docs,1):.2f} min por documento")
    print(f"espera média           : {sum(esperas)/len(esperas):.0f}s")
print()
if motivos:
    print("motivos das falhas:")
    for m, n in motivos.most_common(10):
        print(f"   {n:5d}  {m}")
else:
    print("nenhuma retentativa registada")

print()
print("tamanho dos logs:")
for f in logs:
    print(f"   {f}  {os.path.getsize(f):8d} bytes")
