#!/bin/bash
# Corrida nacional: 5 623 RCM, 8 processos.
#
# NÃO COLAR NO TERMINAL. Guardar em ~/Desktop/FINAL e correr:
#     bash correr_nacional.sh
#
# Pode ser interrompida a qualquer momento. O --retomar salta o que já tem
# Document_Unique_PGx.json, por isso voltar a correr continua de onde ficou.

set -u
cd ~/Desktop/FINAL || exit 1

MODELO="glm-5.3-flash"
SAIDA="out_nacional"

# O número de processos TEM de igualar o limite de pedidos em simultâneo da
# conta Ollama Cloud: Free 1, Pro 3, Max e Team 10.
#
# Acima desse limite não se ganha nada e perde-se muito: os pedidos a mais
# levam 429, e o backoff dorme 30s, depois 60, depois 120. Com 8 processos
# numa conta Pro, cinco estavam permanentemente a dormir e o documento levava
# 30 minutos quando uma chamada demora 10 segundos.
#
#     bash correr_nacional.sh        -> 3 (Pro)
#     bash correr_nacional.sh 10     -> 10 (Max)
PROCESSOS=${1:-3}

# ---------------------------------------------------------------- guardas
if [ ! -d RCMs_a_processar ]; then echo "falta RCMs_a_processar/"; exit 1; fi
if [ ! -d markdown ];          then echo "falta markdown/";          exit 1; fi

N_PDF=$(ls RCMs_a_processar/*.pdf 2>/dev/null | wc -l | tr -d ' ')
N_MD=$(ls markdown/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "PDFs      : $N_PDF"
echo "markdown  : $N_MD"
if [ "$N_PDF" != "$N_MD" ]; then
  echo
  echo "AVISO: os números não batem. Os que não tiverem markdown vão ser"
  echo "convertidos pelo docling durante a corrida, o que a torna muito mais"
  echo "lenta. Confirma antes de continuar."
  echo
fi

MR=RCMprocessor/data/umls/MRCONSO.RRF
if [ ! -f "$MR" ]; then echo "FALTA o MRCONSO em $MR"; exit 1; fi

# ---------------------------------------------------------------- lotes
python3 - "$PROCESSOS" <<'PY'
import os, math, sys, glob
n_proc = int(sys.argv[1])
for f in glob.glob('lote_nac_*.txt'):
    os.remove(f)
base = os.path.join(os.getcwd(), 'RCMs_a_processar')
fs = sorted(os.path.join(base, f) for f in os.listdir(base) if f.lower().endswith('.pdf'))
# repartição equilibrada: nenhum lote fica vazio
for i in range(n_proc):
    parte = fs[i::n_proc]
    with open('lote_nac_%02d.txt' % i, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(parte) + '\n')
    print('lote_nac_%02d.txt  %d documentos' % (i, len(parte)))
print('TOTAL:', len(fs))
PY

echo
echo "=== arranque: $(date '+%Y-%m-%d %H:%M:%S')   com $PROCESSOS processos ==="
echo

i=0
while [ "$i" -lt "$PROCESSOS" ]; do
  n=$(printf "%02d" "$i")
  caffeinate -i nohup python3 -m RCMprocessor.batch_processor \
      RCMs_a_processar "$SAIDA" \
      --model "$MODELO" \
      --markdown-dir markdown \
      --file-list "lote_nac_$n.txt" \
      --retomar \
      > "log_nac_$n.txt" 2>&1 &
  echo "lote $n  pid $!"
  i=$((i + 1))
done

echo
echo "Os 8 processos estão a correr em segundo plano."
echo "Podes fechar o terminal: o nohup mantém-nos vivos."
echo
echo "Para ver o progresso:   bash ver_progresso.sh"
echo "Para parar tudo:        pkill -f batch_processor"
