#!/usr/bin/env python3
"""Reparte os 17 do referencia por N lotes, para a segunda execucao.

O correr_referencia.sh original fez isto em bash, com caminhos do Mac. Os
glote_*.txt que estao na pasta apontam para /Users/hugo/... e nao servem
aqui. Isto regenera-os com os caminhos desta maquina.

Percorre subpastas (TestSet/1oDS+ e TestSet/2oDT-) e lida com o espaco no
nome do "Acido Folico.pdf", que foi a razao de o original nao usar globs.

Nao mexe nos glote_*.txt antigos. Escreve grep_00.txt, grep_01.txt, ...

Uso:
    python lotes_referencia.py 6
"""
import glob
import os
import sys


def main() -> int:
    n_proc = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    pasta = sys.argv[2] if len(sys.argv) > 2 else "TestSet"

    for f in glob.glob("grep_*.txt"):
        os.remove(f)

    base = os.path.join(os.getcwd(), pasta)
    fs = sorted(
        os.path.join(raiz, nome)
        for raiz, _, nomes in os.walk(base)
        for nome in nomes
        if nome.lower().endswith(".pdf") and not nome.startswith("._")
    )

    print(f"documentos encontrados: {len(fs)}")
    if len(fs) != 17:
        print(f"  ATENCAO: esperavam-se 17. Confirma a pasta {pasta}.")
    if not fs:
        return 1

    n_proc = min(n_proc, len(fs))
    for i in range(n_proc):
        parte = fs[i::n_proc]
        with open(f"grep_{i:02d}.txt", "w", encoding="utf-8") as fh:
            fh.write("\n".join(parte) + "\n")
        print(f"  grep_{i:02d}.txt  {len(parte)} documentos")

    print("\nLancar os", n_proc, "de uma vez:\n")
    print(f"  0..{n_proc - 1} | ForEach-Object {{ Start-Process powershell "
          f"-ArgumentList '-NoExit','-Command',"
          f"(\"python -m RCMprocessor.batch_processor TestSet "
          f"out_referencia_rep2 --model glm-5.3-flash "
          f"--markdown-dir markdown_referencia --file-list grep_{{0:d2}}.txt\" "
          f"-f $_) }}")

    print("\nQuando acabarem:\n")
    print("  python medir_concordancia.py out_referencia_final out_referencia_rep2")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
