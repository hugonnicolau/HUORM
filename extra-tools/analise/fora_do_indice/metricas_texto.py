#!/usr/bin/env python3
"""Numeros que saem dos ficheiros de saida da corrida: normalizacao, cabecalhos,
divergencia entre rotulos, tabela de concordancia por seccao."""
import collections, pickle, os, re
from comum import CACHE, bd, excluidos
NORM = ["4.2", "4.3", "4.4", "4.5", "4.8", "5.1", "5.2"]
ld = lambda n: pickle.load(open(os.path.join(CACHE, n), "rb"))
def normalizacao(cen):
    X = excluidos(cen); rows = ld("normalizacoes.pkl"); h = rows[0]
    R = [dict(zip(h, r)) for r in rows[1:] if r and r[0] and r[0] not in X]
    E = [r for r in R if r["Fonte"] == "Extended_PGx_Analysis" and r["Tipo entidade"]]
    m = collections.Counter()
    for r in E: m[r["Tipo entidade"]] += int(r["Nº menções"] or 0)
    G = [r for r in E if r["Tipo entidade"] == "gene"]
    forms = collections.defaultdict(set)
    for r in G: forms[r["Texto normalizado"]].add(str(r["Texto original"]).casefold())
    top = sorted(((len(v), k) for k, v in forms.items()), key=lambda x: (-x[0], x[1]))
    fig = ["G6PD", "HPRT1", "TPMT", "CYP2D6", "ABCB1", "CYP2C19", "MT-RNR1", "UGT1A1"]
    # documentos em que a expansao e' a unica razao de haver entidade
    c = bd()
    ent = collections.defaultdict(set)
    for f, v in c.execute("select d.ficheiro,e.valor from entidade e join documento d on d.id=e.documento_id"):
        if f not in X: ent[f].add(v)
    S = collections.defaultdict(set)
    for r in R:
        if r["Tipo"] == "nome_extenso_para_simbolo": S[r["Documento"]].add(r["Texto normalizado"])
    so = sum(1 for f, vs in ent.items() if vs and all(v in S.get(f, ()) for v in vs))
    return dict(eventos=len(E), docs=len({r["Documento"] for r in E}), mencoes_gene=m["gene"], mencoes_alelo=m["star_allele"],
                mencoes=sum(m.values()), simbolos=len(forms), grafias=sum(len(v) for v in forms.values()),
                figura={k: len(forms.get(k, ())) for k in fig},
                outros=(len([k for k in forms if k not in fig]), sum(len(forms[k]) for k in forms if k not in fig)),
                docs_expansao=len({r["Documento"] for r in R if r["Tipo"] == "nome_extenso_para_simbolo"}),
                so_por_expansao=so, com_entidade=len([f for f in ent if ent[f]]))
def cabecalhos(cen):
    X = excluidos(cen); _, rows = ld("cab_state.pkl")
    forms = collections.defaultdict(collections.Counter)
    for d, s, f in rows:
        if d not in X: forms[s][f] += 1
    tot = sum(len(c) for c in forms.values()); once = sum(1 for c in forms.values() for v in c.values() if v == 1)
    por = {s: (len(c), sum(c.values()), round(100*c.most_common(1)[0][1]/sum(c.values()), 1), sum(c.values())-c.most_common(1)[0][1]) for s, c in sorted(forms.items())}
    return dict(formas=tot, uma_vez=once, por_seccao=por)
def divergencia(cen):
    X = excluidos(cen)
    subs = {d: s for d, s in ld("subst_state.pkl").items() if s is not None and d not in X}
    s44 = ld("s44_state.pkl"); secs = ld("secs_state.pkl")
    c = bd(); pgx = {f: p for f, p in c.execute("select ficheiro,tem_pgx from documento") if f not in X}
    g = collections.defaultdict(list)
    for d, s in subs.items():
        if s: g[s].append(d)
    multi = {k: v for k, v in g.items() if len(v) > 1}
    com = [k for k, v in multi.items() if any(pgx.get(d) for d in v)]
    mix = [k for k in com if not all(pgx.get(d) for d in multi[k])]
    m44 = {k: [d for d in v if d in s44] for k, v in multi.items()}; m44 = {k: v for k, v in m44.items() if len(v) >= 2}
    c44 = [k for k, v in m44.items() if any(s44[d] for d in v)]; x44 = [k for k in c44 if not all(s44[d] for d in m44[k])]
    tab = {}
    for s in NORM:
        gr = uni = pi = pt = 0
        for v in multi.values():
            hs = [secs[d][s] for d in v if d in secs and s in secs[d]]
            if len(hs) < 2: continue
            gr += 1; uni += len(set(hs)) == 1
            n = len(hs); pt += n*(n-1)//2; pi += sum(x*(x-1)//2 for x in collections.Counter(hs).values())
        tab[s] = (gr, uni, round(100*pi/pt, 1))
    iguais7 = sum(1 for v in multi.values() if len({tuple(secs.get(d, {}).get(s, "-") for s in NORM) for d in v}) == 1)
    assin = collections.Counter(tuple(h.get(s) for s in NORM) for d, h in secs.items() if d not in X)
    ndocs = sum(assin.values())
    cand44 = [k for k, v in multi.items() if sum(1 for d in v if d in secs and "4.4" in secs[d]) > 1
              and len({secs[d]["4.4"] for d in v if d in secs and "4.4" in secs[d]}) > 1]
    return dict(substancias=len(multi), docs=sum(len(v) for v in multi.values()), com_pgx=len(com), misto=len(mix),
                misto_pct=round(100*len(mix)/len(com), 1), grupos44=len(m44), com44=len(c44), misto44=len(x44),
                misto44_pct=round(100*len(x44)/len(c44), 1), tabela=tab, sete_iguais=iguais7,
                colapsariam=ndocs-len(assin), colapsariam_de=ndocs, colapsariam_pct=round(100*(ndocs-len(assin))/ndocs, 2),
                grupos_44_divergentes=len(cand44))
if __name__ == "__main__":
    for nome, f in (("normalizacao", normalizacao), ("cabecalhos", cabecalhos), ("divergencia", divergencia)):
        a, b = f("atual"), f("B")
        print(f"===== {nome}")
        for k in a:
            print(f"  {k}: {'igual ' + str(a[k]) if a[k] == b[k] else 'atual ' + str(a[k]) + '  ->  B ' + str(b[k])}")
