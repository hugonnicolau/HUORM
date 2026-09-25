#!/usr/bin/env python3
"""Reparte os PDFs por N lotes, um ficheiro de lista por lote.

Ficheiro próprio, e não um bloco dentro do PowerShell, porque o here-string
do PowerShell escreve um BOM (U+FEFF) à cabeça do texto e o Python recusa-o
com `SyntaxError: invalid non-printable character`. Quando isso acontece o
script continua na mesma e os processos arrancam com os lotes antigos — foi o
que aconteceu a 21-09, com lotes feitos para 8 processos a serem usados por 3.

Uso:
    python fazer_lotes.py 3
"""
import glob
import math
import os
import sys


def main() -> int:
    n_proc = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pasta = sys.argv[2] if len(sys.argv) > 2 else "RCMs_a_processar"

    for f in glob.glob("lote_nac_*.txt"):
        os.remove(f)

    base = os.path.join(os.getcwd(), pasta)
    fs = sorted(
        os.path.join(base, f)
        for f in os.listdir(base)
        if f.lower().endswith(".pdf") and not f.startswith("._")
    )
    if not fs:
        print(f"Nao encontrei PDFs em {base}")
        return 1

    # Repartição alternada: os documentos pesados ficam espalhados pelos lotes
    # em vez de se concentrarem num só, que foi o que fez um lote demorar 53
    # minutos sozinho enquanto os outros sete já tinham acabado.
    total = 0
    for i in range(n_proc):
        parte = fs[i::n_proc]
        total += len(parte)
        with open("lote_nac_%02d.txt" % i, "w", encoding="utf-8") as fh:
            fh.write("\n".join(parte) + "\n")
        print("lote_nac_%02d.txt  %d documentos" % (i, len(parte)))

    print("TOTAL:", total)
    if total != len(fs):
        print("AVISO: a soma dos lotes nao bate com o numero de PDFs")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
