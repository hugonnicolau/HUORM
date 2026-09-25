#!/usr/bin/env python3
"""Constroi a base de dados SQLite a partir das saidas do pipeline.

Le os Document_Unique_PGx.json de cada documento processado e escreve
huorm.db. Nao chama o modelo nem toca no corpus: e uma transformacao de
formato sobre resultados que ja existem, e por isso e reproduzivel a custo
zero sempre que a corrida for refeita.

Uso, a partir de FINALV2:
    python basedados/construir_bd.py out_nacional basedados/huorm.db

Verificar depois:
    python basedados/construir_bd.py --verificar basedados/huorm.db
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


# --- atribuicao de entidade a gene -------------------------------------
# CYP2C19*2 pertence a CYP2C19; SLCO1B1c.521CC pertence a SLCO1B1; "CC"
# solto nao pertence a gene nenhum e fica sem atribuicao, que e a resposta
# correcta e nao uma falha.
_HGVS = re.compile(r"^([A-Z][A-Z0-9-]{2,})c\.\d+", re.IGNORECASE)
_BASES = re.compile(r"^([A-Z][A-Z0-9-]{2,}?)[ACGT]{2}$", re.IGNORECASE)


def gene_de(valor: str) -> str | None:
    v = (valor or "").strip()
    if not v:
        return None
    if "*" in v:
        return v.split("*", 1)[0].upper() or None
    m = _HGVS.match(v) or _BASES.match(v)
    return m.group(1).upper() if m else None


def _texto(v) -> str:
    return str(v).strip() if v is not None else ""


# --- valor canonico de uma entidade ------------------------------------
# Tem de coincidir, campo a campo, com _entity_value do pgx_global_analysis:
# e ele que produz as contagens do Excel e, por essa via, os numeros da tese.
#
# A ordem importa. Um item pode trazer 'entity' e 'symbol' preenchidos com
# valores diferentes; ler primeiro um ou o outro atribui as mesmas mencoes a
# rotulos distintos. Com a ordem trocada, esta base dava 4 437 mencoes de
# genes onde o pipeline conta 4 435.
_HLA_SEM_DOIS_PONTOS = re.compile(r"^(HLA-[A-Z]+\d*)\*(\d{4})$", re.IGNORECASE)


def _canonizar(valor: str) -> str:
    """HLA-B*1502 -> HLA-B*15:02. Mais nada e' convertido.

    Quatro digitos sao 2+2 em todas as designacoes correntes. Cinco ou mais
    admitem varias leituras e ficam como estao, para nao inventar.
    """
    m = _HLA_SEM_DOIS_PONTOS.match(valor or "")
    if m:
        return f"{m.group(1).upper()}*{m.group(2)[:2]}:{m.group(2)[2:]}"
    return valor


def valor_entidade(item: dict) -> str:
    return _canonizar(_texto(
        item.get("entity") or item.get("variant")
        or item.get("symbol") or item.get("rsid")))


# Ficheiros da pasta do documento que nao sao seccoes normativas.
_NAO_SECCAO = {"ATC.json", "Substancia_ativa.json", "Nome_do_Medicamento.json",
               "Grupo_farmacoterapeutico.json", "NAO_UTILIZAVEL.json"}


def ler_entidades_das_seccoes(pasta: Path) -> tuple[dict, bool]:
    """({categoria: {valor: {seccao: mencoes}}}, tem_pgx) lido seccao a seccao.

    Nao se procuram os ficheiros pelo nome. Os RCM portugueses escrevem os
    cabecalhos de todas as maneiras e o pipeline nomeia o ficheiro a partir
    do cabecalho, o que da mais de 130 grafias no corpus
    ("Contra_indicacoes", "CONTRAINDICACOES", "Contraindicativos", ...). A
    seccao identifica-se pelo campo "numero" de dentro do ficheiro.
    """
    fora: dict[str, dict[str, dict[str, int]]] = {}
    tem_pgx = False
    try:
        fichs = [f for f in pasta.iterdir()
                 if f.suffix == ".json" and f.name not in _NAO_SECCAO]
    except OSError:
        return fora, False

    for f in fichs:
        try:
            o = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(o, dict):
            continue
        av = o.get("avaliacao_farmacogenomica")
        if not isinstance(av, dict):
            continue
        # Conteudo PGx e' uma coisa, entidade extraida e' outra: 3 142
        # documentos falam de genetica e so 1 206 nomeiam uma entidade. Sao
        # duas colunas distintas e nao podem sair do mesmo sinalizador.
        if str(av.get("contem_farmacogenomica", "")).lower().startswith("sim"):
            tem_pgx = True

        ents = av.get("pgx_entidades") or {}
        sec = _texto(o.get("numero")) or None
        for chave in ("genes", "star_alleles", "diplotypes", "rsids"):
            for item in (ents.get(chave) or []):
                if not isinstance(item, dict):
                    continue
                valor = valor_entidade(item)
                if not valor:
                    continue
                m = int(item.get("total_mentions") or item.get("mencoes") or 1)
                alvo = fora.setdefault(chave, {}).setdefault(valor, {})
                alvo[sec] = alvo.get(sec, 0) + m
    return fora, tem_pgx


def _entidades(bloco: dict, chave: str) -> list[dict]:
    v = bloco.get(chave)
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def _genes(celula) -> list[str]:
    """'COMT ; OPRM1' -> ['COMT', 'OPRM1']. Celula vazia -> []."""
    t = _texto(celula)
    if not t or t.lower() in ("none", "n/a"):
        return []
    return [g.strip().upper() for g in re.split(r"[;,]", t) if g.strip()]


def carregar_cobertura(con: sqlite3.Connection, xlsx: Path,
                       doc_id: dict[str, int]) -> tuple[int, int]:
    """Preenche 'guideline' e 'cobertura' a partir da folha do Excel.

    A cobertura nao pode vir dos JSON por documento. Esses so registam as
    guidelines cujos genes FORAM encontrados no rotulo; as ausentes — que sao
    precisamente as que interessam — nao aparecem la, porque nao ha entidade a
    que as prender. A folha 'Cobertura detalhe' tem as tres situacoes.

    Granularidade: uma linha por (documento, guideline, GENE), e nao por
    (documento, guideline). Uma guideline pode exigir dois genes e o rotulo
    nomear so um; guardar 'parcial' nos dois obrigaria depois a procurar
    dentro da coluna de texto para saber qual falta. Por gene, a pergunta
    "que farmacos tem guideline para o CYP2D6 e nao o nomeiam" e uma
    comparacao directa.
    """
    try:
        import openpyxl
    except ImportError:
        print("  openpyxl nao instalado: 'guideline' e 'cobertura' ficam vazias")
        return 0, 0
    if not xlsx.exists():
        print(f"  {xlsx.name} nao encontrado: 'guideline' e 'cobertura' vazias")
        return 0, 0

    wb = openpyxl.load_workbook(xlsx, read_only=True)
    if "Cobertura detalhe" not in wb.sheetnames:
        print("  folha 'Cobertura detalhe' ausente: tabelas vazias")
        return 0, 0

    linhas = wb["Cobertura detalhe"].iter_rows(values_only=True)
    next(linhas, None)  # cabecalho
    gid: dict[tuple[str, str, str], int] = {}
    n_g = n_c = 0
    for r in linhas:
        if not r or not r[0]:
            continue
        did = doc_id.get(_texto(r[0]))
        if did is None:          # documento fora do que foi carregado
            continue
        guia, fonte = _texto(r[2]), _texto(r[3])
        farmaco = _texto(r[1]).lower()
        esperados = _genes(r[5])
        mencionados = set(_genes(r[6]))
        em_falta = _genes(r[7])
        if not guia or not esperados:
            continue

        for gene in esperados:
            chave = (guia, farmaco, gene)
            if chave not in gid:
                cur = con.execute(
                    "INSERT INTO guideline (guideline_id, fonte, farmaco, gene)"
                    " VALUES (?,?,?,?)", (guia, fonte or "?", farmaco, gene))
                gid[chave] = cur.lastrowid
                n_g += 1
            estado = "coberta" if gene in mencionados else "ausente"
            try:
                con.execute(
                    "INSERT INTO cobertura (documento_id, guideline_id, estado,"
                    " genes_em_falta) VALUES (?,?,?,?)",
                    (did, gid[chave], estado,
                     " ; ".join(em_falta) or None))
                n_c += 1
            except sqlite3.IntegrityError:
                continue
    wb.close()
    return n_g, n_c


def construir(raiz: Path, destino: Path, xlsx: Path | None = None) -> int:
    if destino.exists():
        destino.unlink()
    con = sqlite3.connect(destino)
    con.executescript((AQUI / "esquema.sql").read_text(encoding="utf-8"))

    subst_id: dict[str, int] = {}
    doc_id: dict[str, int] = {}
    n_doc = n_ent = n_exc = n_sec = 0

    pastas = sorted(p for p in raiz.iterdir() if p.is_dir())
    for pasta in pastas:
        alvo = pasta / "pgx_outputs" / "Document_Unique_PGx.json"
        if not alvo.exists():
            continue
        try:
            j = json.loads(alvo.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  ignorado {pasta.name}: {e}")
            continue

        doc = j.get("documento") or {}
        ids = j.get("identificadores_substancia") or {}
        pipe = j.get("pipeline") or {}
        llm = pipe.get("llm") or {}

        nome_s = _texto(doc.get("substancia_ativa")).lower()
        sid = None
        if nome_s:
            if nome_s not in subst_id:
                cur = con.execute(
                    "INSERT INTO substancia (nome, cui, drugbank, mesh, aliases)"
                    " VALUES (?,?,?,?,?)",
                    (nome_s,
                     _texto(ids.get("mrconso_cui")) or None,
                     _texto(ids.get("drugbank_id")) or None,
                     _texto(ids.get("mesh_id")) or None,
                     " ; ".join(doc.get("aliases_substancia_ativa") or []) or None),
                )
                subst_id[nome_s] = cur.lastrowid
            sid = subst_id[nome_s]

        # O Extended traz identificadores externos e os IDs de guideline que
        # o Document_Unique nao tem. Quando existe, e dele que se lê.
        ext = {}
        p_ext = pasta / "pgx_outputs" / "Extended_PGx_Analysis.json"
        if p_ext.exists():
            try:
                ext = json.loads(p_ext.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                ext = {}
        freq = ext.get("frequencias_entidades") or {}

        ents = j.get("entidades") or {}
        # As entidades sao lidas das SECCOES, nao do Document_Unique.
        #
        # Os dois discordam. No 696704_Atorvastatina_Ezetimiba_Sandoz o
        # Document_Unique da 4 mencoes de SLCO1B1 e as seccoes somam 2. O
        # pgx_global_analysis, que produz o Excel e por essa via os numeros
        # da tese, conta pelas seccoes: ler dali faz a base bater certo com
        # o capitulo 4 em vez de ficar dois acima.
        #
        # Vantagem de desenho: assim ha uma contagem POR seccao, e nao um
        # total do documento repetido em cada uma.
        por_seccao, tem_pgx = ler_entidades_das_seccoes(pasta)

        tem_ent = any(_entidades(ents, k) for k in
                      ("genes", "star_alleles", "diplotypes", "rsids"))

        cur = con.execute(
            "INSERT INTO documento (ficheiro, medicamento, substancia_id,"
            " codigo_atc, grupo_codigo, grupo_nome, tem_pgx, tem_entidades,"
            " versao_pipeline, modelo, processado_em)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pasta.name,
             _texto(doc.get("nome_medicamento")) or None,
             sid,
             _texto(doc.get("codigo_atc")) or None,
             _texto(doc.get("grupo_farmacoterapeutico_codigo")) or None,
             _texto(doc.get("grupo_farmacoterapeutico")) or None,
             1 if tem_pgx else 0,
             1 if tem_ent else 0,
             _texto(pipe.get("pipeline_version")) or None,
             _texto(llm.get("model")) or None,
             _texto(pipe.get("processed_at")) or None),
        )
        did = cur.lastrowid
        doc_id[pasta.name] = did
        n_doc += 1

        for chave, tipo in (("genes", "gene"), ("star_alleles", "alelo"),
                            ("diplotypes", "diplotipo"), ("rsids", "rsid")):
            # indice do Extended pelo valor, para juntar os identificadores
            por_valor = {}
            for it in (freq.get(chave) or []):
                if isinstance(it, dict):
                    v = valor_entidade(it)
                    if v:
                        por_valor[v] = it

            # {valor: {seccao: mencoes}}. Duas grafias que colapsem no mesmo
            # valor canonico — HLA-B*1502 e HLA-B*15:02 — somam-se.
            juntos = por_seccao.get(chave, {})

            for valor, seccoes_m in juntos.items():
                mencoes = sum(seccoes_m.values())
                x = por_valor.get(valor, {})

                # UMA linha por documento e entidade. As mencoes sao as do
                # documento; escrever uma linha por seccao com este mesmo
                # numero fazia SUM(mencoes) contar a dobrar.
                try:
                    cur = con.execute(
                        "INSERT INTO entidade (documento_id, tipo, valor,"
                        " gene, mencoes, pharmgkb_id, ncbi_gene_id,"
                        " hgnc_id, guideline_ids)"
                        " VALUES (?,?,?,?,?,?,?,?,?)",
                        (did, tipo, valor,
                         valor.upper() if tipo == "gene" else gene_de(valor),
                         int(mencoes),
                         _texto(x.get("pharmgkb_id")) or None,
                         _texto(x.get("ncbi_gene_id")) or None,
                         _texto(x.get("hgnc_id")) or None,
                         " ; ".join(x.get("guideline_ids") or []) or None),
                    )
                    eid = cur.lastrowid
                    n_ent += 1
                except sqlite3.IntegrityError:
                    # a mesma entidade ja veio por outro caminho; fica a
                    # primeira e as seccoes acumulam-se na mesma linha
                    linha = con.execute(
                        "SELECT id FROM entidade WHERE documento_id=? AND"
                        " tipo=? AND valor=?", (did, tipo, valor)).fetchone()
                    if not linha:
                        continue
                    eid = linha[0]

                # Agora ha contagem por seccao, porque foi assim que se leu.
                # SUM(mencoes) sobre esta tabela reproduz entidade.mencoes.
                for sec, m in seccoes_m.items():
                    if not sec:
                        continue
                    try:
                        con.execute(
                            "INSERT INTO entidade_seccao (entidade_id, seccao,"
                            " mencoes) VALUES (?,?,?)", (eid, sec, int(m)))
                        n_sec += 1
                    except sqlite3.IntegrityError:
                        continue

        # passagens: o trecho PGx que o modelo extraiu de cada seccao
        for sec_json in sorted(pasta.glob("*.json")):
            try:
                s = json.loads(sec_json.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            av = s.get("avaliacao_farmacogenomica")
            if not isinstance(av, dict):
                continue
            if not str(av.get("contem_farmacogenomica", "")).lower().startswith(
                    ("sim", "true")):
                continue
            texto = _texto(av.get("informacao_farmacogenomica"))
            if not texto or texto.lower() in ("não", "nao", "n/a"):
                continue
            nome_sec = _texto(s.get("numero") or s.get("seccao")
                              or sec_json.stem)
            try:
                con.execute(
                    "INSERT INTO passagem (documento_id, seccao, texto)"
                    " VALUES (?,?,?)", (did, nome_sec, texto))
                n_exc += 1
            except sqlite3.IntegrityError:
                pass

    n_g, n_c = carregar_cobertura(
        con, xlsx or (raiz / "Analise_Global_PGx.xlsx"), doc_id)

    con.commit()
    print(f"documentos : {n_doc}")
    print(f"substancias: {len(subst_id)}")
    print(f"entidades  : {n_ent}")
    print(f"ent.×secção: {n_sec}")
    print(f"passagens  : {n_exc}")
    print(f"guidelines : {n_g}")
    print(f"cobertura  : {n_c}")
    con.close()
    return 0


def verificar(caminho: Path) -> int:
    con = sqlite3.connect(caminho)
    print(f"{caminho}  ({caminho.stat().st_size/1_048_576:.1f} MB)\n")
    vazias = []
    for t in ("substancia", "documento", "entidade", "entidade_seccao",
              "passagem", "guideline", "cobertura"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"   {t:16} {n:7}")
        if n == 0:
            vazias.append(t)
    if vazias:
        print(f"\n   AVISO: tabelas vazias -> {', '.join(vazias)}")
        print("   O esquema declara-as; se ficarem a zero a base promete o que")
        print("   nao tem. Ve o aviso que a construcao imprimiu.")

    # So faz sentido comparar com a tese numa construcao do corpus inteiro.
    n_docs = con.execute("SELECT COUNT(*) FROM documento").fetchone()[0]
    total = con.execute("SELECT SUM(mencoes) FROM entidade").fetchone()[0]
    print(f"\n   menções de entidades: {total}")
    pgx = con.execute("SELECT COUNT(*) FROM documento WHERE tem_pgx=1").fetchone()[0]
    ent = con.execute("SELECT COUNT(*) FROM documento WHERE tem_entidades=1").fetchone()[0]
    if n_docs == 5565:
        print("   o capítulo 4 reporta 5885", end="")
        print("  <-- BATE" if total == 5885 else
              "  <-- NÃO BATE: ver valor_entidade() e ler_entidades_das_seccoes()")
        # Sao duas coisas diferentes e ja saíram iguais por engano uma vez.
        print(f"   documentos com conteúdo PGx : {pgx}  (tese: 3142)"
              + ("  ok" if pgx == 3142 else "  <-- NÃO BATE"))
        print(f"   documentos com entidade     : {ent}  (tese: 1206)"
              + ("  ok" if ent == 1206 else "  <-- NÃO BATE"))
    else:
        print(f"   ({n_docs} documentos, não é o corpus inteiro: não comparo"
              " com a tese)")

    # As duas tabelas tem de ser consistentes entre si, sempre.
    mau = con.execute(
        "SELECT COUNT(*) FROM entidade e WHERE (SELECT SUM(mencoes) FROM"
        " entidade_seccao WHERE entidade_id=e.id) IS NOT NULL AND"
        " (SELECT SUM(mencoes) FROM entidade_seccao WHERE entidade_id=e.id)"
        " <> e.mencoes").fetchone()[0]
    print(f"   entidades cujas secções não somam o total: {mau}"
          + ("  (correcto)" if mau == 0 else "  <-- ERRO"))

    print("\n   genes mais frequentes:")
    for g, n in con.execute(
        "SELECT gene, SUM(mencoes) m FROM entidade WHERE gene IS NOT NULL"
        " GROUP BY gene ORDER BY m DESC LIMIT 5"
    ):
        print(f"      {g:12} {n}")

    print("\n   genes mais exigidos por guideline e mais vezes ausentes:")
    for g, esp, falta in con.execute(
        "SELECT g.gene, COUNT(*),"
        "       SUM(CASE WHEN c.estado='ausente' THEN 1 ELSE 0 END)"
        " FROM cobertura c JOIN guideline g ON g.id = c.guideline_id"
        " GROUP BY g.gene ORDER BY 2 DESC LIMIT 5"
    ):
        print(f"      {g:12} exigido em {esp:5}, ausente em {falta:5}"
              f"  ({falta/esp*100:.0f} %)")
    con.close()
    return 0


if __name__ == "__main__":
    if "--verificar" in sys.argv:
        i = sys.argv.index("--verificar")
        raise SystemExit(verificar(Path(sys.argv[i + 1])))
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    folha = None
    if "--excel" in sys.argv:
        folha = Path(sys.argv[sys.argv.index("--excel") + 1])
    raise SystemExit(construir(Path(sys.argv[1]), Path(sys.argv[2]), folha))
