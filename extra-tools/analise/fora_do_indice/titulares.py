#!/usr/bin/env python3
"""Pares duplicado -> representante: mesmo titular de AIM ou nao (seccao 3.3.2)."""
import csv, collections, os
import comparacao_substancia as cs
def calcula(cen):
    reps, rep_of, desc = cs.mapa(cen)
    mah = {}
    for r in cs.R:
        f = (r["rcm_filename"] or "").split("/")[-1][:-4]
        if f: mah.setdefault(f, (r.get("mah") or "").strip())
    c = collections.Counter()
    for d, rep in rep_of.items():
        a, b = mah.get(d, ""), mah.get(rep, "")
        c["sem titular" if not a or not b else ("mesmo" if a.casefold() == b.casefold() else "diferente")] += 1
    n = sum(c.values()) + len(desc)
    return dict(pares=n, **c, desconhecidos=len(desc), minimo=round(100*c["mesmo"]/n, 2), maximo=round(100*(c["mesmo"]+len(desc))/n, 2))
if __name__ == "__main__":
    for cen in ("atual", "B"): print(cen, calcula(cen))
