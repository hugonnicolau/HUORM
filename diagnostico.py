#!/usr/bin/env python3
"""Onde está o tempo a ser gasto na corrida nacional.

Correr a partir de ~/Desktop/FINAL:
    python3 diagnostico.py
"""
import json
import os
import subprocess
import time
from collections import Counter

SAIDA = "out_nacional"

# ---------------------------------------------------------------- processos
try:
    out = subprocess.run(
        ["pgrep", "-f", "python3 -m RCMprocessor.batch_processor"],
        capture_output=True, text=True, timeout=10).stdout
    pids = [p for p in out.split() if p.strip()]
except Exception:
    pids = []
print(f"processos python vivos : {len(pids)}  (devem ser 8)")

# ---------------------------------------------------------------- documentos
docs = []
for d in os.listdir(SAIDA):
    p = os.path.join(SAIDA, d)
    if not os.path.isdir(p):
        continue
    alvo = os.path.join(p, "pgx_outputs", "Document_Unique_PGx.json")
    if os.path.exists(alvo):
        docs.append((os.path.getmtime(alvo), d, "ok"))
    elif os.path.exists(os.path.join(p, "NAO_UTILIZAVEL.json")):
        docs.append((os.path.getmtime(os.path.join(p, "NAO_UTILIZAVEL.json")), d, "sem_estrutura"))

docs.sort()
print(f"documentos concluídos  : {len(docs)}")
if not docs:
    raise SystemExit("ainda sem documentos concluídos")

tipos = Counter(t for _, _, t in docs)
print(f"  com análise          : {tipos.get('ok', 0)}")
print(f"  sem estrutura        : {tipos.get('sem_estrutura', 0)}")

decorrido = time.time() - docs[0][0]
print(f"decorrido              : {decorrido/3600:.2f} h")
print(f"ritmo                  : {len(docs)/decorrido*3600:.1f} documentos/hora")
print()

# ------------------------------------------------- distribuição no tempo
print("documentos concluídos por período de 30 min:")
t0 = docs[0][0]
janelas = Counter(int((t - t0) // 1800) for t, _, _ in docs)
for j in sorted(janelas):
    print(f"   +{j*30:4d} min  {'#' * janelas[j]} {janelas[j]}")
print()

# ------------------------------------------------- qual lote fez o quê
print("por lote (quem está a trabalhar):")
for n in range(8):
    nome = f"lote_nac_{n:02d}.txt"
    if not os.path.exists(nome):
        continue
    meus = {os.path.basename(l.strip())[:-4] for l in open(nome, encoding="utf-8") if l.strip()}
    feitos = sum(1 for _, d, _ in docs if d in meus)
    log = f"log_nac_{n:02d}.txt"
    tam = os.path.getsize(log) if os.path.exists(log) else 0
    print(f"   lote {n:02d}: {feitos:4d} feitos   log {tam:7d} bytes")
print()

# ------------------------------------------------- o CUI está a vir?
com_cui = sem_cui = 0
for _, d, t in docs[-40:]:
    if t != "ok":
        continue
    p = os.path.join(SAIDA, d, "pgx_outputs", "Extended_PGx_Analysis.json")
    try:
        j = json.load(open(p, encoding="utf-8"))
        cui = (j.get("identificadores_substancia") or {}).get("mrconso_cui")
        if cui:
            com_cui += 1
        else:
            sem_cui += 1
    except Exception:
        pass
print(f"nos últimos 40 documentos: {com_cui} com CUI, {sem_cui} sem CUI")

# ------------------------------------------------- tamanho da cache
cache = "RCMprocessor/data/cache/active_substance_external_cache.json"
if os.path.exists(cache):
    print(f"cache                  : {os.path.getsize(cache)/1e6:.1f} MB")

print()
print("últimas 15 linhas do log do lote 00:")
try:
    print("".join(open("log_nac_00.txt", encoding="utf-8").readlines()[-15:]))
except Exception as e:
    print(f"  ({e})")
