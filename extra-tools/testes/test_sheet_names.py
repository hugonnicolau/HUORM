"""
Validação dos nomes das folhas do Excel.

O Excel proíbe os caracteres `: \\ / ? * [ ]` em títulos de folha, limita-os a
31 caracteres, e não aceita apóstrofos no início ou no fim. O openpyxl só se
queixa em tempo de execução, no momento de criar a folha — ou seja, depois de
toda a análise ter corrido.

A folha "Origem: texto vs tabelas" fez o `pgx_global_analysis` falhar no fim de
uma execução completa, por causa dos dois pontos. Num corpus de milhares de
documentos, descobrir isto só no fim é caro.

Este teste percorre o código à procura de todos os nomes de folha — literais
passados a `create_sheet`, atribuições a `ws.title`, e os nomes passados ao
`_write_frequency_sheet` — e valida-os sem precisar de correr nada.

    python extra-tools/testes/test_sheet_names.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "RCMprocessor" / "pgx_global_analysis.py"

CARACTERES_PROIBIDOS = set(":\\/?*[]")
MAX_COMPRIMENTO = 31


def nomes_de_folha() -> list[str]:
    """Todos os nomes de folha declarados no módulo de análise."""
    src = SOURCE.read_text(encoding="utf-8")
    nomes: list[str] = []

    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue

        # wb.create_sheet("Nome")
        if node.func.attr == "create_sheet" and node.args:
            if isinstance(node.args[0], ast.Constant):
                nomes.append(node.args[0].value)

        # self._write_frequency_sheet(wb, "Nome", ...)
        if node.func.attr == "_write_frequency_sheet" and len(node.args) >= 2:
            if isinstance(node.args[1], ast.Constant):
                nomes.append(node.args[1].value)

    # ws.title = "Nome"
    nomes.extend(re.findall(r'ws\.title\s*=\s*"([^"]+)"', src))

    return nomes


NOMES = nomes_de_folha()


# ==========================================================================
def test_encontrou_nomes():
    """Se a extração deixar de encontrar nomes, o teste passa a ser inútil."""
    assert len(NOMES) >= 15, f"apenas {len(NOMES)} nomes encontrados"


def test_sem_caracteres_proibidos():
    for nome in NOMES:
        maus = sorted(set(nome) & CARACTERES_PROIBIDOS)
        assert not maus, f"{nome!r} contém {maus}"


def test_comprimento_dentro_do_limite():
    for nome in NOMES:
        assert len(nome) <= MAX_COMPRIMENTO, f"{nome!r} tem {len(nome)} caracteres"


def test_sem_apostrofos_nas_extremidades():
    for nome in NOMES:
        assert not nome.startswith("'"), nome
        assert not nome.endswith("'"), nome


def test_nomes_nao_vazios():
    for nome in NOMES:
        assert nome.strip(), "nome de folha vazio"


def test_nomes_unicos():
    """Duas folhas com o mesmo nome fazem o openpyxl renomear em silêncio."""
    duplicados = {n for n in NOMES if NOMES.count(n) > 1}
    assert not duplicados, f"nomes repetidos: {sorted(duplicados)}"


def test_o_caso_que_falhou_esta_coberto():
    """Regressão explícita: a folha da origem das entidades já não tem ':'."""
    origem = [n for n in NOMES if "rigem" in n]
    assert origem, "a folha da origem das entidades desapareceu"
    for nome in origem:
        assert ":" not in nome, f"{nome!r} voltou a ter dois pontos"


# ==========================================================================
if __name__ == "__main__":
    print(f"  nomes de folha encontrados: {len(NOMES)}\n")
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passaram")
    sys.exit(1 if failures else 0)
