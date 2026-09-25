# Registo consolidado — base para a escrita da tese

Última atualização: 17/08/2026 · pipeline versão 2.0.0 · 138 testes automáticos

Documento único com **todos os números, decisões metodológicas e achados**, cada
um com a origem indicada. Serve de fonte para os Métodos, Resultados e
Discussão. Substitui as notas dispersas.

> Leitura complementar já em disco:
> `METODOLOGIA_REPLICACAO.md` (mapeamento ao Jeiziner), `REVISAO_PIPELINE.md`
> (arquitetura e dívida técnica), `AUDITORIA_PASSAGEM1.md` (detalhe dos bugs),
> `NOTAS_DE_ALTERACOES.md` (versão para a orientadora),
> `mluis/_LEIA-ME.md` (subconjunto dos 78 compostos).

---

# 1. O corpus

## 1.1 Recolha

Scraper próprio sobre o Infomed (`extranet.infarmed.pt/INFOMED-fo`), aplicação
JSF/PrimeFaces sem API pública. Varrimento por 12 taxonomias do portal, com
retoma e verificação de integridade binária.

| Métrica | Portal oficial | Recolhido | Cobertura |
|---|---|---|---|
| Substâncias ativas (DCI) | 1 692 | **1 661** | 98,2 % |
| Medicamentos comercializados | 10 426 | **9 538** | 91,5 % |
| Com RCM publicado no Infomed | 7 818 | **7 808** | 99,9 % |
| PDFs em disco (RCM + FI) | — | **15 654** | 100 % íntegros |

**Rendimento marginal por eixo de pesquisa:** ATC 7 351 · Classificação
Farmacoterapêutica 415 · Forma Farmacêutica 42. O ATC sozinho não chega —
487 medicamentos (5,1 %) não têm ATC atribuído e são invisíveis a esse filtro.

## 1.2 O denominador correto

**O corpus de trabalho é de ~7 800 RCM, não de 10 400.** Dos 9 538
medicamentos, apenas 7 818 têm RCM publicado no Infomed. Os 1 720 restantes:

| Motivo | N |
|---|---|
| Autorização centralizada europeia (RCM está no sítio da EMA) | 969 |
| Importação paralela | 65 |
| Aprovações nacionais antigas e preparações tradicionais | 686 |

Isto tem de ficar explícito nos Métodos: o número do portal (10 426) refere-se a
**medicamentos**, não a RCMs disponíveis.

## 1.3 Digitalizações

Documentos sem camada de texto foram identificados e excluídos, em vez de
contribuírem silenciosamente com zeros. **4 em 7 836 (0,05 %)**:

```
43724_Valsartan_Hidroclorotiazida_TevaMG.pdf      0 caracteres
631242_Dexavit.pdf                                 0
703204_Tadalafil_VenxalMG.pdf                     31
703206_Tadalafil_VenxalMG.pdf                     31
```

**OCR foi avaliado e descartado.** Texto pouco fiável produz entidades
inexistentes, o que é pior do que a ausência de texto. Sem esta marcação, um RCM
digitalizado é indistinguível de um que genuinamente não tem PGx, e o
denominador de todas as percentagens fica errado.

## 1.4 Standardização dos nomes

7 838 ficheiros renomeados para `{med_id}_{slug-ascii}.pdf`. O `med_id` é o
número de registo do Infomed — a chave de junção com o `medicamentos.csv`.

- **575** ficheiros tinham acentos. macOS guarda-os decompostos (NFD), Windows
  compostos (NFC): o mesmo nome deixa de ser encontrado ao copiar a pasta entre
  sistemas, sem erro visível.
- **2** tinham extensão `.pdf0000` (bug do scraper) e eram invisíveis ao
  `glob("*.pdf")`.
- Zero colisões após a renomeação.

---

# 2. Deduplicação

## 2.1 O critério de Jeiziner et al. (2021)

Duas partes, e a ordem importa:

1. **agrupar** por código ATC (identidade química)
2. **colapsar** por igualdade de texto dentro do grupo

O ATC agrupa; é o texto que decide o que colapsa. Um grupo ATC com textos
divergentes gera mais do que um refDL — foi o caso do fluorouracilo no artigo
original, único em 167.

O representante é o produto de marca; na sua ausência, o primeiro genérico. No
artigo era "arbitrariamente"; aqui é determinístico (lista de titulares de
genéricos + ordem alfabética), para ser reproduzível.

## 2.2 O método não transfere para Portugal

| | Suíça (2021) | Portugal |
|---|---|---|
| Redução | **88,1 %** | **28,1 %** |
| Grupos com texto uniforme | 166/167 (**99,4 %**) | 73/822 (**8,9 %**) |

Três hipóteses testadas e eliminadas:

1. **Marca comercial** — neutralizados nome, titular, dosagens e datas. A
   redução **piorou** marginalmente (5 610 → 5 633 refDLs).
2. **Forma farmacêutica** — agrupar por ATC + forma subiu a uniformidade de
   8 % para 11 %. Marginal. Por ATC + forma + dosagem colapsa tudo (0,2 %).
3. **Semelhança real** — 5-gramas em 153 pares: mediana **0,576**, p10 0,075,
   e apenas **12 %** dos pares acima de 0,99.

**Conclusão:** os RCM portugueses de genéricos do mesmo ATC são documentos
genuinamente diferentes. Na Suíça os genéricos adotam o texto do original; em
Portugal cada titular redige o seu. É uma diferença regulamentar entre países e
constitui um resultado publicável.

Diagnóstico concreto: dois genéricos de atorvastatina têm textos **98,3 %**
idênticos, diferindo no nome comercial (repetido dezenas de vezes), em variantes
de excipiente (`cálcica` vs `cálcica tri-hidratada`) e em artefactos de extração
(`mono-hidratada` vs `mono- hidratada`).

## 2.3 Releitura do artigo

Os autores compararam *"the PGx-relevant sentences"* — as frases
farmacogenómicas, não o documento integral. A deduplicação equivalente terá de
ser feita **depois** da extração, sobre o conteúdo PGx.

## 2.4 O que se pode deduplicar antes (e é seguro)

Distinção que importa e que inicialmente confundi:

- **Duplicados exactos** (mesmo ATC, mesmo texto após neutralizar datas e
  paginação) — correr o LLM em ambos dá **provadamente** o mesmo resultado,
  porque o input é idêntico. Podem ser saltados antes.
- **refDL do Jeiziner** — exige o conteúdo PGx, vem depois.

Medido no corpus completo (`preflight.py`):

```
7 838  PDFs
    6  digitalizações excluídas
7 832  utilizáveis
1 286  grupos por ATC
5 631  A PROCESSAR
2 201  duplicados poupados      28,1 %   ≈ 62 horas de compute
```

A propagação (`propagate_duplicates.py`) copia o resultado do representante
para cada duplicado, marcando `resultado_propagado_de` no bloco `pipeline`. Sem
isso a análise contaria 5 631 e não 7 832, e as percentagens ficariam sobre o
denominador errado.

## 2.5 Concentração do corpus

Exemplo do subconjunto dos 78 compostos (`mluis/`): **rosuvastatina 173 RCM,
varfarina 1**. Qualquer estatística por documento é dominada pelas estatinas;
por substância, não. É o argumento da deduplicação num caso concreto.

---

# 3. Estudos de referência

## 3.1 Jeiziner et al. (2021) — Suíça

*Pharmacogenetic information in Swiss drug labels — a systematic analysis.*
The Pharmacogenomics Journal 21:423–434. doi:10.1038/s41397-020-00195-4

- 4 306 rótulos / 15 367 produtos, rastreio por NLP determinístico
- 25 radicais escolhidos por painel de peritos → 245 termos de pesquisa
- 5 979 frases-candidatas → **2 564 PGx-relevantes** (avaliação manual)
- **167 refDLs**, cobertura 167/1 763 ATC = **9,47 %**
- 92 (55 %) *actionable PGx* · CYP2D6 o biomarcador mais frequente (n=52)
- Secção dominante: farmacocinética (n=1 110) · Grupo ATC dominante: N (n=793)
- Consistência: 10 % reanotado, 5 % por segunda pessoa

**Critérios de exclusão (copiar tal e qual, para comparabilidade):**
mutações com prevalência <1 %; defeitos génicos ligados à doença; anomalias
cromossómicas; fatores genéticos não humanos; genes de seleção de tratamento
(oncologia); **biomarcadores relativos a um fármaco que não o do rótulo**.

O último é o mais fácil de falhar automaticamente e merece teste dedicado.

Limitaram-se à **farmacocinética** e admitem ter perdido a maioria dos
oncológicos. Alargar à farmacodinâmica ganha cobertura mas perde comparabilidade
— decidir e declarar.

**Dois níveis de análise, nunca com denominadores misturados:**
frase (2 564, todos os produtos) e refDL (167, deduplicado). O abstract carrega
os dois na mesma frase: *"From 5979 hits, 2564 were classified as PGx-relevant
affecting 167 substances."*

## 3.2 Ferreira & Santos — Portugal, SNC

Dissertação de Mestrado em Farmácia, ESS-IPP, 2023. Orientadora Marlene Santos.
recipp.ipp.pt/handle/10400.22/24788 · resumo em *Neuroscience Applied* 5 (2026)
106085.

**Método:** Infomed → filtro Classificação Farmacoterapêutica **Grupo 2 (SNC)**
→ Estado AIM "autorizado" (maio 2023) → cruzamento com CPIC e PharmGKB,
**excluindo os princípios ativos ausentes de ambas** → pesquisa por
"Substância ativa/DCI" um a um, com Comercialização "Comercializado" →
**apenas formulações simples**, associações excluídas.

**62 princípios ativos** (61 comercializados) → 1 162 medicamentos →
**1 135 RCM e 1 136 FI**.

Resultados: PGx em **12,0 % dos FI** (n=136) e **64,8 % dos RCM** (n=736).
Nos FI sobretudo no capítulo 2; nos RCM sobretudo em 4.5.

**Os 64,8 % não são uma estimativa de prevalência.** Pré-selecionaram fármacos
que já se sabia terem PGx. Responde a *"dos fármacos SNC com PGx conhecida,
quantos a têm no RCM?"*, não a *"que fração dos RCM tem PGx?"*. Um leitor
distraído vai comparar com o teu número — convém antecipar na discussão.

**Diferenciadores do teu estudo:** âmbito 9× maior (todo o Infomed, não só SNC);
inclui associações (eles excluíram e apontam-no como limitação); deduplicação
sistemática (eles notaram 44 documentos EMA repetidos e 2 Nicorette à mão, sem
critério); automatizado (eles reviram 2 271 documentos manualmente — não
escalaria para 7 800).

Usaram o **grupo farmacoterapêutico do Infarmed**, não o ATC. É a hierarquia
cujo código o pipeline passou a extrair (`2.9.3` etc.), portanto replicar o
âmbito exato é um filtro `codigo.startswith("2")`.

---

# 4. Gabarito ClinPGx

Snapshot em `data/clinpgx/`: 217 guideline annotations, 208 substâncias
distintas, 25 041 símbolos de gene em `genes.tsv`.

## 4.1 Guidelines com múltiplas substâncias

**31 das 217 (14 %)** cobrem vários fármacos — quase todas CPIC (23/31).
Distribuição: 186 com 1 substância, 11 com 2, 5 com 3, caudas até 25.

**Mas não são medicamentos combinados** — cada fármaco está listado
individualmente em `relatedChemicals`. São guidelines de classe (SSRI,
beta-bloqueantes, opioides, estatinas). Isto valida o desenho de partir
combinações em componentes.

**Substância que é ela própria uma combinação: apenas 1** em 208 —
`sulfamethoxazole / trimethoprim` (PA166279741, CPIC, G6PD). É por isso que o
`split_substances` mantém também a string completa como candidato.

## 4.2 Genes por guideline

190 das 217 têm **um só gene**; 27 são multigénicas. A pior é `PA166341522`
(beta-bloqueantes): ADRA2C, ADRB1, GRK4, GRK5.

**Regra adotada:** um documento *referencia* a guideline quando menciona **pelo
menos um** dos genes; *cobre-a* quando menciona **todos**. Exigir todos faria
com que nenhum RCM de metoprolol contasse, e um RCM de varfarina que menciona
CYP2C9 e VKORC1 mas omite CYP4F2 apareceria como não tendo guideline.

## 4.3 População esperada positiva no corpus

```
7 793  RCM com substância identificada
1 194  substâncias distintas
  131  substâncias com ≥1 guideline ClinPGx    11,0 %
1 857  RCM dessas substâncias                  23,8 %
```

**Um em cada quatro RCM pertence a um fármaco com farmacogenética
estabelecida.** É o denominador do estudo.

Genes mais esperados: CYP2D6 (71 substâncias) · SLCO1B1 (46) · CYP2C19 (38) ·
CYP3A4/5 (26) · ABCG2 (24) · HMGCR (23) · HLA-B (18).

*Limite inferior:* a tradução PT→EN para este cálculo foi por regras
morfológicas, não pelo LLM. Onde as regras falham, a substância conta como sem
guideline. Calibração: 16/17 num conjunto de controlo.

---

# 5. Validação com controlos

## 5.1 Desenho

Dois subconjuntos, com o resultado esperado calculado previamente a partir do
ClinPGx — sem isso, um zero é indistinguível de uma falha.

**Correções ao desenho original dos controlos:**

- **Isoniazida e rifampicina não têm guideline** no ClinPGx. Têm variantes
  clínicas (NAT2, CYP2B6, GSTM1 e outras), que é um nível de evidência
  distinto. Devem sair do controlo positivo ou passar a categoria própria.
- **Ácido fólico tem guideline** (DPWG, MTHFR). Estava no controlo negativo.

## 5.2 Resultados (17/08/2026, pipeline 2.0.0)

**Controlo negativo (6 RCM):**

```
0 com guideline · 0 entidades · 0 falhas de extração
1 com PGx  ← Cetirizina
```

**Controlo positivo (11 RCM):**

```
9 com PGx · 8 com par fármaco-gene · 0 com guideline sem PGx
45 menções de genes com guideline · 106 de entidades
Falhas de extração: 0 · Não-verbatim: 3 (todos "recomposto")
```

Todos os 11 documentos com as **7 secções normativas** extraídas.

## 5.3 Cobertura de guidelines — o achado principal

| Gene | Cobertura | | Gene | Cobertura |
|---|---|---|---|---|
| CYP2C19 | 7/7 (100 %) | | COMT | 0/2 (0 %) |
| CYP2C9 | 5/5 (100 %) | | OPRM1 | 0/2 (0 %) |
| CYP2D6 | 4/4 (100 %) | | ABCG2 | 0/2 (0 %) |
| HLA-B | 4/4 (100 %) | | HTR2A | 0/1 (0 %) |
| VKORC1 | 4/4 (100 %) | | SLC6A4 | 0/1 (0 %) |
| SLCO1B1 | 3/3 (100 %) | | CYP3A4/5, HMGCR | 0/1 (0 %) |

**Os genes de metabolização são sempre mencionados; os de resposta e transporte,
nunca.** Varfarina menciona CYP2C9 e VKORC1 mas omite CYP4F2. Escitalopram
menciona CYP2C19 e CYP2D6 mas omite HTR2A e SLC6A4.

É o resultado mais forte, e é o espelho documental da limitação que o Jeiziner
admite no método deles (limitaram-se à farmacocinética).

## 5.4 Casos individuais esclarecidos

**Rifampicina — `PGx=Não` é correto.** As 7 secções foram lidas. O CYP3A4 e o
CYP2B6 aparecem em contexto de **indução enzimática** numa interação
medicamentosa, que o prompt exclui explicitamente. Na primeira corrida dava
"Sim" — era provavelmente um falso positivo do bug da subcadeia `"sim"`.

**Cetirizina — decisão pendente.** `PGx=Sim`, `entidades=Não`, por:
> *"Os doentes com intolerância hereditária à frutose (IHF) não devem tomar
> este medicamento."*

É uma condição genética que contraindica **por causa da composição** do fármaco
(sorbitol). O gene existe (ALDOB); o RCM não o nomeia. Três opções:

1. **Excluir**, para comparabilidade — o Jeiziner exclui *"disease-related gene
   defects"*.
2. **Incluir como categoria própria**: "contraindicação genética sem par
   fármaco-gene". Mais rico, obriga a justificar a divergência.
3. **Manter e tratar na discussão.**

Nota estrutural: `PGx=Sim` com `entidades=Não` é um estado legítimo e
informativo. Aparece como "documento com PGx sem entidades" e alimenta a
cobertura de guidelines como ausência de par — o pipeline não se contradiz,
descreve a realidade do documento.

**Siponimod — tabelas.** Único documento com entidades vindas de tabelas: 7
únicas, 13 menções, e **1 que não existe em mais lado nenhum do documento**.

---

# 6. Arquitetura do pipeline

Três tipos de mecanismo, e a distinção importa para os Métodos.

## 6.1 Normalização — corre sempre

| Etapa | O que faz | Efeito medido |
|---|---|---|
| Símbolos Symbol | `U+F0xx` → `≥ µ ° ± •` | 331 caracteres em 10 de 71 docs |
| Números de secção | `4 . 2` → `4.2` | recuperou 7 secções (ácido fólico) |
| Segmentação | parágrafo → frase → corte à força | 0 blocos cortados a meio de frase (antes 3 de 4) |
| Contagem | fronteira de token | `CYP2D6*1` contava 4 onde há 1 |
| Tabelas | unidade própria + legenda | 6 diplótipos CYP2C9 recuperados |

## 6.2 Fallback — só quando a via principal falha

**Reconhecimento de secções por título.** Se o cabeçalho disser
`### 4.5 Interações`, é isso que vale. Três travões: a via numérica ganha
sempre, cada número é atribuído uma só vez, títulos ambíguos são descartados.

Testado contra 19 secções que **não** deve capturar (Indicações, Sobredosagem,
Excipientes, Titular da AIM…) e contra subtítulos enganadores
("Posologia pediátrica recomendada" vive dentro de 4.2).

Efeito: fentanilo e ondansetrom de **0 → 7 secções**; nos 71 documentos,
447 → 478 secções, **zero regressões**.

**Registo de falhas de extração.** JSON inválido não fabrica excerto: guarda-se
a resposta bruta à parte e conta-se. Antes guardava o bloco de 6 000 caracteres
como se fosse texto do RCM.

## 6.3 Verificação — confirma sem alterar

**Fidelidade dos excertos**, em três estados:

| Estado | Significado | Conta para entidades? |
|---|---|---|
| `verbatim` | cópia contígua e literal | sim |
| `recomposto` | existe no documento, em partes não contíguas | sim |
| `nao_encontrado` | contém texto inexistente | **não** |

Resultado: **0 `nao_encontrado` em 39 extrações.** Os `recomposto` são tabelas
que o docling emitiu fora da ordem de leitura.

Suporta uma afirmação verificada nos Métodos: *"os excertos são cópias literais
do RCM"* — que é o que compensa parte da diferença face a métodos
determinísticos.

**Símbolos de gene ambíguos.** 29 símbolos do ClinPGx colidem com palavras
portuguesas. Medido em 3,5 M caracteres:

```
TES  4 461 ocorrências,  38 em maiúsculas
POR  2 572,               3   ← e as 3 são "INJEÇÃO POR BÓLUS"
AR   1 577,               1   ← "artrite reumatoide (AR)"
ADA  1 120,               0
```

Maiúsculas não chegam: zero verdadeiros positivos em ambos. Exige-se
**maiúsculas no original E vocabulário genético** numa janela de 160
caracteres. `TPMT`, `DPYD`, `COMT`, `CFTR`, `MTHFR`, `NAT2`, `RYR1` ficam de
fora da regra.

**Guideline ≠ evidência.** Três níveis mantidos separados:

```
genes.tsv            → gene farmacogeneticamente relevante em abstrato
clinicalVariants.tsv → evidência de variante clínica
guidelineAnnotations → guideline para este par fármaco-gene    ← só este conta
```

## 6.4 Reprodutibilidade

`temperature=0`, `top_p=1`, `top_k=1`, `seed=42`, modelo `gpt-oss:120b`.
Registados em cada documento no bloco `pipeline`, com versão e timestamp UTC. A
análise global assinala se o corpus tiver sido produzido com configurações
diferentes.

Antes a temperatura não era definida e usava o default do Ollama (**0,8**) — duas
execuções sobre o mesmo RCM davam contagens diferentes.

---

# 7. Bugs corrigidos, com impacto medido

| # | Problema | Impacto |
|---|---|---|
| 1 | `"sim" in resposta` — subcadeia | 4 falsos positivos em 6 respostas de teste ("**sim**plesmente", "as**sim**", "**sim**ilar") |
| 2 | Temperatura não definida | extração não reprodutível |
| 3 | Contagem por substring | `CYP2D6*1` contava 4 onde há 1 (atinge o alelo selvagem e os mais frequentes) |
| 4 | Genes sem `guideline_ids` no output compacto | **222 de 222** linhas de gene sem guideline; CYP2D6 em 42 docs com 157 menções |
| 5 | `has_guideline` bastava `clinpgx.found` | 49 de 135 docs (36 %) "com guideline" e zero PGx |
| 6 | Corte cego aos 6 000 caracteres | 3 de 4 blocos partidos a meio de frase |
| 7 | Resposta do modelo em `texto_original` | citações do modelo indistinguíveis de texto do RCM |
| 8 | Tabelas removidas e nunca lidas | 6 diplótipos CYP2C9 do siponimod perdidos |
| 9 | Log dava "Processado" a documentos vazios | tramadol oral com 0 secções contava como sucesso |
| 10 | Símbolos de gene ambíguos | `POR` podia render dezenas de menções fabricadas |

**Removido:** segunda passagem ao modelo (classificação Sim/Não redundante —
de ~374 000 para ~187 000 chamadas no corpus completo); fallback que guardava o
bloco inteiro; `pgx_ner.py` e `repair_document_unique_pgx.py`; `merpy`, `ssmpy`,
`opencv-python-headless`.

**Cada bug nasceu de um documento concreto.** A cetamina deu o reconhecimento
por título, o ácido fólico deu a compactação dos números, o siponimod deu as
tabelas, o remifentanilo deu o `POR`, a rifampicina deu a confirmação do bug da
subcadeia. Nenhum foi antecipado.

---

# 8. Fluxo de execução

```bash
# 1. pré-voo — minutos, sem LLM
python -m RCMprocessor.preflight <pdfs> --csv INFOMEDDATASET/medicamentos.csv \
    --out preflight --lotes 10

# 2. processar, retomável
python -m RCMprocessor.batch_processor <pdfs> out \
    --file-list preflight/processar.txt --retomar

# 3. propagar aos duplicados exactos
python -m RCMprocessor.propagate_duplicates out \
    --mapa preflight/mapa_duplicados.csv

# 4. análise global
python -m RCMprocessor.pgx_global_analysis out
```

Verificação antes de qualquer corrida: `python RCMprocessor/tests/run_all.py`
→ **138/138**.

Tempo por documento: ~1min42 a 2min23 (medido em 17 documentos).

---

# 9. Decisões pendentes

1. **Cetirizina / intolerância hereditária à frutose** — conta como PGx?
   (§5.4). Afeta os critérios de inclusão.
2. **Isoniazida e rifampicina** no controlo positivo — mover para categoria
   "com evidência de variante, sem guideline"?
3. **Farmacodinâmica** — alargar além da farmacocinética? Ganha cobertura,
   perde comparabilidade direta com Jeiziner.
4. **Metabolitos** em `EQUIVALENCES` — `norclobazam`, `desmethylnaproxen`,
   `O-desmethyltramadol`, `N-desmethyltamoxifen` herdam as anotações do
   fármaco-mãe? Decisão farmacológica, deixada em aberto de propósito.
   Ver `RCMprocessor/review_substance_equivalences.csv` (63 pares).
5. **Os 26 compostos sem RCM** dos 78 (`mluis/_LEIA-ME.md`) — recolher os 7 de
   autorização centralizada da EMA? Confirmar o **mefenamato**, que em Portugal
   é *ácido mefenâmico*.

---

# 9. Padrão de referência e avaliação dos modelos

## 9.0 Dois conjuntos com papéis distintos

A distinção tem de ficar clara logo na metodologia, porque os números de um
não podem ser apresentados como resultados do outro.

### Conjunto de desenvolvimento — 64 RCM

**Critério de seleção:** a lista de 78 compostos de relevância
farmacogenómica fornecida externamente. Não é «documentos com índice PGx
elevado» medido nos textos — é uma lista de substâncias conhecidas.

```
78 compostos pedidos
 → 51 com RCM no corpus nacional        → 1 086 ficheiros
 → 1 por substância (mono-substância,
   texto mais extenso, legível)          →    51
 → acrescentados manualmente (EMA e
   Infomed sem filtro de comercialização) →   64
```

Enviesado para positivo, mas não uniformemente: **54 das 64 substâncias têm
guideline ClinPGx, 10 não têm**. 57 documentos com conteúdo PGx detetado, 46
com entidades extraídas.

**Função: encontrar e corrigir defeitos, não medir desempenho.** Um conjunto
enviesado para positivo mede mal a especificidade — quase não há negativos
onde o modelo se possa enganar.

**Defeitos que este conjunto revelou, e que foram corrigidos:**

| detetado | correção |
|---|---|
| 5 guidelines perdidas (`alopurinol` ≠ `allopurinol`) | expansão do CUI via UMLS |
| metoxiflurano com o CUI da leucina | comprimento mínimo no match parcial; prioridade ao exacto |
| abacavir com 0 secções contado como «sem PGx» | estado próprio para RCM sem estrutura |
| `CYP2C9*2*3` contado como alelo **e** diplótipo | reclassificação na origem |
| «Cobertura por gene» dizia documentos e somava posições | DPYD passa de 10 para 2 documentos reais |
| secção 4.5 dividida em 3 linhas por variação do título | agrupamento pelo número, com título canónico |
| 7 ficheiros com texto corrompido em 1 086 | validou o detetor recém-escrito |
| KRAS somático, genótipo viral do VHC, aviso de excipiente | categorias identificadas para decisão de âmbito |

Deu também as medições de escala usadas no planeamento: 20,8k tokens de
entrada e 1,02k de saída por documento, 13,5 chamadas ao modelo, 3min26 por
documento.

**Os números de cobertura deste conjunto (49,49%, 92,3% verbatim) não são
resultados.** Saíram de documentos sem anotação humana e não há contra o que
os validar. Pertencem à metodologia, como evidência de que os defeitos foram
detetados antes da avaliação.

### Padrão de referência — 17 RCM

11 de controlo positivo e 6 de controlo negativo, **anotados manualmente por
profissionais da área** (secção 9.1). É o conjunto de avaliação, e é dele que
saem sensibilidade, especificidade e fidelidade.

### Sobreposição a declarar

**8 substâncias estão nos dois conjuntos** — alopurinol, escitalopram,
fentanilo, omeprazol, risperidona, siponimod, tramadol, varfarina. Os
ficheiros são distintos (`RCM_alopurinol.pdf` não é `9522_Zyloric.pdf`), mas
a substância é a mesma.

Não invalida a avaliação: as correções foram todas gerais — um padrão de
numeração, a expansão de CUI, um limite de comprimento — e nenhuma foi
escrita para um caso concreto do padrão de referência. Mas é sobreposição
entre desenvolvimento e avaliação e deve ser declarada, não descoberta pelo
júri.

## 9.1 O que existe

`GoldenStandartSet.xlsx` — **anotação manual por profissionais da área** sobre
os 11 RCM do controlo positivo. 20 linhas: cada documento é dividido por tipo
de conteúdo, e cada linha traz o texto extraído secção a secção (4.1 a 5.2).

A classificação usada pelas anotadoras:

| tipo | linhas |
|---|---|
| Interação | 9 |
| PGx | 3 |
| Biotransformação/PGx | 4 |
| Biotransformação | 2 |
| misturada | 1 |
| Biotransformação/PGx — **não descreve gene** | 1 |

**Corroboração independente de dois achados do pipeline.** As anotadoras
distinguiram, à mão, *Interação* e *Biotransformação* de *PGx* — exactamente a
separação que o pipeline faz e que verificámos caso a caso (o CYP3A4 do
tacrolimus, o CYP2D6 da imipramina e o CYP2C9 do ibuprofeno aparecem apenas
como parceiros de interação, não como determinantes genéticos). E a linha da
isoniazida está marcada «não descreve gene», que é a categoria dos RCM que
reconhecem base genética sem nomear o gene — desflurano, isoflurano,
sevoflurano e succinilcolina, no nosso lado.

Deixa de ser observação nossa: é classificação convergente entre método
automático e revisão humana especializada.

## 9.2 Controlo negativo — a métrica de alucinação

Os 6 RCM do controlo negativo não constam do gabarito, e é correcto que não
constem: não há segmentos a extrair, e a verdade de referência é «nenhum».

**Resultado da corrida de 17/08/2026 com gpt-oss:120b:**

```
Aero-OM         0 entidades
Aldactone       0 entidades
Cetirizina      0 entidades   ← 4.4 classificada PGx=Sim
Gabapentina     0 entidades
Indapamida      0 entidades
Ácido Fólico    0 entidades
```

**Zero entidades fabricadas nos seis.** Nenhum gene, alelo, diplótipo ou rsID
inventado. É este o número a apresentar quando a pergunta for sobre alucinação.

Sem controlo negativo, a sensibilidade sozinha não distingue um bom modelo de
um que responda «sim» a tudo — esse teria sensibilidade perfeita e seria
inútil. Na tabela comparativa dos modelos, **entidades fabricadas nos
negativos** deve ser coluna própria, ao lado da sensibilidade.

## 9.3 O caso da Cetirizina

A única secção classificada positiva no controlo negativo:

> «Este medicamento contém 500 mg de sorbitol em cada ml de solução oral. Os
> doentes com intolerância hereditária à frutose...»

Não é alucinação — o texto está no RCM e é hereditário. É divergência de
**definição**, não erro de extração: o modelo aplicou um critério mais lato do
que o do estudo.

O aviso de excipiente é texto padronizado europeu e aparece em **38 dos 64**
documentos analisados. Num corpus onde a maioria dos RCM não tem
farmacogenómica, passa a ser a principal fonte de falsos positivos.

A decisão — intolerância hereditária à lactose ou à frutose conta como
farmacogenómica? — tem de ser tomada e justificada. Material directo para a
secção «Ambiguity in PGx Statements».

## 9.4 Plano de avaliação

Duas métricas de sensibilidade, porque respondem a perguntas diferentes:

| granularidade | pergunta |
|---|---|
| por secção | o pipeline encontra informação onde o gabarito diz que há? |
| por excerto | o texto extraído coincide com o que foi anotado? |

A primeira mede deteção, a segunda fidelidade da extração. Um modelo pode
acertar na primeira e falhar na segunda.

A calcular para cada modelo candidato, sobre os mesmos 17 documentos:

- **sensibilidade** (11 positivos, por secção e por excerto)
- **entidades fabricadas** (6 negativos)
- **fidelidade das citações** — verbatim / recomposto / não encontrado
- **falhas de extração** — respostas não utilizáveis
- **concordância entre execuções** — mesmo documento, duas vezes

## 9.5 O que isto responde ao feedback do protótipo

O relatório de acompanhamento (18 valores) recebeu a observação de que
*«methodological details and evaluation plans remain somewhat high-level»*.

A secção 3.4 do protótipo abria com *«Although formal quantitative metrics
(precision, recall, F1-score, accuracy) will be computed once annotation of
all documents is finalized, qualitative assessment already indicates strong
performance»*. A anotação está agora finalizada: os números prometidos podem
ser calculados.

**Uma afirmação do protótipo a verificar antes de a repetir.** O texto diz que
o sistema *«detected additional PGx-relevant statements that were not
identified during manual annotation»*. Como está, não tem prova, e um leitor
cético lê «o modelo inventou e o autor chamou-lhe descoberta».

Com o gabarito, cada extra pode ser classificado: se cai em segmentos que as
anotadoras marcaram como *Interação* ou *Biotransformação*, é divergência de
critério e não descoberta; se cai em texto que não cobriram, é achado
legítimo. A distinção tem de ser feita e mostrada.

## 9.6 Linha de base — gpt-oss:120b nos 17 (10/09/2026)

Corrida completa: 11 positivos em 1h11m, 6 negativos em 33m. Um documento
saiu incompleto (Indapamida, por investigar).

**A coluna TIPO do gabarito é o critério, não a presença do gene.** As
anotadoras classificaram cada segmento em *PGx*, *Interação* ou
*Biotransformação* — e em cinco casos escreveram combinações
(«Biotransformação/PGx», «Biotransformação/interação/PGx misturada no
texto»). Uma enzima citada apenas como via metabólica, sem variante,
genótipo ou consequência clínica, não é anotação PGx. Avaliar por presença
de símbolo de gene mede a coisa errada.

Com esse critério, sobre as entidades PGx do gabarito:

| substância | gabarito (contexto PGx) | extraído |
|---|---|---|
| Siponimod | CYP2C9 | ✔ |
| Sinvastatina | SLCO1B1 | ✔ |
| Varfarina | CYP2C9, VKORC1 | ✔ (+ CYP2C9\*2, CYP2C9\*3) |
| Escitalopram | CYP2C19, CYP2D6 | ✔ |
| Tramadol | CYP2D6 | ✔ |
| Omeprazol | CYP2C19 | ✔ |
| Alopurinol | HLA-B\*5801 | ✔ |
| Risperidona | CYP2D6 | ✔ |
| Isoniazida | — (anotado «não descreve gene») | 0 |
| Fentanilo | — (só *Interação* e *Biotransformação*) | 0 |
| Rifampicina | — (só *Interação*) | 0 |

**Sensibilidade 100%, precisão 100%, zero entidades fabricadas** nos 6
controlos negativos. O caso do Fentanilo — em que o pipeline não devolveu
nada apesar de o Excel do gabarito ter texto — resolve-se aqui: o gabarito
nunca o classificou como PGx.

**A discriminação é real e é o achado.** Na secção 5.2 da varfarina, a mesma
frase enumera CYP2C9, CYP2C19, CYP2C8, CYP1A2 e CYP3A4; o modelo extraiu
apenas CYP2C9 — a que tem alelos e consequência anticoagulante — e ignorou
as outras quatro. No tramadol, CYP3A4 aparece só sob «Inibidores CYP3A4»
(interação) e não foi extraída.

**A inconsistência a declarar.** No escitalopram, CYP3A4 foi extraída da 5.2
a partir de *«É possível que exista alguma contribuição das enzimas CYP3A4 e
CYP2D6»* — mera biotransformação, o mesmo padrão que rejeitou na varfarina.
Uma sobre-extração em 11 documentos. Não é alucinação (o texto existe e a
citação é fiel); é limiar instável na fronteira biotransformação/PGx — a
mesma fronteira que o gabarito também assinala como difusa. É este o número
que os outros dois modelos têm de bater.

**Discrepância entre granularidades.** Por secção, a mesma corrida dá
sensibilidade 80,0% e precisão 74,1%: os 5 falsos negativos são todos da
4.2, marcada como PGx por papel clínico e não por marca textual (o excerto
da 4.2 da varfarina não contém gene, alelo nem «genótipo»), e os falsos
positivos concentram-se na 4.5. A métrica por secção penaliza o pipeline por
não inferir contexto clínico que o texto não dá. **A métrica que conta é a
de entidades.**

---

# 10. Por fazer no código

- Tradução para inglês (documentação e nomenclatura); chaves JSON de saída.
- Ancoragem dos cruzamentos em identificadores químicos (ATC, MeSH) em vez de
  nomes em texto livre — elimina a classe inteira de bugs de matching.
- Log incremental (hoje só é escrito no fim do lote).
- Validação do LLM que o Jeiziner não precisou de fazer: concordância entre
  execuções, amostra anotada à mão (eles usaram 10 % reanotado + 5 % por
  segunda pessoa), sensibilidade e especificidade contra essa amostra.
  **Sem isto, a pergunta óbvia na defesa é como sabes que o modelo não
  inventou.**
