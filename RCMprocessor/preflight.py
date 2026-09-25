"""
Pré-voo: decidir o que processar antes de gastar o LLM.

O pipeline chama o modelo por documento. Com ~1min42 por RCM, os 7 800 do
corpus são vários dias. Este passo corre em minutos, sem LLM, e responde a três
perguntas antes de começar:

  1. Quais são digitalizações?          -> excluir, não têm texto para analisar
  2. Quais são duplicados exactos?      -> processar um, propagar o resultado
  3. Como dividir o resto em lotes?     -> gerir tokens e retomar em caso de falha

O ATC e a substância ativa vêm do `medicamentos.csv` do Infomed, não dos PDFs.
São campos estruturados do registo nacional: 5% sem ATC, contra 11% quando se
extrai do texto do documento. Extrair dos PDFs seria mais lento e mais pobre.

    python -m RCMprocessor.preflight <pasta_pdfs> --csv INFOMEDDATASET/medicamentos.csv
    python -m RCMprocessor.preflight <pasta_pdfs> --lotes 8

Produz, na pasta indicada por --out (por omissão `preflight/`):

    processar.txt            um caminho por linha — o que dar ao batch
    lote_01.txt … lote_NN.txt
    mapa_duplicados.csv      ficheiro -> representante, para propagar resultados
    digitalizacoes.csv       excluídos por não terem camada de texto
    relatorio.md
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .scanned_pdf_detector import (
    MAX_CONTROL_FRACTION,
    MIN_LETTER_FRACTION,
    MIN_WORD_DENSITY,
    _readability,
)

# Elementos que mudam entre reedições do mesmo RCM sem alterar o conteúdo.
VOLATEIS = [
    (re.compile(r"(?i)data\s+da\s+(?:primeira\s+)?(?:revis[ãa]o|aprova[çc][ãa]o)"
                r"\s+d[oe]\s+texto.{0,80}"), " "),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), " "),
    (re.compile(r"(?i)\bp[áa]gina\s+\d+\s*(?:de\s+\d+)?"), " "),
    (re.compile(r"(?i)\bAPROVADO\s+EM\b.{0,60}"), " "),
]

MIN_CARACTERES = 400
MARCAS_GENERICO = re.compile(
    r"(?i)\b(generis|ratiopharm|krka|sandoz|teva|viatris|mylan|zentiva|aurovitas|"
    r"pharmakern|bluepharma|azevedos|labesfal|ciclum|farmoz|tecnimede|medinfar|"
    r"accord|stada|normon|kern|cinfa|towa|alter|pentafarma|aristo|jaba)\b"
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def atc_normalizado(codigo: str) -> str:
    c = re.sub(r"[^A-Za-z0-9]", "", str(codigo or "")).upper()
    return c if re.fullmatch(r"[A-Z]\d{2}[A-Z]{2}\d{2}", c) else ""


def analisar_pdf(caminho_str: str) -> dict:
    """Extrai texto e calcula a impressão digital. Corre em paralelo."""
    caminho = Path(caminho_str)
    try:
        resultado = subprocess.run(
            ["pdftotext", "-layout", str(caminho), "-"],
            capture_output=True, text=True, timeout=120,
        )
        bruto = resultado.stdout
    except FileNotFoundError:
        return {"ficheiro": caminho.name, "erro": "pdftotext_ausente"}
    except Exception:  # noqa: BLE001
        return {"ficheiro": caminho.name, "erro": "falha_extracao"}

    compacto = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", bruto)).strip()

    if len(compacto) < MIN_CARACTERES:
        return {"ficheiro": caminho.name, "digitalizacao": True,
                "motivo": f"apenas {len(compacto)} caracteres",
                "caracteres": len(compacto)}

    # Texto em quantidade não é texto legível. Um PDF cuja fonte não traz mapa
    # de caracteres devolve códigos de glifo: o tramadol_oral tem 41 705
    # caracteres e nenhuma palavra portuguesa. Passa o teste de contagem, não
    # gera secção nenhuma, e custa ~1min42 de modelo para devolver zero.
    # Excluir aqui é a diferença entre gastar esse tempo e não gastar.
    legibilidade = _readability(compacto)
    if (legibilidade["control_fraction"] > MAX_CONTROL_FRACTION
            or legibilidade["word_density"] < MIN_WORD_DENSITY
            or legibilidade["letter_fraction"] < MIN_LETTER_FRACTION):
        return {"ficheiro": caminho.name, "digitalizacao": True,
                "motivo": (f"texto ilegível "
                           f"({legibilidade['word_density']:.2f} palavras/1000, "
                           f"{legibilidade['letter_fraction']:.0%} letras)"),
                "caracteres": len(compacto), **legibilidade}

    estavel = compacto
    for padrao, subst in VOLATEIS:
        estavel = padrao.sub(subst, estavel)
    estavel = re.sub(r"\s+", " ", estavel).strip().lower()

    return {
        "ficheiro": caminho.name,
        "digitalizacao": False,
        "caracteres": len(compacto),
        "hash": hashlib.sha256(estavel.encode()).hexdigest(),
    }


def carregar_metadados(csv_path: Path | None, ficheiros: list[Path]) -> dict:
    """Liga cada ficheiro ao seu ATC e substância ativa.

    A ligação é feita pelo número de registo no início do nome do ficheiro
    (`10020_fenolip.pdf` -> med_id 10020), que é a chave do Infomed e sobrevive
    à standardização dos nomes.
    """
    if not csv_path or not csv_path.exists():
        return {}

    por_id, por_nome = {}, {}
    for linha in csv.DictReader(csv_path.open(encoding="utf-8")):
        registo = {
            "med_id": linha.get("med_id", ""),
            "medicamento": linha.get("drug_name", ""),
            "substancia": linha.get("active_substance", ""),
            "atc": atc_normalizado((linha.get("atc_codes") or "").split(";")[0]),
            "titular": linha.get("mah", ""),
        }
        if registo["med_id"]:
            por_id[registo["med_id"]] = registo
        nome = (linha.get("rcm_filename") or "").strip()
        if nome:
            por_nome[nome] = registo

    saida = {}
    for f in ficheiros:
        if f.name in por_nome:
            saida[f.name] = por_nome[f.name]
            continue
        # Nomes standardizados ou com prefixo de composto: procura o med_id.
        m = re.search(r"(?:^|_)(\d{3,7})_", f.name)
        if m and m.group(1) in por_id:
            saida[f.name] = por_id[m.group(1)]
    return saida


def escolher_representante(grupo: list[dict]) -> dict:
    """Prefere o produto de marca; desempata por ordem alfabética.

    É a regra de Jeiziner et al. (2021) — original de marca, ou o primeiro
    genérico — tornada determinística para ser reproduzível.
    """
    originais = [g for g in grupo if not MARCAS_GENERICO.search(g.get("titular", ""))]
    escolhidos = originais or grupo
    return sorted(escolhidos, key=lambda g: (normalizar(g.get("medicamento", "")),
                                             g["ficheiro"]))[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pasta", help="pasta com os PDFs")
    parser.add_argument("--csv", default="INFOMEDDATASET/medicamentos.csv",
                        help="índice do Infomed, para o ATC e a substância")
    parser.add_argument("--out", default="preflight")
    parser.add_argument("--lotes", type=int, default=0,
                        help="dividir o que há para processar em N lotes")
    parser.add_argument("--sem-dedup", action="store_true",
                        help="apenas excluir digitalizações, sem deduplicar")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        sys.exit(f"Pasta não encontrada: {pasta}")

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    ficheiros = sorted(p for p in pasta.glob("*.pdf") if not p.name.startswith("._"))
    if not ficheiros:
        sys.exit(f"Sem PDFs em {pasta}")
    print(f"  PDFs encontrados : {len(ficheiros)}")

    cache = destino / "impressoes.jsonl"
    feitos = {}
    if cache.exists():
        for linha in cache.open(encoding="utf-8"):
            try:
                r = json.loads(linha)
                feitos[r["ficheiro"]] = r
            except Exception:
                continue
        print(f"  já analisados    : {len(feitos)}  (retoma)")

    pendentes = [str(f) for f in ficheiros if f.name not in feitos]
    if pendentes:
        print(f"  a analisar       : {len(pendentes)}")
        with cache.open("a", encoding="utf-8") as fh, \
                ProcessPoolExecutor(max_workers=args.workers) as pool:
            for i, r in enumerate(pool.map(analisar_pdf, pendentes, chunksize=20), 1):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                feitos[r["ficheiro"]] = r
                if i % 500 == 0:
                    fh.flush()
                    print(f"    {i}/{len(pendentes)}", flush=True)

    metadados = carregar_metadados(Path(args.csv), ficheiros)
    if not metadados:
        print("  ⚠ sem metadados do Infomed — a deduplicação usará só o texto")

    digitalizacoes = [r for r in feitos.values() if r.get("digitalizacao")]
    erros = [r for r in feitos.values() if r.get("erro")]
    utilizaveis = [r for r in feitos.values()
                   if not r.get("digitalizacao") and not r.get("erro")]

    # Colapsar por identidade do texto, sem agrupamento prévio.
    #
    # Até 19-09-2026 agrupava-se primeiro por código ATC — ou por
    # `SUB::<substância>` quando o registo não trazia código — e só depois se
    # comparava o texto dentro de cada grupo. Era a transposição directa do
    # Jeiziner et al. (2021), mas aqui não acrescentava nada e partia grupos
    # que deviam ter colapsado: a mesma substância caía nas duas formas de
    # chave, que nunca se comparavam entre si. O lisinopril tinha 3 produtos em
    # C09AA03 e 10 em SUB::lisinopril. Foram 16 substâncias nessa situação e
    # escaparam 38 documentos com texto rigorosamente igual.
    #
    # A auditoria de 19-09 verificou os 37 grupos que a chave partia: 21 eram a
    # mesma substância, 10 tinham a substância em branco nalguns registos, e
    # dos 6 restantes cinco eram os ficheiros contaminados e um era o mesmo
    # produto com a substância rotulada de outra maneira. Zero casos em que
    # colapsar juntasse dois medicamentos realmente diferentes.
    #
    # A chave era, portanto, uma optimização que só fazia mal. O critério
    # sempre foi a identidade do texto, e é o que a tese afirma.
    grupos: dict = defaultdict(lambda: defaultdict(list))
    for r in utilizaveis:
        meta = metadados.get(r["ficheiro"], {})
        grupos["TEXTO"][r["hash"]].append({**r, **meta})

    representantes, mapa = [], []
    for chave, agrupados in grupos.items():
        for _, membros in agrupados.items():
            if args.sem_dedup:
                representantes.extend(m["ficheiro"] for m in membros)
                continue
            escolhido = escolher_representante(membros)
            representantes.append(escolhido["ficheiro"])
            for m in membros:
                if m["ficheiro"] != escolhido["ficheiro"]:
                    mapa.append({
                        "ficheiro": m["ficheiro"],
                        "representante": escolhido["ficheiro"],
                        "chave_grupo": chave,
                        "substancia_ativa": m.get("substancia", ""),
                        "medicamento": m.get("medicamento", ""),
                    })

    representantes.sort()
    (destino / "processar.txt").write_text(
        "\n".join(str(pasta / f) for f in representantes) + "\n", encoding="utf-8")

    if args.lotes > 0:
        tamanho = -(-len(representantes) // args.lotes)
        for n in range(args.lotes):
            fatia = representantes[n * tamanho:(n + 1) * tamanho]
            if fatia:
                (destino / f"lote_{n + 1:02d}.txt").write_text(
                    "\n".join(str(pasta / f) for f in fatia) + "\n", encoding="utf-8")

    def gravar(nome: str, linhas: list[dict]) -> None:
        if linhas:
            with (destino / nome).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
                w.writeheader()
                w.writerows(linhas)

    gravar("mapa_duplicados.csv", mapa)
    gravar("digitalizacoes.csv", [{"ficheiro": r["ficheiro"],
                                   "caracteres": r.get("caracteres", 0),
                                   "motivo": r.get("motivo", ""),
                                   "palavras_por_1000": r.get("word_density", ""),
                                   "fracao_letras": r.get("letter_fraction", ""),
                                   "fracao_controlo": r.get("control_fraction", "")}
                                  for r in digitalizacoes])

    poupados = len(utilizaveis) - len(representantes)
    minutos = poupados * 1.7

    print("\n" + "=" * 66)
    print("PRÉ-VOO")
    print("=" * 66)
    print(f"  PDFs                     : {len(ficheiros)}")
    print(f"  digitalizações excluídas : {len(digitalizacoes)}")
    if erros:
        print(f"  erros de extração        : {len(erros)}")
    print(f"  utilizáveis              : {len(utilizaveis)}")
    print(f"  grupos de texto idêntico : {len(grupos['TEXTO'])}")
    print(f"  A PROCESSAR              : {len(representantes)}")
    print(f"  duplicados poupados      : {poupados}"
          f"  ({100 * poupados / max(len(utilizaveis), 1):.1f}%)")
    print(f"  tempo poupado estimado   : ~{minutos / 60:.0f} h  (a 1min42/doc)")
    if args.lotes:
        print(f"  lotes criados            : {args.lotes}")
    print(f"\n  {destino}")
    print("\n  A seguir:")
    print(f"    python -m RCMprocessor.batch_processor <pasta> <out> "
          f"--file-list {destino / 'processar.txt'}")
    print(f"    e no fim, propagar via {destino / 'mapa_duplicados.csv'}")

    linhas_md = [
        "# Pré-voo\n",
        f"- PDFs inspecionados: **{len(ficheiros)}**",
        f"- Digitalizações excluídas: **{len(digitalizacoes)}**",
        f"- Utilizáveis: **{len(utilizaveis)}**",
        f"- Grupos de texto idêntico: **{len(grupos['TEXTO'])}**",
        f"- **A processar: {len(representantes)}**",
        f"- Duplicados exactos poupados: **{poupados}** "
        f"({100 * poupados / max(len(utilizaveis), 1):.1f}%)\n",
        "## Método\n",
        "Colapsam-se os documentos cujo texto é idêntico depois de neutralizar "
        "datas de revisão e paginação. O representante é o produto de marca; "
        "na sua ausência, o primeiro genérico por ordem alfabética.\n",
        "A comparação não é restringida por código ATC nem por substância "
        "ativa: dois documentos com o mesmo texto são o mesmo documento, "
        "venham do registo que vierem. Restringir por ATC partia grupos que "
        "deviam ter colapsado, porque a mesma substância aparece com e sem "
        "código no índice do Infomed.\n",
        "Documentos com texto diferente **não** são colapsados, mesmo para a "
        "mesma substância. Nos RCM portugueses isso é a regra e não a exceção: "
        "cada titular redige o seu, ao contrário dos rótulos suíços em que os "
        "genéricos adotam o texto do original.\n",
    ]
    (destino / "relatorio.md").write_text("\n".join(linhas_md), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
