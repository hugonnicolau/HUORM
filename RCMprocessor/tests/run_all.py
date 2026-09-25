"""
Corre toda a suite de testes do RCMprocessor.

Nenhum teste precisa de rede, de Ollama, de docling nem dos ficheiros de dados
completos — todos correm em segundos. Correr isto antes de iniciar um batch é
barato e evita descobrir um problema ao fim de horas de processamento.

    python RCMprocessor/tests/run_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SUITES = [
    ("test_pipeline_fixes.py", "Correções de comportamento do avaliador"),
    ("test_text_blocks.py", "Segmentação de blocos enviados ao modelo"),
    ("test_markdown_processor.py", "Extração do grupo farmacoterapêutico"),
    ("test_substance_utils.py", "Normalização e matching de substâncias"),
    ("test_clinical_variants_lookup.py", "Cruzamento com clinicalVariants.tsv"),
    ("test_guideline_coverage.py", "Cobertura de guidelines ClinPGx"),
    ("test_table_evaluation.py", "Avaliação de tabelas e origem das entidades"),
    ("test_section_fallback.py", "Secções por título e símbolos Symbol"),
    ("test_ambiguous_symbols.py", "Símbolos de gene ambíguos em português"),
    ("test_sheet_names.py", "Nomes das folhas do Excel"),
    ("test_unusable_pdf_detection.py", "Digitalizações e texto corrompido"),
    ("test_substance_resolution.py", "Resolução da substância (UMLS/ClinPGx)"),
    ("test_duplicate_propagation.py", "Propagação de duplicados exactos"),
    ("test_two_phase_and_timeout.py", "Duas fases e timeout nas chamadas"),
]


def main() -> int:
    total = passed = 0
    failed_suites = []

    for filename, description in SUITES:
        path = HERE / filename
        if not path.exists():
            print(f"?? {filename} não encontrado")
            failed_suites.append(filename)
            continue

        result = subprocess.run(
            [sys.executable, str(path)], capture_output=True, text=True
        )
        output = result.stdout.strip().split("\n")
        summary = output[-1] if output else "sem output"

        n_passed = n_total = 0
        if "/" in summary:
            try:
                left, right = summary.split("passaram")[0].strip().split("/")
                n_passed, n_total = int(left), int(right)
            except ValueError:
                pass

        total += n_total
        passed += n_passed

        mark = "OK " if result.returncode == 0 else "!! "
        print(f"  {mark}{description:<46} {summary}")

        if result.returncode != 0:
            failed_suites.append(filename)
            for line in output:
                if line.strip().startswith(("FAIL", "ERROR")):
                    print(f"        {line.strip()}")

    print()
    print(f"  TOTAL: {passed}/{total} testes")

    if failed_suites:
        print(f"  Suites com falhas: {', '.join(failed_suites)}")
        return 1

    print("  Tudo verde — seguro para iniciar o batch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
