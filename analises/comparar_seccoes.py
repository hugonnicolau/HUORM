"""
Compara, entre documentos da mesma substancia activa, o texto das seccoes
normativas. Produz os numeros da Tabela 3.x e do paragrafo que lhe segue.

A pergunta que responde: dois RCM da mesma substancia diferem so no nome da
empresa, ou diferem no texto clinico? A deduplicacao do capitulo 3 compara o
documento inteiro, que inclui a seccao 7 (titular da AIM e morada); por isso
nao consegue distinguir os dois casos. Aqui comparam-se apenas as sete
seccoes normativas extraidas pelo pipeline, das quais a 7 nao faz parte.

Uso:
    python analises/comparar_seccoes.py out_nacional
    python analises/comparar_seccoes.py out_nacional --csv resultados.csv

Nota sobre os nomes dos ficheiros: os RCM portugueses escrevem os cabecalhos
das seccoes de todas as maneiras possiveis, e o pipeline nomeia o ficheiro a
partir do cabecalho. Ha mais de 130 grafias distintas no corpus
("Contra_indicacoes", "CONTRAINDICACOES", "Contraindicativos", ...). Por isso
este script NAO procura ficheiros pelo nome: le todos os JSON da pasta e
identifica a seccao pelo campo "numero" de dentro do ficheiro.
"""
import os, sys, json, re, csv, random, difflib, hashlib
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor

FORA = {"ATC.json", "Substancia_ativa.json", "Nome_do_Medicamento.json",
        "Grupo_farmacoterapeutico.json", "NAO_UTILIZAVEL.json"}
NORM = ["4.2", "4.3", "4.4", "4.5", "4.8", "5.1", "5.2"]
NOME = {"4.2": "Posologia", "4.3": "Contraindicacoes", "4.4": "Advertencias",
        "4.5": "Interaccoes", "4.8": "Efeitos indesejaveis",
        "5.1": "Farmacodinamica", "5.2": "Farmacocinetica"}
ESP = re.compile(r"\s+")

def limpo(t): return ESP.sub(" ", t or "").strip()
def h(t): return hashlib.sha1(limpo(t).encode()).hexdigest()[:16]

def ler(p):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return None

def recolhe(raiz, d):
    pasta = os.path.join(raiz, d)
    if os.path.exists(os.path.join(pasta, "NAO_UTILIZAVEL.json")):
        return None
    sa = ler(os.path.join(pasta, "Substancia_ativa.json"))
    subst = None
    if isinstance(sa, dict):
        subst = sa.get("substancia_ativa") or sa.get("content") or sa.get("valor")
    if isinstance(subst, list): subst = " + ".join(map(str, subst))
    reg = {"doc": d, "subst": str(subst).strip().lower() if subst else None, "sec": {}}
    try: fichs = [f for f in os.listdir(pasta) if f.endswith(".json") and f not in FORA]
    except OSError: fichs = []
    for f in fichs:
        o = ler(os.path.join(pasta, f))
        if not isinstance(o, dict): continue
        num = str(o.get("numero") or "").strip()
        if num not in NORM: continue
        txt = o.get("content") or ""
        av = o.get("avaliacao_farmacogenomica") or {}
        pgx = str(av.get("contem_farmacogenomica", "")).lower().startswith("sim")
        novo = {"hash": h(txt), "n": len(limpo(txt)), "pgx": pgx, "fich": f}
        # a mesma seccao pode sair em dois ficheiros; fica a versao mais longa
        if num not in reg["sec"] or novo["n"] > reg["sec"][num]["n"]:
            reg["sec"][num] = novo
    return reg

def main():
    raiz = sys.argv[1] if len(sys.argv) > 1 else "out_nacional"
    csv_saida = None
    if "--csv" in sys.argv: csv_saida = sys.argv[sys.argv.index("--csv") + 1]
    ds = [d for d in sorted(os.listdir(raiz)) if os.path.isdir(os.path.join(raiz, d))]
    print(f"a ler {len(ds)} pastas...", flush=True)
    with ThreadPoolExecutor(32) as ex:
        docs = [r for r in ex.map(lambda d: recolhe(raiz, d), ds) if r]
    print(f"documentos utilizaveis: {len(docs)}")

    g = defaultdict(list)
    for d in docs:
        if d["subst"]: g[d["subst"]].append(d)
    multi = {k: v for k, v in g.items() if len(v) > 1}
    print(f"substancias: {len(g)}   com mais de um documento: {len(multi)} "
          f"({sum(len(v) for v in multi.values())} documentos)\n")

    iguais_tudo = sum(
        1 for v in multi.values()
        if len({tuple(d["sec"].get(s, {}).get("hash", "-") for s in NORM) for d in v}) == 1)
    print(f"grupos em que as sete seccoes coincidem em todos os documentos: {iguais_tudo}\n")

    linhas = []
    print(f"{'sec':5}{'':22}{'grupos':>8}{'uniformes':>11}{'pares iguais':>14}{'%':>8}")
    for s in NORM:
        gr = uni = pi = pt = 0
        for v in multi.values():
            hs = [d["sec"][s]["hash"] for d in v if s in d["sec"]]
            if len(hs) < 2: continue
            gr += 1
            if len(set(hs)) == 1: uni += 1
            n = len(hs); pt += n * (n - 1) // 2
            pi += sum(x * (x - 1) // 2 for x in Counter(hs).values())
        pct = pi / pt * 100 if pt else 0.0
        linhas.append({"seccao": s, "conteudo": NOME[s], "grupos": gr,
                       "uniformes": uni, "pares_iguais": pi, "pares": pt,
                       "pct_pares_iguais": round(pct, 1)})
        print(f"{s:5}{NOME[s]:22}{gr:8}{uni:11}{pi:14}{pct:7.1f}%")

    print(f"\n{'sec':5}{'grupos c/ PGx':>15}{'todos tem':>11}{'discordam':>11}{'%':>8}")
    for s in NORM:
        tod = dis = 0
        for v in multi.values():
            f = [d["sec"][s]["pgx"] for d in v if s in d["sec"]]
            if len(f) < 2 or not any(f): continue
            if all(f): tod += 1
            else: dis += 1
        print(f"{s:5}{tod+dis:15}{tod:11}{dis:11}{dis/(tod+dis)*100 if tod+dis else 0:7.1f}%")

    nen = tod = dis = 0
    for v in multi.values():
        f = [any(x["pgx"] for x in d["sec"].values()) for d in v]
        if not any(f): nen += 1
        elif all(f): tod += 1
        else: dis += 1
    print(f"\ndocumento inteiro: {nen} grupos sem PGx, {tod} em que todos tem, "
          f"{dis} em que uns tem e outros nao ({dis/(tod+dis)*100:.1f}% dos {tod+dis} com PGx)")

    # semelhanca do texto da 4.4, amostra aleatoria
    cand = [v for v in multi.values()
            if sum(1 for d in v if "4.4" in d["sec"]) > 1
            and len({d["sec"]["4.4"]["hash"] for d in v if "4.4" in d["sec"]}) > 1]
    random.seed(11)
    def texto(d):
        o = ler(os.path.join(raiz, d["doc"], d["sec"]["4.4"]["fich"]))
        return limpo(o.get("content")) if isinstance(o, dict) else ""
    def semelhanca(v):
        a, b = random.sample([d for d in v if "4.4" in d["sec"]], 2)
        ta, tb = texto(a), texto(b)
        return difflib.SequenceMatcher(None, ta, tb).ratio() if ta and tb else None
    am = random.sample(cand, min(300, len(cand)))
    with ThreadPoolExecutor(32) as ex:
        rs = sorted(r for r in ex.map(semelhanca, am) if r is not None)
    print(f"\nseccao 4.4, {len(rs)} pares de grupos divergentes (de {len(cand)}):")
    print(f"   mediana {rs[len(rs)//2]:.3f}   Q1 {rs[len(rs)//4]:.3f}   Q3 {rs[3*len(rs)//4]:.3f}")
    print(f"   >=99% iguais: {sum(1 for r in rs if r>=.99)/len(rs)*100:.1f}%   "
          f"abaixo de 70%: {sum(1 for r in rs if r<.70)/len(rs)*100:.1f}%")

    if csv_saida:
        with open(csv_saida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader(); w.writerows(linhas)
        print(f"\nescrito: {csv_saida}")

if __name__ == "__main__":
    main()
