# Pipeline RCM — notas de alterações

Agosto de 2026 · versão 2.0.0

Resumo do trabalho de revisão do pipeline de extração de informação
farmacogenómica dos RCM, e da preparação do corpus nacional completo.

---

## 1. Correções de comportamento

Sete erros que afetavam os resultados. Todos foram reproduzidos com dados
reais antes de serem corrigidos, e cada um tem agora um teste automático que
falha se voltar a acontecer.

### 1.1 Classificação de conteúdo PGx por correspondência parcial

A verificação da resposta do modelo era `"sim" in resposta`. Como é uma
procura por subcadeia, dava positivo dentro de palavras como **sim**plesmente,
as**sim**, **sim**ilar e **sim**ultaneamente — todas frequentes numa resposta
negativa.

> *"Não. O texto refere-se **sim**plesmente ao metabolismo hepático."*
> classificado como **contendo** informação farmacogenómica.

Em seis respostas de teste, quatro eram falsos positivos. Cada um arrastava um
bloco de 6 000 caracteres para a extração e para a contagem de entidades.

### 1.2 Extração não reprodutível

As chamadas ao modelo não definiam a temperatura, pelo que usavam o valor por
omissão (0,8). Duas execuções sobre o mesmo RCM produziam contagens
diferentes.

Fixado em `temperature=0`, `top_p=1`, `top_k=1`, `seed=42`. A configuração
passa a ser gravada em cada documento processado, e a análise global assinala
se o corpus tiver sido produzido com configurações diferentes.

**Para a secção de reprodutibilidade da tese.** São três garantias
sobrepostas, com papéis distintos:

| parâmetro | valor | o que faz |
|---|---|---|
| `temperature` | 0,0 | não achata a distribuição; escolhe sempre o token mais provável |
| `top_k` | 1 | só considera **um** candidato por passo — é a garantia mais forte, porque com um só candidato não há nada a sortear |
| `seed` | 42 | fixa o gerador pseudo-aleatório, caso sobre alguma aleatoriedade |

**O que isto não garante, e convém não sobreafirmar.** Temperatura zero e
seed fixa não asseguram saída idêntica em modelos servidos na nuvem. Modelos
de mistura de peritos (MoE) encaminham tokens por peritos diferentes conforme
o agrupamento de pedidos no servidor, e o hardware pode variar entre chamadas.
É uma limitação conhecida e fora do controlo de quem usa a API.

A afirmação defensável é, portanto, **empírica e não teórica**: correr o mesmo
documento duas vezes e demonstrar que o resultado coincide. Está por fazer, e
deve ser feito para cada modelo candidato — 3 documentos por modelo chegam. Se
divergirem, isso é também resultado: mostra que a reprodutibilidade em
serviços de inferência na nuvem não pode ser dada como adquirida, o que é
relevante para qualquer estudo que use estes modelos como instrumento de
medição.

### 1.3 Contagem inflacionada de alelos

A contagem de menções era feita por subcadeia, sem fronteiras de palavra.
`CYP2D6*1` é o prefixo de `CYP2D6*10`, `*17` e `*100`:

| Texto | Menções reais | Contadas |
|---|---|---|
| `CYP2D6*10, CYP2D6*17, CYP2D6*1, CYP2D6*100` | 1 de `*1` | **4** |

O erro atingia precisamente as entidades mais frequentes, já que `*1` é o
alelo selvagem e `*10`/`*17` estão entre os mais comuns nos RCM.

### 1.4 Genes nunca associados a guidelines

No ficheiro `Document_Unique_PGx.json`, os blocos de alelos, diplótipos e
rsID incluíam os identificadores das guidelines. O bloco dos genes não os
incluía. Como a análise global determina a existência de guideline a partir
desse ficheiro, **nenhum gene era alguma vez associado a uma guideline**.

Medido no corpus de 643 RCM da fase anterior:

```
222 de 222 linhas de gene  →  "sem informação ClinPGx"
Menções de genes com guideline  →  sempre 0
```

Isto apesar de o CYP2D6 aparecer em 42 documentos com 157 menções.

### 1.5 Definição de guideline

Um documento era contabilizado como "tendo guideline" quando o **nome da
substância ativa** correspondia a um registo do ClinPGx — independentemente de
o RCM mencionar o gene relevante. No corpus anterior, 49 dos 135 documentos
assim contabilizados (36%) não tinham qualquer conteúdo farmacogenómico.

Passou a exigir-se o par fármaco–gene, conforme a definição do CPIC e do DPWG:
uma guideline só se aplica quando a substância **e** o gene estão ambos
presentes no documento.

Ficou explicitamente separado o que não é guideline:

| Fonte | Significado |
|---|---|
| `genes.tsv` | o gene é farmacogeneticamente relevante em abstrato |
| `clinicalVariants.tsv` | existe evidência de variante clínica |
| `guidelineAnnotations` | **existe guideline para este par fármaco–gene** |

Os dois primeiros deixaram de contar como guideline, e passam a ser
reportados em colunas próprias.

### 1.6 Segmentação do texto a meio de frase

O texto era dividido em blocos de 6 000 caracteres por corte direto
(`texto[i:i+6000]`), sem atenção ao conteúdo. Uma afirmação farmacogenómica
que atravessasse a fronteira era separada em duas metades, e cada uma seguia
para o modelo sem o contexto da outra.

A segmentação passa a respeitar parágrafos e, quando necessário, frases. Num
teste com texto real, o método anterior partia 3 dos 4 blocos a meio de frase;
o novo não parte nenhum. Verificou-se que nada se perde nem se duplica.

### 1.7 Respostas do modelo tratadas como texto do RCM

Quando a resposta do modelo não era JSON válido, o pipeline guardava o texto
bruto da resposta no campo `texto_original` — um campo cujo conteúdo deve ser,
por definição, uma citação literal do RCM. As duas coisas ficavam
indistinguíveis no ficheiro de saída.

As falhas de extração passaram a ser registadas à parte, com o motivo e a
resposta em bruto.

### 1.8 Código do grupo farmacoterapêutico truncado no primeiro nível

O grupo farmacoterapêutico do Infarmed é hierárquico (`4.1.2` = Sangue →
Antianémicos → anemias megaloblásticas). O agrupamento da análise usa o
**código**, não o rótulo textual: o mesmo grupo aparece escrito de sete
maneiras diferentes ao longo do corpus, e agrupar por texto dava 473 rótulos
distintos para 121 grupos reais.

Em alguns PDF a conversão devolve o código com espaços a rodear os pontos —
`4 . 1 . 2`. O padrão que o lê está ancorado em dígitos consecutivos, pelo que
parava no primeiro: o RCM do Ácido Fólico era arquivado em `4` (Sangue, o topo
da hierarquia) em vez de `4.1.2`. Um documento com um espaço a mais deixava de
ser contado no grupo a que pertence.

O código passa a ser compactado na extração, e não depois. A distinção
importa: o agrupamento acontece dentro da análise, antes de chegar ao Excel —
corrigir a folha já feita não volta a juntar linhas que foram agregadas
separadas.

Medido nos 71 documentos disponíveis: 1 caso (1,4%), o que projeta cerca de
110 nos 7 800 do corpus. O mesmo passo limpa o espaçamento em torno da
pontuação do rótulo (`Aparelho Digestivo . Antiácidos`), que é cosmético mas
poupa a limpeza manual das folhas. Verificado documento a documento: dos 71,
69 ficam byte a byte iguais e os 2 alterados são exatamente os pretendidos.

O valor tal como aparece no PDF continua preservado em `md/normalizado.md`.

---

### 1.9 Número de secção duplicado pela conversão — secção 2 perdida

O RCM do Fludex (indapamida, aprovado pelo INFARMED em 28-01-2022) imprime o
título da secção 2 **sem espaço a seguir ao ponto**:

```
1. NOME DO MEDICAMENTO          ← com espaço
2.COMPOSIÇÃO QUALITATIVA E QUANTITATIVA   ← sem
3. FORMA FARMACÊUTICA           ← com espaço
```

O Docling trata os títulos de topo como lista ordenada e acrescenta o seu
próprio marcador. Onde o número já lá estava colado ao texto, o resultado é
`2. 2.COMPOSIÇÃO`, que a compactação de numeração lia como `2.2`. A secção 2
deixava de existir — e é dela que sai a **substância ativa**, que ancora o
ATC, o MeSH, o CUI do UMLS e o cruzamento com o ClinPGx. O documento
terminava com estado `Incompleto — substância ativa não identificada`.

**O diagnóstico veio da comparação de modelos.** O mesmo documento saiu
incompleto exatamente da mesma maneira no gpt-oss:120b, no glm-5.3-flash e no
deepseek-v4-flash. Um defeito partilhado pelos três não é do modelo; é de um
passo anterior à chamada. É um argumento a favor de correr mais do que um
modelo mesmo quando só um vai ser usado.

A correção colapsa um número repetido de forma idêntica no início da linha, e
nunca quando lhe segue um dígito — `5. 5.2 Propriedades` e `2. 2,5 mg`
mantêm-se intactos. Três testes de regressão em `test_section_fallback.py`.

Frequência: 1 em 186 `raw.md` já produzidos. Raro, mas silencioso — o
documento não falha, devolve-se sem substância ativa.

---

## 2. Verificação de fidelidade das citações

O prompt proíbe reformular, resumir e traduzir os excertos. Passou a
verificar-se se essa instrução é cumprida, em vez de se assumir que sim: cada
excerto é confrontado com o texto de origem.

Três estados:

| Estado | Significado |
|---|---|
| **verbatim** | cópia contígua e literal |
| **recomposto** | o conteúdo existe no documento, mas em partes não contíguas |
| **não encontrado** | contém texto inexistente — indício de reformulação |

Resultado no subconjunto de 17 RCM: **37 verbatim, 2 recompostos, 0 não
encontrados.** Nenhuma extração continha texto que não constasse do documento.

Os dois casos recompostos correspondem a tabelas que a conversão do PDF emitiu
fora da ordem de leitura; o texto é real, apenas não contíguo.

Esta métrica é relevante para a validação metodológica: permite afirmar, com
número, que os excertos citados são texto do RCM — o que compensa parte da
diferença face a métodos determinísticos como o de Jeiziner et al. (2021).

---

## 3. Tabelas passaram a ser analisadas

As tabelas eram detetadas, retiradas do texto da secção e guardadas num campo
próprio — que o avaliador nunca lia. Eram, na prática, descartadas.

Medição no subconjunto de 17 documentos: das 497 linhas de tabela presentes no
markdown, 10 continham termos farmacogenómicos. Nove eram do siponimod:

```
Tabela: Efeito do genótipo CYP2C9 na depuração sistémica e exposição

| CYP2C9*1*1 | 62-65   | 3,1-3,3 | 100    |     metabolizadores extensos
| CYP2C9*1*2 | 20-24   | 3,1-3,3 | 99-100 |
| CYP2C9*2*2 | 1-2     | 2,5-2,6 | 80     |     intermédios
| CYP2C9*1*3 | 9-12    | 1,9-2,1 | 62-65  |
| CYP2C9*2*3 | 1,4-1,7 | 1,6-1,8 | 52-55  |     lentos
| CYP2C9*3*3 | 0,3-0,4 | 0,9     | 26     |
```

Seis diplótipos, com frequências populacionais e impacto na exposição — o
núcleo farmacogenómico de um fármaco que exige genotipagem antes da
prescrição. Nenhum chegava ao modelo.

As tabelas passam a ser avaliadas como unidades próprias, a seguir ao texto
corrido, com a legenda anexada para dar contexto. Cada excerto regista a sua
origem, e a análise global ganhou uma folha com a repartição entre texto e
tabelas, incluindo as entidades que existem **apenas** em tabelas.

---

## 4. Cobertura de guidelines

Métrica nova. Para cada documento cuja substância ativa tem guideline, é agora
possível saber que genes essa guideline exige e quais deles o RCM menciona:

- **coberta** — o RCM menciona todos os genes da guideline
- **parcial** — menciona alguns (aplicável às 27 guidelines multigénicas de 217)
- **ausente** — não menciona nenhum

Os genes implícitos nos alelos contam: um RCM que escreve `CYP2D6*4` está a
referenciar o CYP2D6, ainda que nunca escreva o símbolo isolado.

Resultado no controlo positivo (11 RCM de fármacos com farmacogenética
estabelecida):

| Gene | Cobertura | | Gene | Cobertura |
|---|---|---|---|---|
| CYP2C19 | 7/7 (100%) | | COMT | 0/2 (0%) |
| CYP2C9 | 5/5 (100%) | | OPRM1 | 0/2 (0%) |
| CYP2D6 | 4/4 (100%) | | ABCG2 | 0/2 (0%) |
| HLA-B | 4/4 (100%) | | HTR2A | 0/1 (0%) |
| VKORC1 | 4/4 (100%) | | SLC6A4 | 0/1 (0%) |
| SLCO1B1 | 3/3 (100%) | | CYP3A4 | 0/1 (0%) |

O padrão é nítido: **os genes de metabolização são sempre mencionados; os de
resposta e transporte, nunca.** A varfarina menciona CYP2C9 e VKORC1 mas omite
CYP4F2; o escitalopram menciona CYP2C19 e CYP2D6 mas omite HTR2A e SLC6A4.

---

## 5. Validação com controlos positivo e negativo

Foram construídos dois subconjuntos e calculado previamente, a partir do
ClinPGx, o resultado esperado para cada fármaco.

**Controlo negativo (6 RCM):** 0 com PGx, 0 com guideline, 0 entidades, 0
falhas. Sem falsos positivos.

**Controlo positivo (11 RCM):** 10 com PGx, 8 com par fármaco–gene.

Duas observações do gabarito que corrigem o desenho dos controlos:

- A **isoniazida** e a **rifampicina** não têm guideline no ClinPGx. Têm
  variantes clínicas (NAT2, CYP2B6, GSTM1 e outras), o que é um nível de
  evidência distinto. O pipeline distinguiu-os corretamente.
- O **ácido fólico**, incluído como controlo negativo, **tem** guideline
  (DPWG, MTHFR). O RCM não menciona o gene, pelo que o pipeline o classificou
  como sem par fármaco–gene — comportamento correto.

---

## 6. Corpus nacional

O corpus foi recolhido do Infomed com um scraper próprio, por varrimento das
classificações do portal.

```
10 426   medicamentos comercializados (contador oficial do portal)
 9 538   capturados                                        (91,5%)
 1 661   substâncias ativas distintas de 1 692             (98,2%)
 7 818   com RCM publicado no Infomed
 7 808   descarregados e verificados                       (99,9%)
15 654   ficheiros PDF (RCM + folhetos informativos), 100% íntegros
```

**Nota importante para o desenho do estudo:** só 7 818 dos 9 538 medicamentos
têm RCM publicado no Infomed. Os 1 720 restantes são, na sua maioria,
medicamentos de autorização centralizada europeia (969), cujo RCM está no sítio
da EMA, importação paralela (65) e aprovações nacionais antigas (686).

O corpus de trabalho é, portanto, de **~7 800 RCM** e não de 10 400.

### Âmbito do corpus: só medicamentos comercializados

Verificação sobre `medicamentos.csv`: os **9 538 registos são, sem excepção,
`Autorizado` + `Comercializado`**. Não há um único `Caducado`, `Revogado`,
`Suspenso`, `Não Comercializado` ou `Temporariamente indisponível`.

A recolha corresponde, portanto, ao portal do Infomed com a caixa *«Apenas
medicamentos autorizados e comercializados»* activa — o que é também o
benchmark que o relatório de auditoria usa para calcular a cobertura
(«Marketed Medicines: 10 426»). Os 91,5% são sobre o subconjunto
comercializado, não sobre o universo com AIM.

O relatório afirma ter varrido as dimensões *Estado da AIM* e *Estado de
Comercialização*, mas os tempos desmentem-no: 12 s para 4 categorias e 5 s
para 3, com 0 medicamentos novos. Classifica-as como «100% redundant with
above», o que é uma leitura incorrecta — redundância implicaria que os
registos já tinham sido apanhados, e nenhum registo do corpus tem esses
estados. Uma consulta a «Não Comercializado» que devolve zero é resultado
vazio, não redundância.

**Consequência para a tese.** O âmbito tem de ser declarado como
*medicamentos autorizados e comercializados em Portugal*, não *todos os
medicamentos com AIM*. E a ausência de uma substância do corpus não demonstra
que o Infomed não publique o seu RCM: demonstra que não tem medicamento
comercializado. Para 20 das 78 substâncias de interesse farmacogenómico
— sobretudo anestésicos inalatórios antigos (halotano, enflurano, isoflurano,
metoxiflurano) e fármacos como dapsona, tioguanina e ribavirina — esta
distinção decide se são uma lacuna do corpus ou uma lacuna do país.

### Digitalizações e texto corrompido

Foram identificados os documentos sem camada de texto, para serem excluídos da
análise em vez de contribuírem silenciosamente com zeros. O OCR foi
considerado e descartado — texto pouco fiável produz entidades inexistentes,
o que é pior do que a ausência de texto.

**4 documentos em 7 836 (0,05%).**

Existe um segundo modo de falha, que a contagem de caracteres não apanha.
Alguns PDF trazem camada de texto cuja fonte não tem mapa de caracteres
utilizável: a extração devolve os códigos dos glifos em vez de letras. O
documento parece saudável — o `tramadol_oral` dá 41 705 caracteres — mas o
texto é ilegível, não gera secção nenhuma, e era reportado como processado.

Dois indicadores separam os dois casos de forma inequívoca nos 71 documentos
disponíveis:

| | palavras PT / 1000 car. | letras | car. de controlo |
|---|---|---|---|
| `tramadol_oral` | 0,00 | 15% | 34% |
| os outros 70 | 9,25 – 21,99 | 50 – 78% | 0% |

O intervalo entre os dois grupos é largo, pelo que os limiares não são
ajustados ao caso: estão colocados do lado seguro, para que um documento
duvidoso seja inspecionado e não descartado.

Consequências práticas:

- o pré-voo exclui estes documentos antes de chegarem ao modelo, poupando
  ~1min42 por documento que devolveria zero;
- a análise global deixa de os contar nos denominadores e passa a nomeá-los
  numa linha própria do resumo, para que a exclusão seja auditável e não
  silenciosa;
- o estado é `corrupt`, distinto de `scanned`, para não confundir na tese
  quantos documentos o corpus perde por cada causa.

### Deduplicação

Aplicou-se o critério de Jeiziner et al. (2021): agrupar por código ATC e
colapsar por igualdade de texto.

| | Suíça (2021) | Portugal |
|---|---|---|
| Redução | 88,1% | **28,1%** |
| Grupos com texto uniforme | 166/167 (99,4%) | **73/822 (8,9%)** |

**O método não transfere.** Investigaram-se três hipóteses:

1. **Marca comercial** — neutralizaram-se nome, titular, dosagens e datas. A
   redução não melhorou (piorou marginalmente).
2. **Forma farmacêutica** — agrupar por ATC + forma subiu a uniformidade de 8%
   para 11%. Marginal.
3. **Semelhança real** — medida por 5-gramas em 153 pares: mediana de **0,576**,
   e apenas 12% dos pares acima de 0,99.

Ou seja, os RCM portugueses de genéricos do mesmo ATC são **documentos
genuinamente diferentes**, ao contrário dos rótulos suíços, em que os genéricos
adotam o texto do original. É uma diferença regulamentar entre países, e
constitui um resultado em si.

Relendo o artigo, os autores compararam *"the PGx-relevant sentences"* — as
frases farmacogenómicas, não o documento integral. A deduplicação equivalente
terá de ser feita **depois** da extração, sobre o conteúdo PGx.

---

## 7. Seleção do modelo

O pipeline é agnóstico quanto ao modelo: a flag `--model` percorre a cadeia
toda (`batch_processor` → `RCMProcessor` → `PharmacogenomicsEvaluator` →
chamada à API) e existe uma só invocação do modelo em todo o código. O modelo
usado fica gravado em `pipeline.llm.model` de cada documento processado.

### Candidatos e nomes exactos

Todos servidos pelo Ollama Cloud, para que a comparação corra no mesmo
ambiente e sob a mesma latência:

| modelo | identificador usado | $/M in | $/M out | 10 000 docs |
|---|---|---|---|---|
| GPT-OSS 120B (referência) | `gpt-oss:120b` | 0,15 | 0,60 | ~$27 |
| GLM 5.3 Flash | `glm-5.3-flash:cloud` | 0,15 | 0,50 | **~$26** |
| DeepSeek V4 Flash | `deepseek-v4-flash:0731-cloud` | 0,44 | 1,32 | ~$75 |

O custo estimado assume 20,8k tokens de entrada e 1,02k de saída por
documento, medidos sobre os 64 RCM já processados. **O DeepSeek V4 Flash é o
mais caro dos três candidatos**, cerca de três vezes o GLM: é o único que não
cabe nos créditos mensais do plano Pro para o corpus completo. A designação
«Flash» refere-se à eficiência arquitetural do modelo, não ao preço praticado
pelo serviço.

Usa-se a etiqueta com data (`0731-cloud`) em vez de `:cloud` sempre que
exista. As duas apontam hoje para o mesmo digest, mas `:cloud` pode ser
reapontada para uma versão posterior sem aviso, e nesse caso deixaria de se
saber o que foi efectivamente executado.

### Excluído: Qwen 3.8 Flash Next

**Motivo: indisponibilidade, não desempenho.** O `qwen3.8-flash-next` não é
servido na nuvem do Ollama. As seis variantes publicadas são todas de pesos
locais, entre **105 GB e 360 GB**, o que excede largamente o hardware
disponível para este trabalho.

A exclusão é por constrangimento de infraestrutura e deve ser declarada como
tal: **não houve avaliação do modelo, e nada se pode concluir sobre a sua
adequação à tarefa.** Um leitor que disponha de hardware adequado pode
repetir a comparação incluindo-o.

O mesmo se aplica ao `qwen3.8` (27B), igualmente sem etiqueta *cloud*.

Da família Qwen, apenas o `qwen3.5:397b` é servido na nuvem. **Não foi
incluído por ser de geração anterior à dos restantes candidatos, e a
comparação seria desigual**: atribuir a um modelo mais antigo um desempenho
inferior nada diz sobre a família, apenas sobre a data. Um estudo que compare
modelos como instrumentos de medição tem de os comparar em pé de igualdade —
todos na geração corrente, todos servidos no mesmo ambiente, todos com o mesmo
pipeline e os mesmos parâmetros.

Substituir o Qwen 3.8 por uma versão anterior daria a aparência de cobertura
das três famílias sem a substância: o resultado seria interpretado como
«a família Qwen tem pior desempenho» quando na realidade mediria a diferença
entre gerações. Prefere-se declarar a ausência.

### Parâmetro não controlado

O GLM-5.3-Flash tem raciocínio sempre activo, com esforço configurável
(*low*, *high*, *max*). O pipeline não expõe esse parâmetro, pelo que a
corrida decorre no valor por omissão do serviço. É uma variável não
controlada na comparação e deve constar das limitações.

---

## 8. Removido

- **Segunda passagem ao modelo.** Havia uma chamada de classificação
  (Sim/Não) antes da extração. Era redundante — o prompt de extração já
  devolve lista vazia quando não há conteúdo — e as duas passagens podiam
  discordar entre si. Reduz o custo a metade: de ~374 000 para ~187 000
  chamadas no corpus completo. Reversível por configuração.
- **Fallback que guardava o bloco inteiro** como excerto quando a extração
  falhava, inflacionando as contagens com texto não validado.
- **Ficheiros sem uso:** `pgx_ner.py` (código morto),
  `repair_document_unique_pgx.py` (ferramenta pontual).
- **Dependências obsoletas:** `merpy`, `ssmpy`, `opencv-python-headless`.

---

## 9. Testes

**153 testes automáticos**, sem necessidade de rede, modelo ou dados
completos. Correm em segundos.

```
python RCMprocessor/tests/run_all.py
```

Cada teste codifica um caso real observado no corpus — as sete grafias de
"grupo farmacoterapêutico" encontradas nos PDF, os pares de fármacos com nomes
sobrepostos que geravam falsos cruzamentos, a tabela CYP2C9 do siponimod.

---

## 10. Por fazer

Lista canónica. Actualizar aqui em vez de a manter dispersa.

### Decisões de desenho do estudo — não são técnicas

**Metabolitos e derivados nos cruzamentos** (`review_substance_equivalences.csv`,
63 pares). Quando o RCM do naproxeno fala de **desmetilnaproxeno**, isso conta
como o rótulo mencionar uma entidade com guideline do naproxeno?
Farmacologicamente é o mesmo percurso metabólico; para efeitos regulamentares
são substâncias distintas. Os casos com mais peso:

| substância | apanhava | RCMs |
|---|---|---|
| hidroclorotiazida | clorotiazida | 22 |
| etinilestradiol | estradiol | 21 |
| escitalopram | citalopram | 3 |
| esomeprazol | omeprazol | 3 |
| naproxeno | desmetilnaproxeno | 3 |

A coluna `decisao` do CSV está vazia e **enquanto estiver, nenhum destes
cruzamentos é feito** — o comportamento actual é o conservador. Nem o estudo
suíço nem o italiano abordam a questão, pelo que a decisão terá de ser
justificada na tese seja qual for.

**Aviso de excipiente conta como farmacogenómica?** A frase «problemas
hereditários raros de intolerância à galactose / à frutose» está em 38 dos 64
documentos. É texto padronizado europeu. Num corpus onde a maioria dos RCMs
não tem farmacogenómica, passa a ser o principal falso positivo.

**Entidades somáticas e virais.** O KRAS do irinotecano é genótipo do tumor, e
o «Genótipo 1» do peginterferão é do vírus da hepatite C. Nenhum é
farmacogenética germinal. Ficou decidido contá-los (são o que está no rótulo),
falta decidir se ficam etiquetados à parte.

**Regra de representante a declarar.** Suíços colapsam texto idêntico;
italianos escolhem o rótulo com mais biomarcadores; nós escolhemos o mais
extenso — que é a regra italiana, e enviesa para cima.

### Correções e melhorias

- Tradução do código para inglês: 229 de 666 itens feitos. Faltam 228 nos dois
  módulos grandes (`pharmacogenomics_evaluator`, `pgx_global_analysis`).
- Chaves dos JSON de output em português (31 de 57). Traduzir só no momento em
  que se reprocessar o corpus, senão invalida os outputs existentes.
- Registo de progresso incremental (o log só é escrito no final).
- Partir o `pgx_global_analysis` em análise e escrita de Excel (costura limpa
  na linha 1739).
- Arrumar as seis ferramentas de preparação numa subpasta.
- Apagar `extra-tools/pgx_ner.py`: está morto e nem compila (importa `merpy`,
  removido das dependências).

### Validação do modelo

**Existe padrão de referência anotado à mão.** Os 17 RCMs do subconjunto
(`Subset/1ºDS+`, 11 documentos de controlo positivo; `Subset/2ºDT-`, 6 de
controlo negativo) foram **revistos manualmente por profissionais da área**.
São 152 secções com resposta conhecida.

Isto é o activo metodológico mais forte do trabalho e tem de constar da tese:
a escolha do modelo deixa de ser preferência e passa a ser medição. Permite
calcular, para cada modelo candidato:

- **sensibilidade** — das secções que contêm farmacogenómica, quantas o
  modelo identifica;
- **especificidade** — das que não contêm, quantas rejeita corretamente (é
  para isto que serve o controlo negativo);
- **precisão das entidades** — das entidades extraídas, quantas constam
  mesmo do texto.

Sem padrão de referência, comparar modelos entre si mede apenas concordância:
se dois falharem no mesmo sítio, concordam e ninguém dá por isso. Com ele,
mede-se acerto.

Por fazer: correr cada modelo candidato sobre os mesmos 17 e calcular as três
métricas contra a anotação manual. Falta ainda a concordância entre corridas
do mesmo modelo (o pipeline é determinístico, mas convém demonstrá-lo).

---

## 11. Varrimento linear do MRCONSO — o tecto do processamento nacional

**Diagnosticado a 15-09-2026, durante o benchmark de paralelismo. Por
corrigir.**

### Sintoma

Na corrida do GLM de 10-09, o omeprazol levou 64 minutos contra uma média de
3m38s nos restantes dez documentos. Na altura foi atribuído a um problema de
rede. **Estava errado.** A 15-09, com a cache do resolvedor apagada, o mesmo
documento voltou a levar mais de setenta minutos.

### Prova

Com o processo ainda vivo (PID 78673, lançado às 04:13, `sample` às 05:26):

- `ps aux` — 211,6% de CPU no último minuto, mas só **12m25s de CPU
  acumulado em ~73 minutos de relógio**. Passou a maior parte do tempo sem
  progredir e nada disso era espera de rede.
- `sample` — a pilha da main thread parada em
  `unicode_join` → `PySequence_Fast` → `list_extend` → `gen_iternext` →
  `unicodedata_UCD_combining`. É o idioma de remoção de acentos, carácter a
  carácter, em Python puro.
- `lsof -p 78673 -i` — a ligação a `ollama.com` **estabelecida mas
  inactiva**. O modelo não estava a ser chamado.

O log estava vazio: o `medir.sh` invocava `python3` sem `-u` e o stdout
redirigido ficou em buffer. Setenta minutos às cegas. Corrigir no script.

### Causa

`active_substance_external_resolver._resolve_mrconso_one()` percorre o
`MRCONSO.RRF` **linha a linha, do princípio ao fim**, e para cada linha chama
`substance_utils.normalize()` (linha 484):

```python
text = unicodedata.normalize("NFKD", text)
text = "".join(c for c in text if not unicodedata.combining(c))
```

O ficheiro tem **2,34 GB**. E há uma **segunda** passagem completa na linha
545, para recolher os sinónimos ingleses e o DrugBank ID dos CUI encontrados.

Uma substância não-cacheada custa portanto ~4,7 GB de leitura e a
normalização de milhões de strings em Python. O `break` dos 25 candidatos só
dispara em nomes muito comuns; para um nome raro lê-se o ficheiro inteiro.
Substâncias compostas custam múltiplos disto, uma vez por cada candidato
devolvido por `split_substances`.

### Porque é que isto é o tecto

A cache tem **501 substâncias**. O corpus nacional tem **1 661 distintas**.
Sobram ~1 160 frias. Mesmo a dez minutos cada — e o omeprazol levou mais —
são mais de oito dias de CPU em série só a ler o MRCONSO, antes de contar um
único minuto de LLM.

**O limite do processamento nacional não é a concorrência do Ollama Cloud.**
É isto. O benchmark de paralelismo não responde à pergunta que interessa
enquanto isto não for corrigido — e, pior, o `medir.sh` apaga a cache antes
de cada K, o que paga o custo três vezes e, no K=2 e K=4, concentra-o num só
processo enquanto os outros esperam no `wait`. As medições de 15-09 são
inválidas e foram descartadas.

### Correcção proposta

Indexar o MRCONSO **uma vez** para SQLite, com as colunas usadas
(`cui`, `lat`, `sab`, `code`, `scui`, `sdui`, `str`, `str_norm`) e índices em
`str_norm` e `cui`:

- match exacto — deixa de ser varrimento e passa a lookup;
- parcial `string_norm in query_norm` — inverte-se para as substrings da
  consulta, que são poucas e curtas;
- parcial `query_norm in string_norm` — passa a `LIKE`, corrido em C pelo
  SQLite em vez de Python;
- segunda passagem — deixa de reler 2,34 GB para ir buscar uma dúzia de
  linhas por CUI.

Construção: uma passagem única. Validação: os resultados têm de ser idênticos
aos actuais nas 501 substâncias já em cache, que servem de padrão de
regressão.

### A corrigir no `benchmark11/medir.sh`

1. `python3 -u`, para o log existir enquanto corre.
2. Não apagar a cache entre valores de K — a corrida nacional terá a cache
   quente em quase todos os documentos, portanto é o estado quente que
   interessa medir.
