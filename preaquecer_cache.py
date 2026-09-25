#!/usr/bin/env python3
"""Pré-enche a cache de resolução externa, usando o índice MRCONSO já construído.

Porquê
------
O portão do `resolve()` exige que a entrada em cache tenha `english_terms`.
Nenhuma das 501 entradas antigas o tem, porque foram criadas antes da expansão
de sinónimos. Resultado: a cache é rejeitada a 100% e cada documento varre o
MRCONSO duas vezes. Com ~1 200 substâncias no corpus nacional isso são dias.

Este script resolve todas as substâncias uma vez, à frente, e grava entradas
completas. A partir daí o portão deixa-as passar e a corrida fica só com a
espera do modelo.

O que é real e o que é substituído
----------------------------------
O ClinPGx e o MeSH correm pelo código do pipeline, sem atalhos. A ÚNICA coisa
substituída é o `_resolve_mrconso_one`, que em vez de varrer 2,3 GB consulta o
índice construído pelo `construir_indice_mrconso.py` — que foi validado contra
a cache existente e contra as saídas do pipeline, com resultados idênticos.
Substâncias fora do índice caem no código original.

Uso
---
    python3 preaquecer_cache.py substancias.txt indice_mrconso.json
    python3 preaquecer_cache.py substancias.txt indice_mrconso.json 0 4

Os dois últimos argumentos são o número deste processo e o total, para correr
em paralelo. A escrita na cache é feita com lock, portanto os processos não se
apagam uns aos outros.
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


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    lista = Path(sys.argv[1])
    indice_path = Path(sys.argv[2])
    parte = int(sys.argv[3]) if len(sys.argv) > 4 else 0
    total = int(sys.argv[4]) if len(sys.argv) > 4 else 1

    substancias = [
        l.strip() for l in lista.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    indice = json.loads(indice_path.read_text(encoding="utf-8"))
    print(f"substâncias na lista : {len(substancias)}")
    print(f"entradas no índice   : {len(indice)}")

    minhas = substancias[parte::total]
    print(f"este processo ({parte+1}/{total}) : {len(minhas)}")

    original = ActiveSubstanceExternalResolver._resolve_mrconso_one

    def pelo_indice(self, query: str) -> dict:
        achado = indice.get(query)
        if achado is not None:
            # cópia, para o chamador não mexer no índice partilhado
            return json.loads(json.dumps(achado))
        return original(self, query)

    ActiveSubstanceExternalResolver._resolve_mrconso_one = pelo_indice

    data_dir = BASE / "RCMprocessor" / "data"
    resolver = ActiveSubstanceExternalResolver(data_dir=data_dir)

    t0 = time.time()
    feitas = saltadas = erros = 0
    for i, s in enumerate(minhas, 1):
        try:
            antes = len(resolver.cache)
            resolver.resolve(active_substance=s, aliases=[])
            if len(resolver.cache) == antes:
                saltadas += 1
            else:
                feitas += 1
        except Exception as e:  # nunca parar a meio por causa de uma substância
            erros += 1
            print(f"  erro em {s!r}: {e}")

        if i % 25 == 0 or i == len(minhas):
            decorrido = time.time() - t0
            resta = decorrido / i * (len(minhas) - i)
            print(f"  [{i}/{len(minhas)}] {decorrido/60:.1f} min decorridos, "
                  f"~{resta/60:.1f} min a faltar   (novas {feitas}, já lá estavam {saltadas}, erros {erros})")

    print()
    print(f"novas entradas : {feitas}")
    print(f"já existentes  : {saltadas}")
    print(f"erros          : {erros}")
    print(f"tempo          : {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
