# Por corrigir na base de dados

Nada disto afecta a dissertação: os números do texto vêm do
`Analise_Global_PGx.xlsx`, não daqui. São defeitos da base e da API, para
quando houver tempo e quota de escrita no D1.

---

## 1. O código ATC aparece em duas grafias

**O problema.** O mesmo código está gravado de duas maneiras, porque vem
extraído do texto do rótulo e alguns RCM escrevem-no com um espaço:

```
M01AE01     45 documentos
M01A E01    26 documentos
```

São o mesmo grupo — ibuprofeno oral — e a base trata-os como dois. Quem
consultar a API por `codigo_atc` recebe o grupo partido ao meio, o que é pior
do que não ter a coluna: parece uma resposta completa e não é.

O preflight não sofre disto porque usa o ATC do **índice do INFOMED**, não do
texto. Foi por isso que a dissertação conseguiu formar o grupo inteiro de 81
registos enquanto a base só vê 45.

**A correcção.** Normalizar no `construir_bd.py`, ao inserir o documento:
retirar espaços e passar a maiúsculas antes de gravar `codigo_atc`. Vale a
pena verificar antes se há outras grafias além do espaço a meio (pontos,
hífenes), com:

```sql
SELECT codigo_atc, COUNT(*) FROM documento
 WHERE codigo_atc IS NOT NULL GROUP BY codigo_atc ORDER BY 2 DESC;
```

**Cuidado.** O ATC do índice e o ATC do rótulo podem divergir por outras
razões que não a grafia. Normalizar resolve o espaço, não resolve uma
divergência de conteúdo — se aparecerem documentos cujo código do rótulo não é
o do registo, isso é outro problema e merece ser olhado antes de se juntar
tudo.

---

## 2. O campo `medicamento` junta apresentações

Num documento que cobre várias dosagens, o campo traz as três concatenadas:

```
Mayzent 0 , 25 mg comprimidos revestidos por película
Mayzent 1 mg comprimidos revestidos por película
Mayzent 2 mg comprimidos revestidos por película
```

Vem assim da extração, não da base. Fica legível mas ocupa a largura toda da
tabela na página de consulta.

---

## 3. O ATC não é lido quando vem mal escrito no RCM

**O problema.** O `codigo_atc` vem do texto da secção 5.1, e a extracção falha
quando o código está escrito fora do formato: com espaços (`C09 AA 03`,
`N 03 A G01`), com a letra O no lugar do zero (`NO5BA12`, `LO2BG03`,
`CO9BA04`, `BO6AB`) ou com hífenes (`B -01 -AB -10`). Nesses documentos o
campo fica vazio e o documento parece não ter ATC, quando tem.

Verificado a 26-09-2026 nos 747 RCM que dão o grupo farmacoterapêutico só
como descrição: 743 imprimem o código, mas o pipeline só leu 704. Os 39 que
falham estão todos neste caso. Só um (`50757_Irbesartan_Hidroclorotiazida_BasiMG`)
tem o rótulo "código ATC:" vazio.

**A correcção.** A mesma normalização do ponto 1, alargada: antes de validar,
retirar espaços e hífenes e trocar O por 0 nas posições que são dígitos no
formato ATC (letra, 2 dígitos, letra, letra, 2 dígitos). Como alternativa,
usar o ATC do índice do INFOMED quando o do texto vier vazio, registando de
qual das fontes veio.

---

## Depois de corrigir

O ciclo é o mesmo de sempre, e a ordem importa:

```powershell
python basedados\construir_bd.py out_nacional basedados\huorm.db
python basedados\construir_bd.py --verificar basedados\huorm.db
Copy-Item basedados\huorm.db basedados\site\huorm.db -Force
cd api
python exportar_para_d1.py ..\basedados\huorm.db huorm_d1.sql
npx wrangler d1 execute huorm --remote --file=huorm_d1.sql
```

A verificação tem de continuar a dizer **5831 menções**, **3131 documentos com
PGx** e **1200 com entidade** (corpus de 26-09-2026, sem os 14 documentos fora
do índice do INFOMED; ver `fora_do_indice/LEIA-ME.md`). Se algum mudar, a correcção do ATC mexeu em
mais do que devia.

Lembra-te do limite: são cerca de 69 000 escritas por importação e o plano
gratuito dá 100 000 por dia.
