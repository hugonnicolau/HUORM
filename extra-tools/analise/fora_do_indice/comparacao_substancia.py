#!/usr/bin/env python3
"""Seccao 3.3.2 e Figura 3.3: quantos textos distintos sobrevivem em cada grupo de substancia.

Populacao: os representantes analisados mais os duplicados que neles colapsaram.
Chave: o primeiro codigo ATC de cinco niveis do registo de cada documento no
indice do INFOMED, ou a substancia activa quando o registo nao tem nenhum.
Identidade de texto: o representante para que cada duplicado colapsou,
reconstruido a partir do mapa do preflight, da lista DUPLICADOS_A_REMOVER e
das correccoes de integridade. Os duplicados cujo representante nao ficou
registado (ficheiros descarregados de novo) ficam de fora e sao contados.
"""
import csv, json, collections, statistics, re, os, sqlite3, sys
from comum import FINAL, excluidos, TROCA, ORFAOS, bd
D = lambda *p: os.path.join(FINAL, *p)
R = list(csv.DictReader(open(D("dados/medicamentos.csv"), encoding="utf-8")))
rec = {}; por_id = {}
for r in R:
    por_id.setdefault(r["med_id"], r)
    f = (r["rcm_filename"] or "").split("/")[-1][:-4]
    if f and f not in rec: rec[f] = r
H = {}
for l in open(D("dados/preflight/impressoes.jsonl"), encoding="utf-8"):
    r = json.loads(l)
    if "hash" in r: H[r["ficheiro"][:-4]] = r["hash"]
quar = {"1026_Bialzepam", "44766_Daivobet", "47138_Ionolyte", "642990_Zeflavon", "1028_Bialzepam", "1029_Bialzepam_Retard"}
pasta = {f[:-4] for f in os.listdir(D("RCMs_a_processar"))}
def mapa(cen):
    X = excluidos(cen)
    reps = set(pasta) - X
    if cen == "B":
        reps = (reps - set(TROCA)) | set(TROCA.values())
    byhash = collections.defaultdict(list)
    for f in reps:
        if f in H: byhash[H[f]].append(f)
    rep_of = {}; desconhecido = []
    fontes = [(r["ficheiro"][:-4], r["representante"][:-4]) for r in csv.DictReader(open(D("dados/preflight/mapa_duplicados.csv"), encoding="utf-8"))]
    fontes += [(l.strip()[:-4], None) for l in open(D("extra-tools/dados/DUPLICADOS_A_REMOVER.txt"), encoding="utf-8") if l.strip()]
    for d, rep in fontes:
        if d in quar or d in reps or (cen == "B" and d in ORFAOS): continue
        if rep is None or rep not in reps:
            cand = [x for x in byhash.get(H.get(rep), []) + byhash.get(H.get(d), []) if x != d]
            rep = cand[0] if cand else None
        if rep: rep_of[d] = rep
    for d in ["648204_Ajovy", "748126_Aprovel_DP_Abacus_Medicine", "24_Acfol", "203_Aldomet_Forte", "746027_Aerius_DP_Abacus_Medicine"]:
        desconhecido.append(d)
    return reps, rep_of, desconhecido
def chave(f):
    r = rec.get(f) or por_id.get(f.split("_")[0])
    if not r: return None
    codes = [a.strip() for a in re.split(r'[;,|]', r["atc_codes"]) if a.strip()]
    five = [a for a in codes if len(a) == 7]
    return "ATC:" + five[0] if five else "SUB:" + r["active_substance"].strip().lower()
def calcula(cen):
    reps, rep_of, desc = mapa(cen)
    c = bd(); analis = {f for (f,) in c.execute("select ficheiro from documento")} - excluidos(cen)
    if cen == "B": analis = (analis - set(TROCA)) | set(TROCA.values())
    pop = set(analis) | {d for d, r in rep_of.items() if r in analis}
    semchave = [f for f in pop if chave(f) is None]
    g = collections.defaultdict(list)
    for f in pop:
        k = chave(f)
        if k: g[k].append(rep_of.get(f, f))
    multi = {k: v for k, v in g.items() if len(v) > 1}
    rp = [k for k, v in multi.items() if len(set(v)) < len(v)]
    ident = [k for k, v in multi.items() if len(set(v)) == 1]
    dist = [len(set(v)) for v in multi.values()]
    barras = collections.Counter(min(x, 13) for x in dist)
    ibu = g.get("ATC:M01AE01", [])
    return dict(populacao=len(pop), sem_chave=len(semchave), duplicados_sem_representante=len(desc), grupos=len(g),
                multi=len(multi), com_repeticao=len(rp), identicos=len(ident),
                pct_rep=round(100*len(ident)/len(rp), 1), pct_multi=round(100*len(ident)/len(multi), 1),
                mediana=statistics.median(dist), maximo=max(dist), barras=[barras[i] for i in range(1, 14)],
                ibuprofeno=(len(ibu), len(set(ibu))))
if __name__ == "__main__":
    print("tese  : grupos 1294 | multi 824 | repeticao 378 | identicos 86 (22.8% / 10.4%) | mediana 3 | ibuprofeno 81/76")
    print("        barras [86,212,127,91,64,43,36,22,9,15,8,12,99]")
    for cen in ("atual", "B"): print(cen, calcula(cen))
