"""
Propagation of results from representatives to exact duplicates.

This module decides the denominators of the whole study, and until now it had
no test coverage at all — while never having been run for real.

The preflight collapses documents whose text is byte-identical after
normalisation: 2 201 of 7 832 in the national corpus, 28.1%. Running them all
would, by construction, produce the same answers — the input is the same, the
model runs at temperature 0 with a fixed seed.

But the global analysis walks output folders. Without propagation it would
count 5 631 documents instead of 7 832, and every percentage would rest on the
wrong denominator. Saving compute cannot cost correctness.

The failure mode that matters is silent: a propagation that quietly skips
files leaves an analysis that looks complete and is not.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

MODULO = "RCMprocessor.propagate_duplicates"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _monta(tmp: Path, duplicados: int = 2, com_resultado: bool = True) -> tuple[Path, Path]:
    """Build an output tree with one representative and N duplicates."""
    out = tmp / "out"
    out.mkdir(parents=True, exist_ok=True)

    rep = out / "1000_representante"
    (rep / "pgx_outputs").mkdir(parents=True)
    if com_resultado:
        (rep / "pgx_outputs" / "Document_Unique_PGx.json").write_text(
            json.dumps({
                "pipeline": {"pipeline_version": "2.0.0"},
                "documento": {"substancia_ativa": "ceftriaxona"},
                "contagens": {"genes_unicos_total": 3},
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    (rep / "Interacoes.json").write_text('{"numero": "4.5"}', encoding="utf-8")

    mapa = tmp / "mapa.csv"
    with mapa.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ficheiro", "representante", "chave_grupo",
            "substancia_ativa", "medicamento",
        ])
        w.writeheader()
        for i in range(duplicados):
            w.writerow({
                "ficheiro": f"200{i}_duplicado.pdf",
                "representante": "1000_representante.pdf",
                "chave_grupo": "J01DD04",
                "substancia_ativa": "Ceftriaxona",
                "medicamento": f"Duplicado {i}",
            })
    return out, mapa


def _corre(out: Path, mapa: Path, *extra: str) -> subprocess.CompletedProcess:
    # UTF-8 dos dois lados do cano.
    #
    # Sem `encoding` aqui, o Windows descodifica a saída do filho com a página
    # de códigos do sistema e rebenta com UnicodeDecodeError. E sem PYTHONUTF8
    # no ambiente do filho, é ele que a escreve em cp1252 — e então "já
    # existiam" chega estragado e o teste falha a procurar a palavra.
    #
    # Nenhum dos dois é defeito do pipeline: é o teste a medir a plataforma.
    ambiente = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", MODULO, str(out), "--mapa", str(mapa), *extra],
        capture_output=True, text=True, cwd=str(RAIZ), timeout=120,
        encoding="utf-8", errors="replace", env=ambiente,
    )


# --------------------------------------------------------------------------

def test_propaga_e_marca_proveniencia():
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=2)
        r = _corre(out, mapa)
        assert r.returncode == 0, r.stderr

        pastas = sorted(p.name for p in out.iterdir() if p.is_dir())
        assert len(pastas) == 3, f"1 representante + 2 duplicados, obtive {pastas}"

        alvo = out / "2000_duplicado" / "pgx_outputs" / "Document_Unique_PGx.json"
        assert alvo.exists(), "o resultado não foi copiado"

        dados = json.loads(alvo.read_text(encoding="utf-8"))
        assert dados["pipeline"]["resultado_propagado_de"] == "1000_representante.pdf", (
            "sem esta marca não se distingue um documento processado de um herdado, "
            "e a contagem de chamadas ao modelo deixa de ser auditável"
        )
        # O conteúdo tem de vir intacto.
        assert dados["contagens"]["genes_unicos_total"] == 3


def test_dry_run_nao_escreve_nada():
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=2)
        r = _corre(out, mapa, "--dry-run")
        assert r.returncode == 0, r.stderr
        pastas = [p.name for p in out.iterdir() if p.is_dir()]
        assert pastas == ["1000_representante"], f"criou pastas em simulação: {pastas}"


def test_representante_por_processar_nao_e_silencioso():
    """Sem resultado do representante não há nada a propagar — tem de avisar.

    Se falhasse em silêncio, os duplicados ficariam sem pasta e o denominador
    da análise viria curto sem ninguém dar por isso.
    """
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=2, com_resultado=False)
        r = _corre(out, mapa)
        assert r.returncode == 0, r.stderr
        saida = r.stdout.lower()
        assert "representante não processado" in saida or "não processado" in saida, (
            f"falhou em silêncio; saída:\n{r.stdout}"
        )
        assert "propagados                    : 0" in r.stdout


def test_idempotente():
    """Correr duas vezes não pode duplicar nem corromper."""
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=2)
        _corre(out, mapa)
        antes = sorted(p.name for p in out.iterdir() if p.is_dir())

        r = _corre(out, mapa)
        depois = sorted(p.name for p in out.iterdir() if p.is_dir())

        assert antes == depois, "a segunda passagem alterou as pastas"
        assert "já existiam" in r.stdout, "devia dizer que saltou os existentes"


def test_forcar_substitui():
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=1)
        _corre(out, mapa)

        alvo = out / "2000_duplicado" / "pgx_outputs" / "Document_Unique_PGx.json"
        alvo.write_text('{"lixo": true}', encoding="utf-8")

        r = _corre(out, mapa, "--forcar")
        assert r.returncode == 0, r.stderr
        dados = json.loads(alvo.read_text(encoding="utf-8"))
        assert "lixo" not in dados, "--forcar não substituiu"
        assert dados["contagens"]["genes_unicos_total"] == 3


def test_mapa_inexistente_falha_em_vez_de_seguir():
    with tempfile.TemporaryDirectory() as d:
        out, _ = _monta(Path(d))
        r = _corre(out, Path(d) / "nao_existe.csv")
        assert r.returncode != 0, "devia terminar com erro, não continuar"


def test_conta_o_que_propagou():
    """O número reportado tem de bater com as pastas criadas.

    É por este número que se confirma que o denominador voltou ao certo.
    """
    with tempfile.TemporaryDirectory() as d:
        out, mapa = _monta(Path(d), duplicados=5)
        r = _corre(out, mapa)
        assert "propagados                    : 5" in r.stdout, r.stdout
        criadas = len([p for p in out.iterdir() if p.is_dir()]) - 1
        assert criadas == 5


# ==========================================================================
if __name__ == "__main__":
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
