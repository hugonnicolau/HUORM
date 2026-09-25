"""
Propagação dos resultados dos representantes para os duplicados exactos.

O `preflight` reduz o que vai ao LLM colapsando documentos cujo texto é
idêntico dentro do mesmo código ATC. Corrê-los todos daria, por construção, o
mesmo resultado — o input é o mesmo.

Mas a análise global percorre as pastas de output. Sem este passo, contaria
5 631 documentos em vez de 7 832, e todas as percentagens ficariam sobre o
denominador errado. A poupança de compute não pode custar a correcção dos
números.

O que se faz: para cada duplicado, cria-se a pasta de output com os ficheiros
do representante, marcados com a proveniência. O bloco `pipeline` recebe

    "resultado_propagado_de": "<ficheiro do representante>"

para que nunca se confunda um documento processado com um documento herdado, e
para que a contagem de chamadas ao modelo continue auditável.

    python -m RCMprocessor.propagate_duplicates <out> --mapa preflight/mapa_duplicados.csv
    python -m RCMprocessor.propagate_duplicates <out> --mapa ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

MARCA = "resultado_propagado_de"


def carregar_mapa(caminho: Path) -> list[dict]:
    if not caminho.exists():
        sys.exit(f"Mapa não encontrado: {caminho}")
    return list(csv.DictReader(caminho.open(encoding="utf-8")))


def marcar_proveniencia(destino: Path, origem_nome: str) -> None:
    """Anota, em cada JSON copiado, que o resultado foi herdado."""
    for json_path in list(destino.rglob("*.json")):
        try:
            dados = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(dados, dict):
            continue

        bloco = dados.get("pipeline")
        if isinstance(bloco, dict):
            bloco[MARCA] = origem_nome
        else:
            dados[MARCA] = origem_nome

        json_path.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", help="pasta raiz dos outputs do batch")
    parser.add_argument("--mapa", required=True,
                        help="mapa_duplicados.csv produzido pelo preflight")
    parser.add_argument("--dry-run", action="store_true",
                        help="mostrar o que seria feito, sem copiar")
    parser.add_argument("--forcar", action="store_true",
                        help="substituir pastas de duplicados já existentes")
    args = parser.parse_args()

    raiz = Path(args.output_root).resolve()
    if not raiz.is_dir():
        sys.exit(f"Pasta de outputs não encontrada: {raiz}")

    mapa = carregar_mapa(Path(args.mapa))
    print(f"  duplicados no mapa : {len(mapa)}")

    propagados = saltados = 0
    sem_representante: list[str] = []
    ja_existiam: list[str] = []

    for linha in mapa:
        dup_stem = Path(linha["ficheiro"]).stem
        rep_stem = Path(linha["representante"]).stem

        origem = raiz / rep_stem
        destino = raiz / dup_stem

        # O representante tem de ter sido processado com sucesso.
        if not (origem / "pgx_outputs" / "Document_Unique_PGx.json").exists():
            sem_representante.append(f"{dup_stem} <- {rep_stem}")
            continue

        if destino.exists():
            if not args.forcar:
                ja_existiam.append(dup_stem)
                saltados += 1
                continue
            if not args.dry_run:
                shutil.rmtree(destino)

        if args.dry_run:
            propagados += 1
            continue

        shutil.copytree(origem, destino)
        marcar_proveniencia(destino, linha["representante"])
        propagados += 1

    print("\n" + "=" * 62)
    print("PROPAGAÇÃO" + ("  (simulação)" if args.dry_run else ""))
    print("=" * 62)
    print(f"  propagados                    : {propagados}")
    if saltados:
        print(f"  já existiam, saltados         : {saltados}"
              f"   (usa --forcar para substituir)")
    if sem_representante:
        print(f"  representante não processado  : {len(sem_representante)}")
        for x in sem_representante[:8]:
            print(f"      {x}")
        if len(sem_representante) > 8:
            print(f"      … e mais {len(sem_representante) - 8}")
        print("  → corre primeiro o batch sobre processar.txt, ou usa --retomar")

    if not args.dry_run:
        total = len([p for p in raiz.iterdir() if p.is_dir()])
        print(f"\n  pastas de output agora        : {total}")
        print("  A seguir: python -m RCMprocessor.pgx_global_analysis "
              f"{args.output_root}")
    else:
        print("\n  Nada foi alterado. Retira --dry-run para aplicar.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
