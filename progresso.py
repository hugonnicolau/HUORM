#!/usr/bin/env python3
"""Progresso da corrida nacional.

Ficheiro próprio e não um bloco dentro do PowerShell: o here-string escreve um
BOM à cabeça e o Python recusa-o.

Uso:
    python progresso.py
    python progresso.py out_nacional
    python progresso.py out_nacional 45     # janela de 45 minutos

O segundo argumento e a janela, em minutos, sobre a qual o ritmo e medido.
Por omissao sao 120. Usar uma janela curta logo a seguir a mexer na rede ou no
numero de processos: a janela larga mistura o ritmo antigo com o novo e esconde
a mudanca que se quer ver.
"""
import glob
import json
import os
import sys
import time
from collections import Counter

saida = sys.argv[1] if len(sys.argv) > 1 else "out_nacional"
try:
    janela_min = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
except ValueError:
    janela_min = 120.0
JANELA = janela_min * 60
total = len(glob.glob(os.path.join("RCMs_a_processar", "*.pdf")))

feitos = []
sem_estrutura = 0
if os.path.isdir(saida):
    for d in os.listdir(saida):
        p = os.path.join(saida, d)
        if not os.path.isdir(p):
            continue
        alvo = os.path.join(p, "pgx_outputs", "Document_Unique_PGx.json")
        nao = os.path.join(p, "NAO_UTILIZAVEL.json")
        if os.path.exists(alvo):
            feitos.append(os.path.getmtime(alvo))
        elif os.path.exists(nao):
            feitos.append(os.path.getmtime(nao))
            sem_estrutura += 1

erros = 0
for f in glob.glob("log_nac_*.txt"):
    try:
        with open(f, encoding="utf-8", errors="ignore") as fh:
            erros += fh.read().count("Erro ao processar")
    except Exception:
        pass

print(f"documentos feitos : {len(feitos)} de {total}")
print(f"sem estrutura     : {sem_estrutura}")
print(f"erros             : {erros}")

if feitos:
    feitos.sort()
    agora = time.time()

    # Ritmo na janela recente, que é o que vale depois de se ter mudado o
    # número de processos ou a rede. O ritmo desde o início mistura a corrida
    # antiga, com 8 processos numa conta que só serve 3, e dá um número que já
    # não descreve nada.
    recentes = [t for t in feitos if agora - t < JANELA]
    if len(recentes) >= 2:
        janela = agora - recentes[0]
        ritmo = len(recentes) / max(janela, 1)
        print(f"\nnas ultimas {janela/3600:.1f} h : {len(recentes)} documentos")
        print(f"ritmo actual      : {ritmo*3600:.0f} documentos/hora")
        falta = total - len(feitos)
        print(f"faltam            : {falta}")
        print(f"ESTIMATIVA        : {falta/max(ritmo,1e-9)/3600:.1f} h  "
              f"({falta/max(ritmo,1e-9)/86400:.1f} dias)")
    else:
        print(f"\nainda sem documentos suficientes nos ultimos {janela_min:.0f} min "
              f"para medir o ritmo; tenta uma janela maior")

    decorrido = agora - feitos[0]
    print(f"\ndesde o primeiro documento: {decorrido/3600:.1f} h, "
          f"media global {len(feitos)/decorrido*3600:.0f}/hora")

# O CUI vir preenchido confirma que o MRCONSO e a cache estao a funcionar.
com_cui = sem_cui = 0
if os.path.isdir(saida):
    pastas = sorted(
        (os.path.getmtime(os.path.join(saida, d)), d)
        for d in os.listdir(saida)
        if os.path.isdir(os.path.join(saida, d))
    )[-30:]
    for _, d in pastas:
        p = os.path.join(saida, d, "pgx_outputs", "Extended_PGx_Analysis.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                j = json.load(fh)
            if (j.get("identificadores_substancia") or {}).get("mrconso_cui"):
                com_cui += 1
            else:
                sem_cui += 1
        except Exception:
            pass
if com_cui or sem_cui:
    print(f"\nnos ultimos documentos: {com_cui} com CUI, {sem_cui} sem CUI")
