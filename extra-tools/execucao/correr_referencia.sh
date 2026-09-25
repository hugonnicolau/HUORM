#!/bin/bash
# Revalidação dos 17 do conjunto de referência, a N=8.
#
# NÃO COLAR ESTE CONTEÚDO NO TERMINAL.
# Guardar o ficheiro em ~/Desktop/FINAL e correr:   bash correr_gabarito.sh
#
# Sem `split -n` (não existe no macOS) e sem globs no shell: a repartição
# pelos 8 lotes é feita em Python, que também evita problemas com o espaço
# no nome do "Ácido Fólico.pdf".

set -u
cd ~/Desktop/FINAL || exit 1

MODELO="glm-5.3-flash"
MD="markdown_gabarito"
SAIDA="out_gabarito_final"

python3 - <<'PY'
import os, math, glob
for f in glob.glob('glote_*.txt'):
    os.remove(f)
base = os.path.join(os.getcwd(), 'TestSet')
fs = sorted(
    os.path.join(r, f)
    for r, _, nomes in os.walk(base)
    for f in nomes
    if f.lower().endswith('.pdf')
)
if not fs:
    raise SystemExit('Nao encontrei PDFs em TestSet/')
n = math.ceil(len(fs) / 8)
for i in range(8):
    parte = fs[i*n:(i+1)*n]
    with open('glote_%02d.txt' % i, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(parte) + ('\n' if parte else ''))
    print('glote_%02d.txt  %d documentos' % (i, len(parte)))
print('TOTAL:', len(fs))
PY

echo
echo "=== fase 2, 8 processos ==="
time ( for n in 00 01 02 03 04 05 06 07; do
  python3 -m RCMprocessor.batch_processor TestSet "$SAIDA" \
      --model "$MODELO" \
      --markdown-dir "$MD" \
      --file-list "glote_$n.txt" > "log_g$n.txt" 2>&1 &
done; wait )

echo
echo "documentos com saida : $(ls "$SAIDA" 2>/dev/null | wc -l)"
echo "erros nos logs       : $(grep -c 'Erro ao processar' log_g*.txt 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')"
echo "sem estrutura        : $(find "$SAIDA" -name NAO_UTILIZAVEL.json 2>/dev/null | wc -l)"
