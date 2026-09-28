#!/usr/bin/env python3
"""Perfil farmacogenomico por substancia (seccao 4.3.9): entidades por seccao normativa, documento a documento."""
import collections, pickle, os
from comum import CACHE, bd, excluidos
def calcula(cen, forma):
    X = excluidos(cen)
    subs = {d: s for d, s in pickle.load(open(os.path.join(CACHE, "subst_state.pkl"), "rb")).items() if s and d not in X}
    c = bd(); prof = collections.defaultdict(set)
    for f, sec, t, v in c.execute("select d.ficheiro,es.seccao,e.tipo,e.valor from entidade e join entidade_seccao es on es.entidade_id=e.id join documento d on d.id=e.documento_id"):
        prof[f].add(forma(sec, t, v))
    g = collections.defaultdict(list)
    for d, s in subs.items(): g[s].append(d)
    multi = {k: v for k, v in g.items() if len(v) > 1}
    iguais = [k for k, v in multi.items() if len({frozenset(prof.get(d, ())) for d in v}) == 1]
    vazios = [k for k in iguais if not prof.get(multi[k][0])]
    com = [k for k, v in multi.items() if any(prof.get(d) for d in v)]
    concordam = [k for k in com if k in iguais]
    return dict(substancias=len(multi), iguais=len(iguais), vazios=len(vazios), com_entidade=len(com), concordam=len(concordam), discordam=len(com)-len(concordam))
if __name__ == "__main__":
    print("tese: 721 | 630 iguais | 564 vazios | 157 com entidade | 66 concordam | 91 nao")
    for nome, f in (("(seccao,tipo,valor)", lambda s, t, v: (s, t, v)), ("(seccao,valor)", lambda s, t, v: (s, v))):
        for cen in ("atual", "B"): print(nome, cen, calcula(cen, f))
