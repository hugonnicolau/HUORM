#!/usr/bin/env python3
"""Resumo da corrida sobre os 17 do conjunto de referência.

Correr a partir de ~/Desktop/FINAL:
    python3 resumo_gabarito.py

Não altera nada. Só lê os outputs e imprime uma tabela.
"""
import json
import os
import sys

SAIDA = sys.argv[1] if len(sys.argv) > 1 else "out_gabarito_final"

POSITIVOS = {
    "RCM_alopurinol", "RCM_escitalopram", "RCM_Fentanilo", "RCM_Isoniazida",
    "RCM_omeprazol", "RCM_Rifampicina", "RCM_Risperidona", "RCM_sinvastatina",
    "RCM_siponimod", "RCM_tramadol", "RCM_varfarina",
}


def ler(pasta, nome):
    for p in (os.path.join(pasta, "pgx_outputs", nome), os.path.join(pasta, nome)):
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                return None
    return None


docs = sorted(d for d in os.listdir(SAIDA) if os.path.isdir(os.path.join(SAIDA, d)))
print(f"documentos com saída: {len(docs)}\n")

cab = f"{'documento':22s} {'esp':4s} {'PGx':4s} {'gene':5s} {'star':5s} {'dipl':5s} {'rsid':5s} {'CUI':5s} {'sec':4s}"
print(cab)
print("-" * len(cab))

falsos_neg, fabricacao, sem_cui = [], [], []

for d in docs:
    p = os.path.join(SAIDA, d)
    if os.path.exists(os.path.join(p, "NAO_UTILIZAVEL.json")):
        print(f"{d[:21]:22s} {'':4s} NAO UTILIZAVEL")
        continue

    ext = ler(p, "Extended_PGx_Analysis.json") or {}
    cls = ext.get("classificacao", {})
    cnt = ext.get("contagens_documento", {})
    ids = ext.get("identificadores_substancia", {})

    esperado = "+" if d in POSITIVOS else "-"
    tem = bool(cls.get("has_pgx"))
    g = cnt.get("genes_unicos_total", 0)
    s = cnt.get("star_alleles_unicos_total", 0)
    dp = cnt.get("diplotipos_unicos_total", 0)
    r = cnt.get("rsids_unicos_total", 0)
    cui = ids.get("mrconso_cui") or ""
    sec = cls.get("seccoes_com_pgx_total", 0)

    print(f"{d[:21]:22s} {esperado:4s} {'sim' if tem else 'nao':4s} "
          f"{g:<5d} {s:<5d} {dp:<5d} {r:<5d} {('ok' if cui else 'VAZIO'):5s} {sec:<4d}")

    total_ent = g + s + dp + r
    if esperado == "+" and not tem:
        falsos_neg.append(d)
    if esperado == "-" and total_ent > 0:
        fabricacao.append((d, total_ent))
    if not cui:
        sem_cui.append(d)

print()
print(f"falsos negativos nos positivos : {len(falsos_neg)}  {falsos_neg}")
print(f"FABRICAÇÃO nos negativos       : {len(fabricacao)}  {fabricacao}")
print(f"sem CUI do MRCONSO             : {len(sem_cui)}  {sem_cui}")

meta = ler(os.path.join(SAIDA, docs[0]), "Extended_PGx_Analysis.json") if docs else None
if meta:
    pm = meta.get("pipeline") or meta.get("pipeline_metadata") or {}
    if pm:
        print(f"\nproveniência: {json.dumps(pm, ensure_ascii=False)}")
