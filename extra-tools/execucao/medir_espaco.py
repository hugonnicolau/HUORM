#!/usr/bin/env python3
"""Mede o espaço por documento numa saída já produzida e extrapola.

Correr a partir de ~/Desktop/FINAL:
    python3 medir_espaco.py out_gabarito_final
    python3 medir_espaco.py out_nacional 5623
"""
import math
import os
import sys

CLUSTER = 4096

saida = sys.argv[1] if len(sys.argv) > 1 else "out_gabarito_final"
alvo = int(sys.argv[2]) if len(sys.argv) > 2 else 5623

docs = [d for d in os.listdir(saida) if os.path.isdir(os.path.join(saida, d))]
if not docs:
    raise SystemExit(f"sem documentos em {saida}")

por_tipo = {}
reais = alocados = ficheiros = 0

for d in docs:
    p = os.path.join(saida, d)
    for sub, dirs, fs in os.walk(p):
        rel = os.path.relpath(sub, p)
        alocados += CLUSTER * (1 + len(dirs))
        for f in fs:
            t = os.path.getsize(os.path.join(sub, f))
            reais += t
            alocados += max(CLUSTER, math.ceil(t / CLUSTER) * CLUSTER)
            ficheiros += 1
            if rel == "md":
                k = "md/ (raw + normalizado)"
            elif rel == "pgx_outputs":
                k = "pgx_outputs/ (o LLM)"
            else:
                k = "JSON de secção e metadados"
            por_tipo[k] = por_tipo.get(k, 0) + t

n = len(docs)
print(f"documentos medidos : {n}")
print(f"ficheiros por doc  : {ficheiros/n:.1f}")
print()
for k, v in sorted(por_tipo.items(), key=lambda x: -x[1]):
    print(f"  {k:32s} {v/n/1024:8.1f} KB/doc")
print()
print(f"bytes reais        : {reais/n/1024:8.1f} KB/doc")
print(f"espaço em disco    : {alocados/n/1024:8.1f} KB/doc   (+{100*(alocados-reais)/reais:.0f}%)")
print()
print(f"EXTRAPOLAÇÃO para {alvo} documentos")
print(f"  sem ajuste (estes documentos são pesados) : {alocados/n*alvo/1e9:6.2f} GB")
print(f"  ajustado ao tamanho médio nacional (0,57) : {alocados/n*alvo*0.57/1e9:6.2f} GB")
print()
print("O ajuste de 0,57 vem de medir o texto extraído de 250 PDF do corpus")
print("nacional (37 854 bytes em média) contra os do conjunto de")
print("desenvolvimento (65 886), que foram escolhidos por terem conteúdo PGx")
print("e são por isso mais longos.")
