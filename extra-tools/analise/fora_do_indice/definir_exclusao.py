#!/usr/bin/env python3
"""Documentos da colheita que nao pertencem ao indice do INFOMED.

A pasta dos PDFs descarregados guardava 32 ficheiros de uma passagem anterior
do harvester cujo numero de registo nao existe no indice final (9 546
registos). Entraram na triagem com os restantes. Este script identifica-os e
decide o que acontece a cada grupo de texto de que fazem parte:

  - grupo so' de orfaos  -> o grupo sai do corpus (o representante sai)
  - grupo misto          -> o grupo fica; o representante passa a ser um
                            registo do indice com o mesmo texto, escolhido
                            pela regra da tese (marca primeiro, senao o
                            primeiro generico por ordem alfabetica)

Escreve exclusao.csv e representantes_novos.csv nesta pasta.
"""
import csv, json, os, collections
BASE = os.path.join(os.path.dirname(__file__), "..", "..", "..")
R = list(csv.DictReader(open(os.path.join(BASE, "dados/medicamentos.csv"), encoding="utf-8")))
ids = {r["med_id"] for r in R}
porfich = {}
for r in R:
    f = (r["rcm_filename"] or "").split("/")[-1]
    if f and f not in porfich: porfich[f] = r
imp = [json.loads(l) for l in open(os.path.join(BASE, "dados/preflight/impressoes.jsonl"), encoding="utf-8")]
orf = {r["ficheiro"] for r in imp if r["ficheiro"].split("_")[0] not in ids}
quar = {"1026_Bialzepam.pdf", "44766_Daivobet.pdf", "47138_Ionolyte.pdf", "642990_Zeflavon.pdf",
        "1028_Bialzepam.pdf", "1029_Bialzepam_Retard.pdf"}
reps = set(os.listdir(os.path.join(BASE, "RCMs_a_processar")))
g = collections.defaultdict(list)
for r in imp:
    if r.get("hash") and r["ficheiro"] not in quar: g[r["hash"]].append(r["ficheiro"])
def generico(f):  # os genericos do INFOMED terminam em "MG"
    return f[:-4].endswith("MG")
saem, trocas = [], []
for h, v in g.items():
    if not any(f in orf for f in v): continue
    rep = [f for f in v if f in reps]
    if all(f in orf for f in v):
        saem += [(f, "representante" if f in reps else "duplicado") for f in v]
    else:
        cand = sorted(f for f in v if f not in orf)
        marca = [f for f in cand if not generico(f)]
        novo = (marca or cand)[0]
        trocas.append((rep[0] if rep else "", novo, ";".join(f for f in v if f in orf)))
        saem += [(f, "duplicado orfao de grupo misto") for f in v if f in orf]
with open(os.path.join(os.path.dirname(__file__), "exclusao.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["ficheiro", "papel"]); w.writerows(sorted(saem))
with open(os.path.join(os.path.dirname(__file__), "representantes_novos.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["representante_antigo", "representante_novo", "orfaos_do_grupo"]); w.writerows(trocas)
print("orfaos:", len(orf), "| saem:", len(saem), "| representantes que saem:",
      sum(1 for f, p in saem if p == "representante"), "| grupos mistos:", len(trocas))
for t in trocas: print("   ", t[0], "->", t[1], "| med_id no indice:", t[1].split("_")[0] in ids, "|", porfich.get(t[1], {}).get("drug_name", "?"))
