#!/usr/bin/env python3
"""Lista as substâncias activas do corpus, para pré-resolver contra o MRCONSO.

As substâncias vêm do índice do INFOMED (`medicamentos.csv`), que é o campo
estruturado do registo nacional. Não são exactamente as que o modelo extrai da
secção 2 de cada RCM — essas só se conhecem em tempo de execução — mas na
esmagadora maioria dos casos coincidem depois de normalizadas. Onde não
coincidirem, esse documento paga o varrimento como antes.

Acrescenta também as substâncias que já estão na cache, para que as entradas
antigas (a que falta o campo `english_terms`) sejam refeitas de uma vez.

Uso, a partir de ~/Desktop/FINAL:
    python3 listar_substancias.py RCMs_a_processar dados/medicamentos.csv
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent


def chave(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def main() -> int:
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else "RCMs_a_processar")
    csv_path = Path(sys.argv[2] if len(sys.argv) > 2 else "dados/medicamentos.csv")
    saida = Path(sys.argv[3] if len(sys.argv) > 3 else "substancias.txt")

    idx = {r["med_id"]: r for r in csv.DictReader(csv_path.open(encoding="utf-8"))}

    vistos: dict[str, str] = {}

    def juntar(valor: str) -> None:
        for parte in re.split(r"\s*\+\s*|\s*,\s*|\s+e\s+", valor or ""):
            parte = parte.strip()
            if len(parte) < 3:
                continue
            k = chave(parte)
            if k and k not in vistos:
                vistos[k] = parte

    n_pdf = 0
    for f in sorted(pasta.iterdir()):
        if f.suffix.lower() != ".pdf":
            continue
        n_pdf += 1
        med_id = f.stem.split("_", 1)[0]
        juntar((idx.get(med_id) or {}).get("active_substance", ""))

    cache_path = BASE / "RCMprocessor" / "data" / "cache" / "active_substance_external_cache.json"
    n_cache = 0
    if cache_path.exists():
        try:
            c = json.loads(cache_path.read_text(encoding="utf-8"))
            for k in c:
                for t in k.split("|"):
                    juntar(t)
            n_cache = len(c)
        except Exception:
            pass

    saida.write_text("\n".join(sorted(vistos.values())) + "\n", encoding="utf-8")
    print(f"PDFs lidos            : {n_pdf}")
    print(f"entradas da cache     : {n_cache}")
    print(f"substâncias distintas : {len(vistos)}")
    print(f"escrito em            : {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
