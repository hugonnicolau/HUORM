#!/usr/bin/env python3
"""Confirma que a cache passou a ser aceite pelo portão do resolve().

Correr a partir de ~/Desktop/FINAL:
    python3 verificar_cache.py

Antes do pré-aquecimento dava 0%.
"""
import json
from pathlib import Path

CACHE = Path("RCMprocessor/data/cache/active_substance_external_cache.json")
c = json.loads(CACHE.read_text(encoding="utf-8"))


def passa(v):
    refs = (v or {}).get("references") or {}
    if "mrconso" not in refs:
        return False
    t = json.dumps(refs["mrconso"], ensure_ascii=False).lower()
    return ("mrconso_path" not in t and "chebi_id" not in t
            and "drugbank_id" in t and "english_terms" in t)


ok = [k for k, v in c.items() if passa(v)]
mau = [k for k, v in c.items() if not passa(v)]
total = max(len(c), 1)
print(f"entradas na cache : {len(c)}")
print(f"PASSAM no portão  : {len(ok)}  ({100*len(ok)/total:.1f}%)")
print(f"ainda falham      : {len(mau)}")
if mau:
    print(f"  exemplos: {mau[:6]}")
print()

for q in ("siponimod", "varfarina", "alopurinol", "abacavir", "voriconazol",
          "carbamazepina", "clopidogrel"):
    achou = None
    for k, v in c.items():
        if any(t.strip().lower() == q for t in k.split("|")):
            achou = (k, v)
            break
    if not achou:
        print(f"  {q:15s} (não está na cache)")
        continue
    k, v = achou
    rb = ((v.get("references") or {}).get("mrconso") or {}).get("results_by_substance") or {}
    b = {}
    for kk, vv in rb.items():
        if kk.strip().lower() == q:
            b = vv.get("best_match") or {}
            break
    if not b and rb:
        b = (list(rb.values())[0] or {}).get("best_match") or {}
    exp = v.get("queries_expandidas") or []
    print(f"  {q:15s} {'OK ' if passa(v) else 'MAU'} cui={b.get('cui','-'):11s} "
          f"db={b.get('drugbank_id','-'):9s} expandidas={len(exp)}")

print()
print("o siponimod tem de dar C3657824 / DB12371")
