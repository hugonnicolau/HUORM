# Thesis structure — working scaffold

**Development of a Large Language Model-Based Pipeline for the Extraction of
Pharmacogenomic Information from Unstructured Data Sources**

Hugo Nicolau · MIPD, Faculdade de Ciências, Universidade de Lisboa
Submission: 30 September 2026

> **Actualizado a 15-09-2026** para corresponder exactamente ao projecto
> Overleaf (`tese_overleaf/parts/`). A estrutura anterior — Methods / Results /
> Discussion em capítulos separados — foi abandonada. O template FCUL de 2019
> organiza o trabalho em **capítulos de contribuição**, cada um com o seu
> Methods / Evaluation / Results and Discussion. É essa a estrutura daqui em
> diante.

---

> **Como usar este ficheiro.** Os títulos em inglês são os títulos reais da
> tese e correspondem 1:1 aos `\chapter{}` e `\section{}` dos ficheiros em
> `tese_overleaf/parts/`. Escreve por baixo deles. As linhas marcadas `>` são
> notas para ti: apaga-as à medida que escreves. Os blocos `[FIG n]` e
> `[TAB n]` marcam onde entra cada gráfico ou tabela, e dizem **que pergunta
> essa figura tem de responder**. Se os dados não responderem à pergunta, a
> figura sai — não se põe um gráfico só porque há números.
>
> **Normas FCUL (Anexo B) — já verificadas e aplicadas** no `main.tex`:
>
> | regra | valor |
> |---|---|
> | **Limite do texto principal** | **80 páginas** (referências e anexos ficam de fora) |
> | Corpo | 11 pt, espaçamento **1,15** |
> | Legendas e notas de rodapé | 9 pt, espaçamento **1** |
> | Margens | 2,5 cm nos quatro lados |
> | Pré-textuais | numeração **romana**, em baixo ao centro |
> | Texto principal | árabe contínua desde 1, incluindo páginas de figuras e anexos |
> | Numeração de figuras/tabelas | `capítulo.ordem` (ex. `3.16`), **duas sequências distintas** |
> | Legendas | **acima** das tabelas, **abaixo** das figuras |
> | Língua | Português **ou** Inglês — mas **Resumo obrigatório nas duas** |
>
> **O limite de 80 páginas muda a estratégia:** material pesado — a tabela
> completa de defeitos, os prompts, o esquema JSON, as anotações dos 17 — vai
> para **anexos**, que não contam. No corpo fica o argumento, com a remissão.

---

## Mapa: ficheiro Overleaf → secção deste documento

| ficheiro | conteúdo | estado |
|---|---|---|
| `01_acknowledgements.tex` | Agradecimentos | por escrever |
| `02_resumo.tex` | Resumo + palavras-chave (PT) | por escrever, **em último** |
| `03_abstract.tex` | Abstract + keywords (EN) | por escrever, **em último** |
| `04_resumo_alargado.tex` | Resumo alargado (PT) | por escrever |
| `05_contents.tex` … `07_list_of_tables.tex` | Índices | automáticos |
| `08_introduction.tex` | **Cap. 1** | escrito; falta `Contributions` |
| `09_related_work.tex` | **Cap. 2** | ~3 300 palavras em falta |
| `10_corpus.tex` | **Cap. 3** | desbloqueado, escreve já |
| `11_extraction.tex` | **Cap. 4** | parcial; espera a corrida final |
| `12_conclusion.tex` | **Cap. 5** | último |
| `13_references.tex` | Referências | `references.bib`, 14 entradas |

---

# 1. Introduction

> `08_introduction.tex` — **escrito**, ~1 170 palavras. Só falta uma secção.

## 1.1 Motivation

> Feito. Cinco parágrafos: o que é PGx e porque importa · o rótulo como
> veículo regulamentar · o exemplo do siponimod (explícito mas não legível por
> máquina) · o contraste com a isoniazida (fenótipo sem gene nomeado) · a
> conclusão da literatura e a escala nacional.

## 1.2 Objectives

> Feito. Enquadramento, as quatro alíneas do Work Plan **copiadas à letra**, e
> a hipótese explícita. Não reescrever as alíneas por outras palavras — o júri
> avalia-te contra elas.

## 1.3 Methodology

> Feito. Duas fases, mapeadas para os capítulos 3 e 4.

## 1.4 Contributions

> ⏳ **Único bloco em falta no capítulo.** Esqueleto já no ficheiro, com os
> números em comentário. Fecha-o quando a corrida final der resultados.
>
> Um parágrafo de abertura + uma subsecção por objectivo. A contribuição
> transversal a não esquecer: **a grelha de anotação PGx / Interação /
> Biotransformação**, que é o que permite distinguir um falso negativo de uma
> divergência de critério.

## 1.5 Document Structure

> Feito.

---

# 2. Related Work

> `09_related_work.tex` — **~3 300 palavras em falta** e três secções sem
> nenhuma referência. É o capítulo com mais leitura por fazer.

## 2.1 Pharmacogenomics and Clinical Implementation

> O que é PGx, o que é um consórcio de guidelines (CPIC, DPWG, RNPGx, AIOM),
> como diferem em âmbito e em força de recomendação. Necessário para o leitor
> perceber o que significa "documento com guideline" no capítulo 4.
> Referências: `osanlou2022`, `ehmann2015`.

## 2.2 Pharmacogenomic Knowledge Bases

> ClinPGx (ex-PharmGKB, renomeado a 30-07-2025 — **dizer isto**, porque a
> literatura anterior cita PharmGKB) e os níveis de evidência 1A–4. Vais usar
> os níveis nos resultados (SLCO1B1 + sinvastatina é 1A) e sem esta base o
> leitor não sabe o que isso vale.

## 2.3 Nomenclature of Pharmacogenomic Entities

**[FIG 2.1] — Hierarquia da nomenclatura PGx, com um exemplo real**

> **Pergunta que responde:** porque é que `CC` não é um rsID nem um diplótipo?
>
> Diagrama em quatro níveis, ancorado no `SLCO1B1` da sinvastatina:
>
> | nível | exemplo | o que identifica |
> |---|---|---|
> | rsID | `rs4149056` | a posição no genoma |
> | variante (HGVS) | `c.521T>C` | a alteração nessa posição |
> | genótipo | `TT` · `TC` · `CC` | as duas cópias que o doente tem |
> | haplótipo / diplótipo | `SLCO1B1*5` · `*1/*5` | variantes herdadas em conjunto |
>
> Mostrar que `*5`, `*15` e `*17` carregam todos o alelo C — logo `CC` **não
> determina** um diplótipo. Esta figura sustenta a discussão do capítulo 4 e
> evita que um revisor de farmacogenética leia o teu output como erro
> conceptual. É a figura mais barata de fazer e das que mais te protege.

## 2.4 Pharmacogenomic Information in Drug Labels

> O núcleo do capítulo e onde estão as tuas referências mais fortes.
> `jeiziner2021` é o comparador directo (Suíça, 4 306 rótulos, 28,4% → vais
> contrastar). `moschella2025` (AIFA, Itália), `shekhani2020` (só 50% dos 54
> fármacos accionáveis têm informação no rótulo; concordância entre agências
> de 18%), `tutton2014` (linguagem que manda agir vs que apenas informa),
> `ema2025conceptpaper` (a orientação europeia está a ser revista agora — a
> tua tese cai nessa janela), e `ferreira2026`, o precedente português
> limitado a fármacos do SNC.

## 2.5 Automated Extraction from Regulatory Texts

> `barone2025dart` (DART, corpus de RCM italianos — o trabalho mais próximo do
> teu capítulo 3) e `kadi2025smpc` (SmPC → IDMP com LLM e RAG). Depois as
> modalidades de falha dos LLM: alucinação, não-determinismo, sensibilidade ao
> prompt.
>
> **Se não explicares aqui porque é que a fabricação de entidades é *a*
> métrica crítica, o controlo negativo do capítulo 4 parece um detalhe.**

## 2.6 Gap Addressed by This Work

> Três eixos: nenhum levantamento nacional português automatizado; os recursos
> de NLP existentes são anglófonos ou de outro país; e os estudos de rótulos
> existentes são manuais e não escalam.

---

# 3. A National Corpus of Portuguese Summaries of Product Characteristics

> `10_corpus.tex` — **completamente desbloqueado, ~1 700 palavras.**
> Escreve este primeiro: não depende de nenhuma corrida futura e os números
> estão todos fechados desde 15-09.

## 3.1 Methods

### Source and harvesting procedure

> INFOMED, harvester próprio em Playwright, varrimento por classificações do
> portal. **Declarar quais**: das 12 dimensões disponíveis correram três —
> travessia WHO ATC (9 006 registos), Classificação Farmacoterapêutica (498) e
> Forma Farmacêutica (42).

### Inclusion criteria and scope

> **Critério de inclusão, escrito de cabeça levantada e não como desculpa:**
>
> > Only medicines in the *Comercializado* (marketed) state were included. An
> > SmPC for a product that is not on the market does not reach the point of
> > prescribing, and the object of this work is the pharmacogenomic
> > information available to prescribers for medicines that can actually be
> > dispensed in Portugal. Medicines in other commercialization or
> > marketing-authorization states fall outside this scope.
>
> **Não escrever** que foram os únicos que o scraper apanhou (falso — o
> harvester tem `--comerc`) nem que os outros estão desactualizados (não
> verificado). Ambas se desmontam com uma pergunta.
>
> Consequência a escrever com todas as letras: a ausência de uma substância
> não prova que o INFOMED não publique o RCM — prova que não há medicamento
> comercializado.

### Document usability screening

> Dois modos de falha distintos — digitalização sem camada de texto, e texto
> corrompido por fonte sem mapa de caracteres (o caso do tramadol: 41 705
> caracteres, nenhuma palavra portuguesa). E porquê o OCR foi descartado:
> texto pouco fiável gera entidades inexistentes, pior do que a ausência de
> texto.

### Deduplication

> Critério de Jeiziner: agrupar por ATC, colapsar por igualdade de texto
> depois de neutralizar datas de revisão e paginação. O representante é o
> produto de marca; na ausência, o primeiro genérico por ordem alfabética.

**[FIG 3.1] — Corpus construction flow (estilo PRISMA)**

> **Pergunta:** de quantos documentos se partiu e quantos chegaram à análise?
>
> Caixas em cascata. **Números finais, de 15-09-2026:**
>
> ```
>  9 546  medicamentos comercializados no índice
>  7 930  com RCM assinalado
>  7 924  RCM descarregados e verificados
>    -21  digitalizações / texto ilegível
>  7 903  utilizáveis
>  1 303  grupos por ATC ou substância
> -2 243  duplicados exactos, colapsados      (28,4%)
>  5 660  documentos analisados
> ```
>
> **Esta figura é obrigatória** — é o que torna todos os denominadores do
> capítulo 4 auditáveis.

## 3.2 Evaluation

> Secção curta, mas é o que distingue um corpus de uma pasta de PDF.
>
> - **Integridade:** o conjunto na pasta final bate certo com `processar.txt`
>   (5 660, nenhum a faltar nem a mais) e o sha256 confere por amostragem.
> - **Reconciliação da cascata:** cada passo tem o seu N e a soma fecha.
> - **Estabilidade entre colheitas:** contra a colheita anterior (5 622
>   representantes), 5 559 documentos em comum. As diferenças restantes são
>   quase todas o mesmo documento com o nome escrito de outra maneira — a
>   colheita antiga gravava em minúsculas, sem acentos e truncava nomes
>   longos. **Vale a pena dizer isto:** mostra que o método é estável e não
>   dependente de uma colheita em particular.

## 3.3 Results and Discussion

**[FIG 3.2] — Distribuição dos documentos por grupo farmacoterapêutico**

> **Pergunta:** que áreas terapêuticas compõem o corpus nacional?
> Barras horizontais, agrupadas por **código** e não por rótulo — o mesmo
> grupo aparece escrito de sete maneiras, e agrupar por texto dava 473 rótulos
> para 121 grupos reais. Facto que vale uma frase no texto.

**[FIG 3.3] — Deduplicação: Portugal vs Suíça**

> **Pergunta:** o método de Jeiziner transfere para o corpus português?
>
> | | Suíça (2021) | Portugal |
> |---|---|---|
> | Redução | 88,1% | **28,4%** |
> | Grupos com texto uniforme | 166/167 (99,4%) | **~9%** |
>
> Duas barras lado a lado chegam. **Isto é um resultado, não um detalhe
> metodológico** — é uma diferença entre sistemas regulatórios nacionais, e é
> original. Em Portugal cada titular redige o seu RCM; na Suíça os genéricos
> adoptam o texto do original. Dá-lhe espaço no texto.

**[TAB 3.1] — Nomenclatura presente no corpus**

> **Pergunta:** que formas de identificação genética usam os RCM portugueses?
>
> **Zero rsID em 5 660 documentos.** É um resultado de nomenclatura e
> pertence a este capítulo, não ao 4: caracteriza o corpus, não o extractor.
> Contrastar com o siponimod, cujos rsID existem — mas no Anexo II, fora do
> RCM. Ligar à FIG 2.1.

---

# 4. Extracting Pharmacogenomic Information with Large Language Models

> `11_extraction.tex` — o capítulo mais longo. Methods e Evaluation podem ser
> escritos já; Results espera a corrida final.

## 4.1 Methods

### Pipeline architecture

**[FIG 4.1] — Arquitetura do pipeline (A FIGURA PRINCIPAL DA TESE)**

> **Pergunta:** o que entra, o que sai, e em que ponto o LLM decide o quê?
>
> Três módulos do Work Plan, com o fluxo de dados entre eles:
>
> - **Module A** — PDF → docling → markdown → normalização de títulos →
>   segmentação por secção normativa
> - **Module B** — por secção: classificação PGx → extração de entidades →
>   verificação de fidelidade contra o texto de origem
> - **Module C** — enriquecimento externo (ClinPGx, UMLS, ATC) → JSON por
>   documento → agregação global
>
> Marcar visualmente **onde o LLM é chamado** e onde não é. É a distinção que
> o júri vai querer: o que é decisão do modelo e o que é lookup determinístico.
> Caminho tracejado para a propagação a duplicados exactos.

> **Desvio ao Work Plan a declarar aqui.** O plano previa PostgreSQL. A saída
> é JSON por documento + Excel agregado. Justificação honesta: com o esquema
> de entidades ainda a estabilizar, congelar um esquema relacional teria sido
> prematuro; o JSON é a forma intermédia de onde a população da base de dados
> é trivial.

### Prompt design and extraction schema

**[TAB 4.1] — Categorias de entidade extraídas**

> Genes · star alleles · diplotypes · rsIDs, com um exemplo de cada.
> **Nota a incluir:** não há categoria `genotype`, e isso tem consequência
> (ver 4.3).

### Integration of external resources

> ClinPGx (`genes.tsv`, `clinicalVariants.tsv`, `guidelineAnnotations/`),
> UMLS `MRCONSO.RRF` como ponte PT↔EN via CUI, ATC como âncora química.
> Explicar **porque é que a tradução da substância ativa é feita por modelo e
> não por dicionário** — e como o CUI do UMLS a ancora depois.

### Reproducibility controls

> `temperature=0`, `top_p=1`, `top_k=1`, `seed=42`, tag exacta do modelo.
> Dizer o que a seed é e **o que ela não garante**: com modelos MoE em cloud o
> encaminhamento entre peritos não é controlável, portanto o determinismo é
> aproximado. É esta honestidade que justifica o teste de concordância entre
> execuções.

### Software, versions and computing environment

> Versões fixadas em `requirements.txt` com a justificação já lá escrita.
> Referir a separação em duas fases — conversão local, depois extração — e
> porquê: a conversão é CPU e não escala com processos; a extração é espera de
> rede e escala. Medido a 15-09: 49,3 s por documento na conversão, débito
> local plano (73/82/81 doc/h para 1/2/4 processos).

## 4.2 Evaluation

### Reference standard

> **Distinção essencial, e a primeira coisa que um júri atento vai procurar.**
> Os 64 documentos serviram de conjunto de **desenvolvimento** — foi neles que
> os defeitos foram encontrados e corrigidos. Os 17 são o **padrão de
> referência**, anotados manualmente e revistos por profissionais. Declarar a
> sobreposição de 8 substâncias e o que isso implica.

### Annotation categories

> **Crítico e frequentemente esquecido.** O gabarito classifica cada segmento
> em *PGx*, *Interação* ou *Biotransformação* — e em cinco casos em
> combinações destas. Uma enzima citada só como via metabólica, sem variante,
> genótipo ou consequência clínica, **não é anotação PGx**.
>
> Sem esta secção, os resultados não se percebem: é este critério que
> transforma 5 "falsos negativos" em zero.

### Negative controls

> 6 RCM sem conteúdo PGx esperado. A métrica que produzem é a taxa de
> fabricação de entidades. Referir a cetirizina (sorbitol / intolerância
> hereditária à frutose) como caso-fronteira.

**[TAB 4.2] — Definição das métricas**

> | métrica | granularidade | pergunta que responde |
> |---|---|---|
> | sensibilidade | entidade | das entidades PGx anotadas, quantas extraiu? |
> | precisão | entidade | das que extraiu, quantas existem no texto? |
> | fabricação | documento | quantas entidades inexistentes inventou? |
> | fidelidade | excerto | o excerto é verbatim, recomposto ou não encontrado? |
> | concordância | execução | o mesmo documento duas vezes dá o mesmo? |
>
> **Justificar porque a métrica principal é por entidade e não por secção.**
> A métrica por secção penaliza o pipeline por não inferir contexto clínico
> que o texto não dá — a 4.2 da varfarina está anotada como PGx por papel
> clínico e o excerto não contém gene, alelo nem a palavra "genótipo".
> Apresenta as duas, mas diz qual conta e porquê.

**[TAB 4.3] — Modelos avaliados**

> Tag exacta, parâmetros, custo por 10 000 documentos, e **a justificação da
> exclusão do Qwen**. O DeepSeek é o mais caro ($75 vs $26/10k) e o de pior
> recall.

## 4.3 Results and Discussion

**[TAB 4.4] — Defeitos encontrados no desenvolvimento**

> **Pergunta:** quanto é que cada defeito custava, em documentos?
>
> Uma linha por defeito: descrição · como foi detectado · impacto medido ·
> correção · teste de regressão. Material em `NOTAS_DE_ALTERACOES.md`:
>
> - classificação PGx por correspondência parcial ("sim" como substring)
> - código do grupo farmacoterapêutico truncado no primeiro nível
> - secções perdidas por numeração com pontuação espaçada
> - referências cruzadas promovidas a título
> - texto corrompido reportado como processado
> - número de secção duplicado pela conversão (indapamida)
>
> **É este bloco que distingue uma tese de engenharia de um relatório de
> utilização de ferramenta.** Cada linha é trabalho teu, mensurável. Não o
> enterres num anexo.

**[FIG 4.2] — Um defeito ilustrado: a secção 2 perdida na conversão**

> **Pergunta:** como é que um espaço em falta apaga a substância ativa?
>
> Três painéis: (a) o PDF original — `2.COMPOSIÇÃO` sem espaço, contra
> `1. NOME` e `3. FORMA` com espaço; (b) o markdown do docling —
> `2. 2.COMPOSIÇÃO`; (c) a leitura resultante — secção `2.2`, secção 2
> inexistente, substância ativa perdida.
>
> Vale a figura porque o diagnóstico veio da comparação de modelos: os três
> falharam identicamente, o que provou que a causa era anterior à chamada ao
> LLM. Argumento a favor de correr mais do que um modelo mesmo quando só um
> vai ser usado.

**[FIG 4.3] — Precisão e sensibilidade por modelo**

> **Pergunta:** qual dos três modelos extrai melhor?
> Barras agrupadas, 3 modelos × 2 métricas. Linha de referência a 100%.

**[TAB 4.5] — Concordância entidade a entidade entre modelos**

> **Pergunta:** onde é que os modelos discordam, e porquê?
>
> - o **GLM omite CYP3A4** no escitalopram, omeprazol e siponimod — sempre
>   onde a enzima só aparece como via metabólica. É o único que aplica o
>   critério de forma consistente.
> - só o **GLM apanhou os genótipos da sinvastatina** (CC/TC/TT — risco de
>   miopatia 15% / 1,5% / 0,3% com 80 mg). A frase mais accionável do RCM,
>   perdida pelos outros dois.
> - o **DeepSeek perdeu 4 dos 5 alelos CYP2C9** do siponimod. Falha de recall
>   numa tabela, e é o modelo mais caro.

**[TAB 4.6] — Controlos negativos**

> **Pergunta:** algum modelo inventou entidades?
> 6 documentos × 3 modelos. Resultado: 0 genes, 0 alelos, 0 menções em todos.
> **Uma tabela de zeros é um resultado forte** — apresenta-a como tal.

**[FIG 4.4] — Tempo de execução e custo por modelo**

> **Pergunta:** o melhor modelo é comportável no corpus completo?
> Tempo médio por documento × custo projectado para 5 660 documentos.

**[FIG 4.5] — Concordância entre execuções**

> **Pergunta:** o mesmo documento, duas vezes, dá o mesmo?
> Valida empiricamente os controlos de reprodutibilidade de 4.1.

> ⏳ **As figuras seguintes dependem da corrida final.**

**[FIG 4.6] — Prevalência de conteúdo PGx no corpus**

> **Pergunta:** que fração dos RCM portugueses menciona farmacogenómica?
> O número-título da tese. Merece figura própria e destaque.

**[FIG 4.7] — Genes e entidades mais frequentes**

> **Pergunta:** que genes dominam o panorama nacional? Top 20, barras
> horizontais.

**[FIG 4.8] — Distribuição por secção normativa**

> **Pergunta:** onde é que a informação PGx vive dentro do RCM?
> 4.2 · 4.3 · 4.4 · 4.5 · 4.8 · 5.1 · 5.2, barras empilhadas. Implicação
> prática directa: se a informação está sobretudo na 5.2, o prescritor que lê
> só a 4.2 não a vê.

**[FIG 4.9] — Cobertura de guidelines: esperado vs observado**

> **Pergunta:** que fração das recomendações publicadas chegou ao rótulo?
>
> **Distinguir as duas métricas com clareza** — foi fonte de confusão e vai
> voltar a ser para o leitor:
> - **genes com guideline cobertos** (posições gene-documento)
> - **pares fármaco-gene distintos cobertos**
>
> No conjunto de validação: 67,57% e 45,45%. São coisas diferentes e a legenda
> tem de o dizer.

**[FIG 4.10] — Cobertura por classe de gene**

> **Pergunta:** que tipo de gene é que o rótulo menciona, e qual é que omite?
>
> **Este é o achado principal da tese.** O padrão já medido:
>
> | mencionados sempre | nunca mencionados |
> |---|---|
> | CYP2C9 5/5 · CYP2D6 4/4 · HLA-B 4/4 · VKORC1 4/4 · SLCO1B1 3/3 | OPRM1 0/2 · ABCG2 0/2 · HTR2A 0/1 · SLC6A4 0/1 |
>
> **Os genes de metabolização são sempre mencionados; os de resposta e
> transporte, nunca.** A varfarina menciona CYP2C9 e VKORC1 e omite CYP4F2; o
> escitalopram menciona CYP2C19 e CYP2D6 e omite HTR2A e SLC6A4.
>
> Isto não é uma limitação do pipeline — é uma **lacuna sistemática dos
> rótulos**, e é o resultado com maior valor clínico da tese.

### Discussion

> Fecha o capítulo com três blocos, não com uma lista:
>
> **Comparação com trabalho anterior.** O que replicaste de `jeiziner2021`, o
> que não transferiu (deduplicação) e o que acrescentaste — a validação do
> LLM, que eles não precisaram de fazer porque não usaram um.
>
> **Onde o modelo acerta e onde é inconsistente.** *A secção mais honesta da
> tese, e a que mais credibilidade te dá.* Discrimina: na 5.2 da varfarina a
> mesma frase enumera CYP2C9, CYP2C19, CYP2C8, CYP1A2 e CYP3A4, e o modelo
> extraiu só CYP2C9 — a que tem alelos e consequência anticoagulante. Mas não
> sempre: no escitalopram extraiu CYP3A4 de «É possível que exista alguma
> contribuição das enzimas CYP3A4 e CYP2D6» — mera biotransformação, o mesmo
> padrão que rejeitou na varfarina. Não é alucinação (o texto existe, a
> citação é fiel); é **limiar instável na fronteira
> biotransformação/PGx** — a mesma fronteira que o gabarito assinala como
> difusa. E o esquema tem uma lacuna: `CC`/`TC`/`TT` são genótipos em
> rs4149056, arrumados em `diplotypes` porque não existe categoria `genotype`.
> Ligar à FIG 2.1.
>
> **Limitações.** Âmbito comercializado-apenas · corpus nacional sem os RCM da
> EMA (1 732 medicamentos de autorização centralizada) · determinismo
> aproximado em cloud MoE · padrão de referência de 17 documentos · ausência
> de classificação do tipo de recomendação.

---

# 5. Conclusion

> `12_conclusion.tex`. Uma a duas páginas. Sem números novos, sem citações
> novas.

> **Incluir a tabela de desvios ao Work Plan.** Secção curta e explícita —
> escreve-a, não esperes que ninguém repare:
>
> | previsto no Work Plan | executado | justificação |
> |---|---|---|
> | PostgreSQL (Module C) | JSON + Excel | esquema de entidades ainda a estabilizar |
> | INFOMED **e** EMA | INFOMED apenas | âmbito nacional; EMA como trabalho futuro |
> | pipeline em LangChain | um componente (`MarkdownHeaderTextSplitter`) | a orquestração não foi necessária |
> | «recommendation types» | não implementado | trabalho futuro |
>
> Um trabalho que executa o plano à letra é suspeito. Um que se desvia e
> justifica cada desvio com medições é mais forte. Mas o desvio tem de estar
> escrito.

> **Implicações práticas**, em poucas linhas: para prescritores, farmacêuticos,
> INFARMED, e para quem construa apoio à decisão.

## 5.1 Future Work

> PostgreSQL e API de consulta · RCM da EMA · classificação do tipo de
> recomendação · categoria `genotype` e ponte HGVS→rsID · equivalências de
> metabolitos (63 pares por decidir) · anotação somática/viral · colheita das
> restantes dimensões do INFOMED (não comercializados, outros estados de AIM).

---

# References

> `13_references.tex` + `references.bib`. 14 entradas verificadas — as que
> têm PDF foram lidas do próprio artigo, as restantes confirmadas na fonte.
> **Não usar o reference map como fonte**: tinha erros de autores, revista e
> paginação em quatro entradas.

# Appendices

- **A** — Lista das 78 substâncias de interesse farmacogenómico e estado no corpus
- **B** — Prompts (versão exacta usada em produção)
- **C** — Esquema JSON da saída
- **D** — Padrão de referência: os 17 documentos e as suas anotações
- **E** — Suite de testes de regressão (174 testes)
- **F** — Relatório de deduplicação (`_preflight_final/relatorio.md`)

---

# Ordem de escrita sugerida

> Pela dependência dos dados, não pela ordem dos capítulos:
>
> | # | o quê | ficheiro | depende da corrida final? |
> |---|---|---|---|
> | 1 | **Cap. 3 inteiro** | `10_corpus.tex` | não — escreve já |
> | 2 | **4.1 + 4.2** (Methods, Evaluation) | `11_extraction.tex` | não |
> | 3 | **Cap. 2** | `09_related_work.tex` | não — mas exige leitura nova |
> | 4 | **4.3 até à FIG 4.5** | `11_extraction.tex` | não (3 modelos, quase fechado) |
> | 5 | **1.4 Contributions** | `08_introduction.tex` | parcialmente |
> | 6 | **4.3 da FIG 4.6 em diante** | `11_extraction.tex` | **sim** |
> | 7 | **Cap. 5** | `12_conclusion.tex` | parcialmente |
> | 8 | **Resumo + Abstract + Resumo alargado** | `02`–`04` | sim |
>
> Se a corrida final escorregar, tens ~70% da tese escrita e o capítulo 4
> reduz-se ao conjunto de validação. Continua a ser uma tese defensável: passa
> a ser sobre **construção e validação do método**, com o panorama nacional
> como demonstração parcial.
