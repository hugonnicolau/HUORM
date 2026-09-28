#!/usr/bin/env python3
"""Numeros do capitulo 3: grupo farmacoterapeutico, rsID, comparacao por substancia, titulares."""
import collections, pickle, os, re, sys, csv, json, statistics
from comum import CACHE, FINAL, excluidos, EXC, TROCA, ORFAOS
sys.path.insert(0, os.path.join(FINAL, "RCMprocessor"))
ld = lambda n: pickle.load(open(os.path.join(CACHE, n), "rb"))
def grupos(cen):
    import markdown_processor as mp
    cls = [v for v in vars(mp).values() if isinstance(v, type) and hasattr(v, "_extrair_grupo_farmacoterapeutico")][0]
    X = excluidos(cen); full = ld("grpfull.pkl"); st = ld("grp_state.pkl")
    reg = {}  # documento -> (tem_cabecalho, codigo, rotulo, analisado)
    for d, v in full.items():
        if d in X: continue
        if st.get(d) == "inutilizavel":
            o = cls.__new__(cls); o.md_text = md(d) or ""
            g, cod = o._extrair_grupo_farmacoterapeutico(); reg[d] = (bool(g), cod, g or "", False)
        else:
            reg[d] = (v is not None, v[0] if v else None, v[1] if v else "", True)
    com = {d: r for d, r in reg.items() if r[1]}; semcab = [d for d, r in reg.items() if not r[0]]
    semcod = [d for d, r in reg.items() if r[0] and not r[1]]; semcod_an = [d for d in semcod if reg[d][3]]
    desc = {d: reg[d][2] for d in semcod_an}
    rom = {d for d, t in desc.items() if re.match(r'^\s*[IVX]{1,4}\b', t)}
    cod = {d for d, t in desc.items() if re.search(r'\d+(\.\d+){1,}', t)}
    hom = {d for d, t in desc.items() if re.search(r'(?i)homeop', t)}
    so_desc = [d for d in desc if d not in rom | cod | hom]
    rot = re.compile(r'(?i)(?:c[oó]digo\s*[-–]?\s*ATC|ATC\s*code|classifica[çc][ãa]o\s*ATC|ATC)\s*[:–\-]?\s*([A-Z][\s\-]*[0-9O][\s\-]*[0-9O][^\n]{0,20})')
    atc_imp = sum(1 for d in so_desc if rot.search(md(d) or ""))
    lab = collections.defaultdict(set)
    for d, (_, c, g, _) in com.items():
        lab[c].add(re.sub(r'^[\s\-–—.:;,]+', '', g[len(c):] if g.startswith(c) else g))
    top = max(lab.items(), key=lambda x: len(x[1]))
    nivel1 = collections.Counter(c.split(".")[0] for _, c, _, _ in com.values())
    return dict(corpus=len(reg), com_codigo=len(com), sem_codigo=len(reg)-len(com), sem_cabecalho=len(semcab),
                cabecalho_sem_codigo=len(semcod), analisados_sem_codigo=len(semcod_an), descricao=len(so_desc),
                descricao_com_atc=atc_imp, codigo_noutro_sitio=len(cod), romanos=len(rom), homeopaticos=len(hom),
                codigos=len(lab), rotulos=sum(len(v) for v in lab.values()), codigos_varios=sum(1 for v in lab.values() if len(v) > 1),
                max_rotulos=(top[0], len(top[1])), nivel1=dict(sorted(nivel1.items(), key=lambda x: int(x[0]))))
def md(d):
    p = os.path.join(FINAL, "markdown", d + ".md")
    if not os.path.exists(p):
        pref = d.split("_")[0] + "_"
        cand = [f for f in os.listdir(os.path.join(FINAL, "markdown")) if f.startswith(pref)]
        p = os.path.join(FINAL, "markdown", cand[0]) if len(cand) == 1 else p
    return open(p, encoding="utf-8", errors="ignore").read() if os.path.exists(p) else None
def rsid(cen):
    X = excluidos(cen); st = ld("grp_state.pkl")
    hits = []; falta = []
    for d in st:
        if d in X: continue
        t = md(d)
        if t is None: falta.append(d); continue
        if re.search(r'(?i)\brs\d{3,}\b', t): hits.append(d)
    return dict(documentos=len([d for d in st if d not in X]), com_padrao=hits, sem_markdown=falta)
if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "grupos"
    f = {"grupos": grupos, "rsid": rsid}[what]
    a, b = f("atual"), f("B")
    for k in a: print(f"  {k}: {'igual ' + str(a[k]) if a[k] == b[k] else 'atual ' + str(a[k]) + '  ->  B ' + str(b[k])}")
