#!/usr/bin/env python3
"""Mede a latência do modelo com pedidos REAIS, não com os de 64 tokens.

O `probe_concorrencia.py` usava `--num-predict 64` e um excerto curto. A
extração real envia blocos de 6 000 caracteres e recebe JSON longo. A latência
por chamada não tem nada a ver, e foi por isso que a estimativa da corrida
falhou por uma ordem de grandeza.

Este script tira um bloco verdadeiro de um documento já processado e mede a
latência a várias concorrências, com o mesmo prompt e as mesmas opções do
pipeline.

Correr a partir de ~/Desktop/FINAL, com a corrida a decorrer ou parada:
    python3 probe_real.py
    python3 probe_real.py 8 16 32 48
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    from dotenv import load_dotenv
    # O load_dotenv() sem argumentos procura a partir da pasta do ficheiro que
    # o chama. O do pipeline vive dentro de RCMprocessor/ e encontra o .env lá;
    # este script está um nível acima e não encontrava nada.
    for candidato in (BASE / "RCMprocessor" / ".env", BASE / ".env"):
        if candidato.exists():
            load_dotenv(candidato)
            break
    else:
        load_dotenv()
except ImportError:
    pass

from ollama import Client  # noqa: E402

MODELO = os.environ.get("MODELO_PROBE", "glm-5.3-flash")
OPCOES = {"temperature": 0.0, "top_p": 1.0, "top_k": 1, "seed": 42}


def arranjar_bloco() -> str:
    """Um bloco real, do tamanho que o pipeline envia."""
    for raiz in ("out_nacional", "out_gabarito_final", "markdown"):
        p = Path(raiz)
        if not p.exists():
            continue
        for f in p.rglob("*.md"):
            t = f.read_text(encoding="utf-8", errors="ignore")
            if len(t) > 6000:
                return t[:6000]
    return "texto de teste " * 400


PROMPT = """Analisa o seguinte excerto de um Resumo das Características do Medicamento.

Extrai as entidades farmacogenómicas presentes: genes, alelos star, diplótipos e rsID.

Responde apenas com JSON válido, no formato:
{{"genes": [], "star_alleles": [], "diplotipos": [], "rsids": []}}

Texto:
{texto}
"""


def main() -> int:
    escala = [int(x) for x in sys.argv[1:]] or [1, 4, 8, 16]
    bloco = arranjar_bloco()
    prompt = PROMPT.format(texto=bloco)
    print(f"modelo   : {MODELO}")
    print(f"prompt   : {len(prompt)} caracteres")
    print(f"escala   : {escala}")
    print()

    chave = os.environ.get("OLLAMA_API_KEY", "")
    if not chave:
        print("OLLAMA_API_KEY não encontrada. Procurei em:")
        print(f"  {BASE / 'RCMprocessor' / '.env'}")
        print(f"  {BASE / '.env'}")
        print("Alternativa: export OLLAMA_API_KEY='...' antes de correr.")
        return 1
    print(f"chave    : encontrada ({len(chave)} caracteres)")
    print()

    cliente = Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {chave}"},
        timeout=300,
    )

    def uma(_):
        t0 = time.time()
        try:
            r = cliente.chat(model=MODELO,
                             messages=[{"role": "user", "content": prompt}],
                             stream=False, options=OPCOES)
            saida = (r.get("message") or {}).get("content") or ""
            return time.time() - t0, len(saida), None
        except Exception as e:
            return time.time() - t0, 0, str(e)[:60]

    print(f"{'N':>3}  {'ok':>4}  {'falhas':>6}  {'mediana':>9}  {'p95':>9}  "
          f"{'chars':>7}  {'débito':>12}")
    print("-" * 66)

    for n in escala:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=n) as ex:
            res = list(ex.map(uma, range(n)))
        ronda = time.time() - t0
        ok = [r for r in res if r[2] is None]
        mau = [r for r in res if r[2] is not None]
        if ok:
            lat = sorted(r[0] for r in ok)
            med = statistics.median(lat)
            p95 = lat[int(0.95 * (len(lat) - 1))]
            chars = statistics.mean(r[1] for r in ok)
            deb = len(ok) / ronda
            print(f"{n:>3}  {len(ok):>4}  {len(mau):>6}  {med:>8.1f}s  {p95:>8.1f}s  "
                  f"{chars:>7.0f}  {deb:>8.3f}/s")
        else:
            print(f"{n:>3}  {0:>4}  {len(mau):>6}   todas falharam: {mau[0][2]}")

    print()
    print("O que interessa: a latência mediana com um pedido real, e se o débito")
    print("continua a subir com N. Se subir, mais processos resolvem a corrida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
