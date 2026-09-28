#!/usr/bin/env python3
"""Numeros que saem da base de dados: prevalencia, entidades, genes, seccoes, cobertura."""
import collections, re, sys
from comum import bd, excluidos
def calcula(cen):
    c = bd(); X = excluidos(cen); out = {}
    docs = [(i, f, p, e) for i, f, p, e in c.execute("select id,ficheiro,tem_pgx,tem_entidades from documento") if f not in X]
    ids = {i for i, *_ in docs}
    N = len(docs); P = sum(p for *_, p, e in docs); E = sum(e for *_, e in docs)
    out.update(analisados=N, pgx=P, pgx_pct=round(100*P/N, 1), entidades=E, ent_pct=round(100*E/N, 1),
               pgx_sem_entidade=P-E, sem_pgx=N-P, ent_de_pgx_pct=round(100*E/P, 1))
    ent = [(d, t, v, g, m) for d, t, v, g, m in c.execute("select documento_id,tipo,valor,gene,mencoes from entidade") if d in ids]
    for t in ("gene", "alelo", "diplotipo"):
        out[f"mencoes_{t}"] = sum(m for d, tt, v, g, m in ent if tt == t)
        out[f"distintos_{t}"] = len({v for d, tt, v, g, m in ent if tt == t})
    out["mencoes_total"] = sum(m for *_, m in ent)
    gm = collections.Counter(); gd = collections.defaultdict(set)
    for d, t, v, g, m in ent:
        if g: gm[g] += m; gd[g].add(d)
    out["top_genes"] = [(g, n, len(gd[g])) for g, n in gm.most_common(12)]
    out["hlab_gene_docs"] = len({d for d, t, v, g, m in ent if t == "gene" and v == "HLA-B"})
    out["hlab_alelo_docs"] = len({d for d, t, v, g, m in ent if t in ("alelo", "diplotipo") and g == "HLA-B"})
    sec = collections.defaultdict(lambda: collections.Counter()); secdocs = collections.defaultdict(set)
    tipo = {i: (d, t) for i, d, t in c.execute("select id,documento_id,tipo from entidade")}
    for eid, s, m in c.execute("select entidade_id,seccao,mencoes from entidade_seccao"):
        d, t = tipo[eid]
        if d in ids: sec[s][t] += m; secdocs[s].add(d)
    tot = sum(sum(v.values()) for v in sec.values())
    out["seccoes"] = {s: (sec[s]["gene"], sec[s]["alelo"], sec[s]["diplotipo"], sum(sec[s].values()),
                          round(100*sum(sec[s].values())/tot, 1), len(secdocs[s])) for s in sorted(sec)}
    base = "from cobertura cb join guideline g on g.id=cb.guideline_id join documento d on d.id=cb.documento_id"
    cov = [(d, s, gene, fonte, est) for d, s, gene, fonte, est in
           c.execute(f"select d.id,d.substancia_id,g.gene,g.fonte,cb.estado {base}") if d in ids]
    pares = {(s, g) for d, s, g, f, e in cov}; cob = {(s, g) for d, s, g, f, e in cov if e == "coberta"}
    out.update(pares=len(pares), pares_cobertos=len(cob), pares_pct=round(100*len(cob)/len(pares), 1))
    dg = collections.defaultdict(list)
    for d, s, g, f, e in cov: dg[d].append(e)
    semnenhum = sum(1 for v in dg.values() if "coberta" not in v)
    out.update(docs_guideline=len(dg), docs_sem_gene=semnenhum, docs_sem_gene_pct=round(100*semnenhum/len(dg), 1))
    fontes = collections.defaultdict(lambda: [set(), set()])
    for d, s, g, f, e in cov:
        fontes[f][0].add((s, g))
        if e == "coberta": fontes[f][1].add((s, g))
    out["consorcios"] = {f: (len(a), round(100*len(a)/len(pares), 1), len(b), round(100*len(b)/len(cob), 1))
                         for f, (a, b) in sorted(fontes.items(), key=lambda x: -len(x[1][0]))}
    pos = collections.Counter(); posc = collections.Counter()
    for d, s, g, f, e in cov:
        pos[g] += 1
        if e == "coberta": posc[g] += 1
    top12 = pos.most_common(13)
    out["genes_exigidos_top13"] = [(g, n, posc[g]) for g, n in top12]
    pas = [(d, t) for d, t in c.execute("select documento_id,texto from passagem") if d in ids]
    out["passagens"] = len(pas)
    cyp = [d for d, t in pas if t and "CYP3A4" in t]
    ent3a4 = {d for d, t, v, g, m in ent if t == "gene" and v == "CYP3A4"}
    out.update(cyp3a4_passagens=len(cyp), cyp3a4_docs_entidade=len(ent3a4), cyp3a4_so_passagem=len(set(cyp)-ent3a4))
    out["hmgcr_mthfr_slc6a4_passagens"] = [sum(1 for d, t in pas if t and x in t) for x in ("HMGCR", "MTHFR", "SLC6A4")]
    return out
if __name__ == "__main__":
    a, b = calcula("atual"), calcula("B")
    for k in a:
        if a[k] != b[k] or k in ("analisados",):
            print(f"{k}:\n   atual {a[k]}\n   B     {b[k]}")
        else:
            print(f"{k}: igual {a[k] if not isinstance(a[k], (list, dict)) else '(igual)'}")
