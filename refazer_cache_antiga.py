#!/usr/bin/env python3
"""Refaz as entradas antigas da cache sob a MESMA chave.

Porquê
------
O `preaquecer_cache.py` resolve substâncias a partir dos nomes do índice do
INFOMED e grava-as com a chave que essas consultas produzem. As entradas
antigas têm outra chave, porque foram criadas pelo pipeline a partir do nome
extraído pelo modelo mais os seus aliases — por exemplo `warfarin | varfarina`
em vez de `Varfarina`.

Essas chaves antigas são precisamente as que o pipeline vai voltar a gerar em
execução. Se ficarem por refazer, o portão rejeita-as e o documento paga o
varrimento completo do MRCONSO, que é o que se está a tentar evitar.

Este script percorre as entradas que falham o portão, recupera a lista de
consultas que cada uma guarda, e manda o `resolve()` refazê-la — com o MRCONSO
servido pelo índice. A chave sai igual porque as consultas são as mesmas.

Uso, a partir de ~/Desktop/FINAL:
    python3 refazer_cache_antiga.py indice_mrconso.json
    python3 refazer_cache_antiga.py indice_mrconso.json 0 4
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from RCMprocessor.active_substance_external_resolver import (  # noqa: E402
    ActiveSubstanceExternalResolver,
)

CACHE = BASE / "RCMprocessor" / "data" / "cache" / "active_substance_external_cache.json"


def passa_no_portao(entrada: dict) -> bool:
    refs = (entrada or {}).get("references") or {}
    if "mrconso" not in refs:
        return False
    t = json.dumps(refs["mrconso"], ensure_ascii=False).lower()
    return ("mrconso_path" not in t
            and "chebi_id" not in t
            and "drugbank_id" in t
            and "english_terms" in t)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    indice = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    parte = int(sys.argv[2]) if len(sys.argv) > 3 else 0
    total = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    obsoletas = [(k, v) for k, v in cache.items() if not passa_no_portao(v)]
    print(f"entradas na cache : {len(cache)}")
    print(f"a refazer         : {len(obsoletas)}")

    minhas = obsoletas[parte::total]
    print(f"este processo ({parte+1}/{total}) : {len(minhas)}")

    original = ActiveSubstanceExternalResolver._resolve_mrconso_one

    def pelo_indice(self, query: str) -> dict:
        achado = indice.get(query)
        if achado is None:
            # o índice foi construído com nomes do INFOMED; as consultas antigas
            # podem ter outra capitalização
            for k, v in indice.items():
                if k.lower() == query.lower():
                    achado = v
                    break
        if achado is not None:
            copia = json.loads(json.dumps(achado))
            copia["query"] = query
            for m in copia.get("matches", []):
                m["query"] = query
            return copia
        return original(self, query)

    ActiveSubstanceExternalResolver._resolve_mrconso_one = pelo_indice

    resolver = ActiveSubstanceExternalResolver(data_dir=BASE / "RCMprocessor" / "data")

    t0 = time.time()
    feitas = erros = sem_queries = 0
    for i, (chave, entrada) in enumerate(minhas, 1):
        queries = (entrada or {}).get("queries") or []
        if not queries:
            sem_queries += 1
            continue
        try:
            # a chave é reconstruída a partir das mesmas consultas
            resolver.cache.pop(chave, None)
            resolver.resolve(active_substance=queries[0], aliases=queries[1:])
            feitas += 1
        except Exception as e:
            erros += 1
            print(f"  erro em {chave!r}: {e}")

        if i % 25 == 0 or i == len(minhas):
            d = time.time() - t0
            print(f"  [{i}/{len(minhas)}] {d/60:.1f} min, "
                  f"~{d/i*(len(minhas)-i)/60:.1f} min a faltar  "
                  f"(refeitas {feitas}, sem consultas {sem_queries}, erros {erros})")

    print()
    print(f"refeitas        : {feitas}")
    print(f"sem consultas   : {sem_queries}")
    print(f"erros           : {erros}")
    print(f"tempo           : {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
