# Correcção das associações às guidelines do ClinPGx

Aplicada a 28-09-2026. Não mexe na extracção: entidades, menções, secções e
passagens ficam iguais. Muda apenas a que guidelines cada RCM ficou associado,
e com isso a cobertura.

## O problema

Uma palavra de sal ou genérica bastava para ligar um medicamento a uma
guideline de outro fármaco:

- "beta-histina, **cloridrato**", "tramadol, cloridrato", "mianserina,
  cloridrato": "cloridrato" era procurado sozinho e chegava às guidelines da
  imipramina, do irinotecano e da doxorrubicina ("imipramine hydrochloride"…);
- sais de **sódio** (soro fisiológico, diclofenac sódico, bicarbonato de
  sódio…) ligados ao nitrato de sódio da lista do CPIC para o *G6PD*;
- produtos com **ácido** ligados ao ácido fólico (DPWG, *MTHFR*) e às listas
  do *G6PD* (ácido aminossalicílico, ácido nalidíxico);
- sais de **potássio** ligados a "Vitamin K and analogues" (K é o símbolo do
  potássio);
- a menotropina (**hMG**) ligada às estatinas ("HMG-CoA reductase inhibitors").

Havia ainda dois mecanismos menos óbvios:

- sinónimos do UMLS vindos de correspondências **parciais**: paracetamol +
  cafeína chegava à aspirina por uma marca que junta os três; os salicilatos
  tópicos chegavam lá por "Aspirin measurement";
- **estereoisómeros**: o escitalopram herdava a guideline do citalopram por
  "(S)-citalopram", contra a regra que o próprio código já declarava.

## As regras

1. Palavras de sal ou genéricas nunca bastam sozinhas
   (`GENERIC_TERMS` em `RCMprocessor/substance_utils.py`).
2. Um estereoisómero não herda a guideline do composto de origem.
3. Os sinónimos do UMLS só contam se a correspondência ao conceito for exacta
   (`_expandir_com_sinonimos` em `active_substance_external_resolver.py`).
4. As equivalências verdadeiras ficam declaradas: ácido acetilsalicílico =
   aspirina, ácido ascórbico = vitamina C, metamizol = dipirona (e a que já
   existia, dexibuprofeno = ibuprofeno).

A cache do resolver passa a registar a versão das regras (`REGRAS_CLINPGX`):
uma entrada gravada com as regras antigas tem o cruzamento com o ClinPGx refeito
a partir do MRCONSO guardado, sem rede. 199 testes, todos verdes.

## Como foi aplicada às saídas

```powershell
python extra-tools\preparacao\recalcular_guidelines.py out_nacional --copia correcao_guidelines\antes
```

323 documentos mudaram; a lista, com as guidelines removidas e acrescentadas
em cada um, está em `ALTERACOES.csv`. As versões anteriores dos ficheiros estão
em `antes/`, e o Excel e a base de antes em `Analise_Global_PGx_antes.xlsx` e
`huorm_antes.db`. Um documento ganhou associações (um RCM de pantoprazol que
não tinha as guidelines do pantoprazol); os restantes só perderam.

Verificação: todas as 3 380 associações que ficam foram confrontadas com o nome
da substância, a tradução inglesa ou uma equivalência declarada. Bate em todas
menos uma (sulfacetamida sódica, por um sinónimo exacto do UMLS), que não
altera nenhum par, porque a sulfacetamida tem a sua própria entrada do CPIC
para o *G6PD*.

## Números

| | antes | agora |
|---|---:|---:|
| pares fármaco-gene com guideline | 890 | 623 |
| representados no rótulo | 166 (18,7%) | 164 (26,3%) |
| documentos de substâncias com guideline | 1 601 | 1 353 |
| que não nomeiam o gene | 814 (50,8%) | 575 (42,5%) |

A extracção não muda: 5 551 documentos, 3 131 com conteúdo PGx, 1 200 com
entidade, 5 831 menções.

## Para pôr a API em dia

A partir de `FINALV2\api`:

```powershell
npx wrangler d1 execute huorm --remote --file=huorm_d1.sql
```
