#!/usr/bin/env python3
"""Semelhanca de caracteres da seccao 4.4 entre dois rotulos da mesma substancia.

Versao deterministica da amostra de comparar_seccoes.py: os 710 grupos de
substancia com a seccao 4.4 nao uniforme sao ordenados pelo nome, e com
random.Random(11) tiram-se 300 grupos e, em cada um, dois documentos. O
original tirava a amostra dentro de threads concorrentes, o que a tornava
irreprodutivel. Corre em bocados (limite de tempo por chamada) e guarda o
progresso em cache/semelhanca_44_<cenario>.pkl.
"""
import os, sys, json, pickle, random, difflib, re, time, collections
from comum import CACHE, FINAL, excluidos
ESP = re.compile(r"\s+")
def amostra(cen):
    X = excluidos(cen)
    subs = {d: s for d, s in pickle.load(open(os.path.join(CACHE, "subst_state.pkl"), "rb")).items() if s and d not in X}
    secs = pickle.load(open(os.path.join(CACHE, "secs_state.pkl"), "rb"))
    _, rows = pickle.load(open(os.path.join(CACHE, "cab_state.pkl"), "rb"))
    fich44 = {d: f for d, s, f in rows if s == "4.4"}
    g = collections.defaultdict(list)
    for d, s in subs.items(): g[s].append(d)
    cand = []
    for s in sorted(g):
        v = sorted(d for d in g[s] if d in secs and "4.4" in secs[d])
        if len(g[s]) > 1 and len(v) > 1 and len({secs[d]["4.4"] for d in v}) > 1: cand.append((s, v))
    rnd = random.Random(11)
    am = rnd.sample(cand, min(300, len(cand)))
    pares = [(s, *rnd.sample(v, 2)) for s, v in am]
    return len(cand), pares, fich44
def texto(d, fich44):
    o = json.load(open(os.path.join(FINAL, "out_nacional", d, fich44[d] + ".json"), encoding="utf-8"))
    return ESP.sub(" ", o.get("content") or "").strip()
if __name__ == "__main__":
    cen = sys.argv[1] if len(sys.argv) > 1 else "B"
    st = os.path.join(CACHE, f"semelhanca_44_{cen}.pkl")
    ncand, pares, fich44 = amostra(cen)
    feitos = pickle.load(open(st, "rb")) if os.path.exists(st) else {}
    t0 = time.time()
    for p in pares:
        if p in feitos: continue
        if time.time() - t0 > 140: break
        a, b = texto(p[1], fich44), texto(p[2], fich44)
        feitos[p] = difflib.SequenceMatcher(None, a, b).ratio() if a and b else None
        pickle.dump(feitos, open(st, "wb"))
    rs = sorted(r for p, r in feitos.items() if p in set(pares) and r is not None)
    print(f"grupos com 4.4 nao uniforme: {ncand} | pares feitos: {len([p for p in pares if p in feitos])}/{len(pares)}")
    if len([p for p in pares if p in feitos]) == len(pares):
        print(f"mediana {rs[len(rs)//2]:.2f} | >=99% iguais {100*sum(r>=.99 for r in rs)/len(rs):.1f}% | abaixo de 70% {100*sum(r<.70 for r in rs)/len(rs):.1f}%")
