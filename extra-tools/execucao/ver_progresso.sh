#!/bin/bash
# Progresso da corrida nacional.
#     bash ver_progresso.sh

set -u
cd ~/Desktop/FINAL || exit 1

SAIDA="out_nacional"
TOTAL=$(ls RCMs_a_processar/*.pdf 2>/dev/null | wc -l | tr -d ' ')

VIVOS=$(ps aux | grep batch_processor | grep -v grep | wc -l | tr -d ' ')
FEITOS=$(find "$SAIDA" -name Document_Unique_PGx.json 2>/dev/null | wc -l | tr -d ' ')
SEMESTRUT=$(find "$SAIDA" -name NAO_UTILIZAVEL.json 2>/dev/null | wc -l | tr -d ' ')
ERROS=$(grep -h "Erro ao processar" log_nac_*.txt 2>/dev/null | wc -l | tr -d ' ')

echo "processos vivos   : $VIVOS de 8"
echo "documentos feitos : $FEITOS de $TOTAL"
echo "sem estrutura     : $SEMESTRUT"
echo "erros             : $ERROS"

INICIO=$(ls -ld "$SAIDA" 2>/dev/null | awk '{print $6, $7, $8}')
echo "pasta criada em   : $INICIO"

if [ "$FEITOS" -gt 0 ]; then
  python3 - "$SAIDA" "$FEITOS" "$TOTAL" <<'PY'
import os, sys, time
saida, feitos, total = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
t0 = os.path.getmtime(saida)
# o mais antigo Document_Unique_PGx.json marca o arranque real
mais_antigo = None
for r, _, fs in os.walk(saida):
    if 'Document_Unique_PGx.json' in fs:
        m = os.path.getmtime(os.path.join(r, 'Document_Unique_PGx.json'))
        if mais_antigo is None or m < mais_antigo:
            mais_antigo = m
if mais_antigo:
    decorrido = time.time() - mais_antigo
    ritmo = feitos / max(decorrido, 1)
    resta = (total - feitos) / max(ritmo, 1e-9)
    print(f"decorrido         : {decorrido/3600:.2f} h")
    print(f"ritmo             : {ritmo*3600:.0f} documentos/hora")
    print(f"ESTIMATIVA        : faltam {resta/3600:.1f} h")
PY
fi

echo
echo "últimas linhas do lote 00:"
tail -3 log_nac_00.txt 2>/dev/null || echo "  (ainda sem saída — o Python guarda em buffer)"
