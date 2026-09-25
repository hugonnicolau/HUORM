#!/usr/bin/env python3
"""Exporta o huorm.db para SQL que o D1 da Cloudflare aceita.

O D1 e SQLite, mas nao aceita o dump do sqlite3 tal e qual: rejeita
PRAGMA, transaccoes explicitas, e as tabelas internas sqlite_*. Este script
produz um ficheiro limpo, com o esquema e os dados, pronto para:

    npx wrangler d1 execute huorm --remote --file=./huorm_d1.sql

Uso, a partir de FINALV2:
    python api/exportar_para_d1.py basedados/huorm.db api/huorm_d1.sql

Os INSERT saem agrupados em lotes, porque uma linha por instrucao faz um
ficheiro com centenas de milhares de comandos e a importacao demora.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ordem obrigatoria: as chaves estrangeiras exigem que o alvo ja exista.
# A entidade_seccao vem depois da entidade, que e quem ela referencia.
TABELAS = ["substancia", "documento", "entidade", "entidade_seccao",
           "passagem", "guideline", "cobertura"]

# O corte e' por TAMANHO, nao por numero de linhas.
#
# Com lotes de 200 linhas o D1 respondia SQLITE_TOOBIG: ha um limite por
# instrucao, e uma passagem pode ter 10 KB de texto, pelo que 200 delas
# passavam-no com folga. 25 000 caracteres ficam bem abaixo do limite e
# continuam a ser poucas instrucoes.
MAX_CHARS = 25_000
MAX_LINHAS = 200


def escapar(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def exportar(origem: Path, destino: Path) -> int:
    con = sqlite3.connect(origem)
    con.row_factory = sqlite3.Row
    linhas_totais = 0

    with open(destino, "w", encoding="utf-8", newline="\n") as out:
        out.write("-- HUORM: base farmacogenomica dos RCM portugueses.\n")
        out.write(f"-- Gerado de {origem.name}. Nao editar a mao.\n\n")

        # Apagar antes de criar, para o ficheiro poder ser reimportado.
        #
        # O sqlite_master so guarda os CREATE, por isso os DROP tem de ser
        # escritos aqui. Sem eles a segunda importacao morre em "table
        # substancia already exists". Ordem inversa a da criacao: quem tem
        # chave estrangeira cai primeiro.
        out.write("DROP VIEW  IF EXISTS entidade_completa;\n")
        for t in reversed(TABELAS):
            out.write(f"DROP TABLE IF EXISTS {t};\n")
        out.write("\n")

        # esquema: tabelas e indices, sem as internas do SQLite
        for (sql,) in con.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
            " ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"
        ):
            out.write(sql.strip().rstrip(";") + ";\n")
        out.write("\n")

        for t in TABELAS:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            if not cols:
                continue
            lista = ", ".join(cols)
            valores, tamanho, n, lotes = [], 0, 0, 0

            def despejar():
                nonlocal valores, tamanho, lotes
                if not valores:
                    return
                out.write(f"INSERT INTO {t} ({lista}) VALUES\n"
                          + ",\n".join(valores) + ";\n")
                valores, tamanho = [], 0
                lotes += 1

            for r in con.execute(f"SELECT {lista} FROM {t}"):
                linha = "(" + ", ".join(escapar(r[c]) for c in cols) + ")"
                # despeja ANTES de acrescentar, senao o lote ja vai grande
                if valores and (tamanho + len(linha) > MAX_CHARS
                                or len(valores) >= MAX_LINHAS):
                    despejar()
                valores.append(linha)
                tamanho += len(linha) + 2
                n += 1
            despejar()
            out.write("\n")
            print(f"   {t:16} {n:7} linhas em {lotes} instruções")
            linhas_totais += n

    con.close()
    mb = destino.stat().st_size / 1_048_576
    print(f"\n{destino}  ({mb:.1f} MB, {linhas_totais} linhas)")
    if mb > 100:
        print("AVISO: acima de 100 MB o wrangler pode recusar a importacao.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(exportar(Path(sys.argv[1]), Path(sys.argv[2])))
