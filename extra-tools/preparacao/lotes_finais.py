#!/usr/bin/env python3
"""Reparte os documentos que ainda faltam por N lotes novos.

Para a cauda da corrida: quando sobram poucos documentos concentrados num
lote, o ultimo processo fica sozinho a arrasta-los em serie. Isto apanha o
que falta e reparte por varios processos.

PARAR O PROCESSO QUE AINDA CORRE ANTES DE USAR ISTO. Se ficar vivo, dois
processos podem pegar no mesmo documento ao mesmo tempo.

Nao mexe nos lote_nac_*.txt. Escreve lote_fim_00.txt, lote_fim_01.txt, ...

Um documento conta como feito se tiver Document_Unique_PGx.json ou
NAO_UTILIZAVEL.json. E o mesmo criterio do progresso.py.

Uso:
    python lotes_finais.py 6
    python lotes_finais.py 6 out_nacional RCMs_a_processar
"""
import glob
import os
import sys


def main() -> int:
    n_proc = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    saida = sys.argv[2] if len(sys.argv) > 2 else "out_nacional"
    pasta = sys.argv[3] if len(sys.argv) > 3 else "RCMs_a_processar"

    for f in glob.glob("lote_fim_*.txt"):
        os.remove(f)

    base = os.path.join(os.getcwd(), pasta)
    todos = sorted(
        f for f in os.listdir(base)
        if f.lower().endswith(".pdf") and not f.startswith("._")
    )

    faltam = []
    for f in todos:
        stem = f[:-4]
        d = os.path.join(saida, stem)
        feito = (
            os.path.exists(os.path.join(d, "pgx_outputs",
                                        "Document_Unique_PGx.json"))
            or os.path.exists(os.path.join(d, "NAO_UTILIZAVEL.json"))
        )
        if not feito:
            faltam.append(os.path.join(base, f))

    print(f"PDFs no total : {len(todos)}")
    print(f"ja feitos     : {len(todos) - len(faltam)}")
    print(f"faltam        : {len(faltam)}")

    if not faltam:
        print("\nNada a fazer.")
        return 0

    n_proc = min(n_proc, len(faltam))
    lotes = [faltam[i::n_proc] for i in range(n_proc)]

    print()
    for i, lote in enumerate(lotes):
        nome = f"lote_fim_{i:02d}.txt"
        with open(nome, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lote) + "\n")
        print(f"  {nome}  {len(lote)} documentos")

    print("\nLancar (uma janela por lote):\n")
    for i in range(n_proc):
        print(f"  python -m RCMprocessor.batch_processor RCMs_a_processar "
              f"{saida} --model glm-5.3-flash --markdown-dir markdown "
              f"--file-list lote_fim_{i:02d}.txt --retomar "
              f"*> log_fim_{i:02d}.txt")

    print("\nOu todos de uma vez, no PowerShell:\n")
    print(f"  0..{n_proc - 1} | ForEach-Object {{ "
          f"Start-Process powershell -ArgumentList "
          f"'-NoExit','-Command',"
          f"(\"python -m RCMprocessor.batch_processor RCMs_a_processar "
          f"{saida} --model glm-5.3-flash --markdown-dir markdown "
          f"--file-list lote_fim_{{0:d2}}.txt --retomar\" -f $_) }}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
