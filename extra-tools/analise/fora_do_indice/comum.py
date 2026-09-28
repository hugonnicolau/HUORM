"""Definicoes partilhadas pelos recalculos: caminhos, populacao atual e populacao sem os orfaos.

Escrito para medir o antes e o depois. Depois de aplicar_exclusao.py (26-09-2026)
a base e as pastas ja sao as do cenario B, e os dois cenarios dao o mesmo;
os caches em cache/ guardam o estado de antes."""
import csv, os, sqlite3
AQUI = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
CACHE = os.path.join(AQUI, "cache")
BD = os.path.join(FINAL, "basedados", "huorm.db")
EXC = {r["ficheiro"][:-4] for r in csv.DictReader(open(os.path.join(AQUI, "exclusao.csv"), encoding="utf-8"))
       if r["papel"] == "representante"}
TROCA = {r["representante_antigo"][:-4]: r["representante_novo"][:-4]
         for r in csv.DictReader(open(os.path.join(AQUI, "representantes_novos.csv"), encoding="utf-8"))}
ORFAOS = {r["ficheiro"][:-4] for r in csv.DictReader(open(os.path.join(AQUI, "exclusao.csv"), encoding="utf-8"))}
def excluidos(cenario):
    """cenario 'atual' nao exclui nada; 'B' exclui os 14 representantes orfaos."""
    return set() if cenario == "atual" else set(EXC)
def bd():
    return sqlite3.connect(BD)
