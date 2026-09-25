# HUORM

Pipeline de extracção de informação farmacogenómica dos Resumos das
Características do Medicamento (RCM) portugueses, baseado num modelo de
linguagem.

Dissertação de mestrado em Bioinformática e Biologia Computacional, Faculdade
de Ciências da Universidade de Lisboa, 2026.

- **Consulta pública:** <https://huorm-api.hugonnicolau.workers.dev>
- **Corpus:** 5 565 RCM do INFOMED, deduplicados por identidade textual exacta

---

## Estrutura

```
RCMprocessor/       O pipeline. É isto que a tese descreve.
basedados/          Esquema SQLite, construtor e página de consulta.
api/                API pública (Cloudflare Workers + D1).
extra-tools/        Tudo o que não é o pipeline.
  preparacao/         antes da corrida: índice MRCONSO, cache, lotes
  execucao/           durante: lançamento, progresso, diagnóstico
  analise/            depois: os números que entram na tese
  testes/             189 testes automáticos
  dados/              saídas guardadas em CSV
Dockerfile          Ambiente de execução fixado.
PASSO_A_PASSO.md    Como montar a base de dados e publicar.
api/README.md       Como publicar a API.
```

A divisão tem uma regra: o `RCMprocessor/` contém apenas os módulos que a
corrida importa. Tudo o que se corre à mão — para preparar, acompanhar ou
analisar — está em `extra-tools/`, porque não faz parte do método descrito na
tese e não deve dar a entender que faz.

## Correr os testes

```bash
python extra-tools/testes/run_all.py
```

Devem passar 189 de 189.

## O que não está aqui

O corpus de RCM não é redistribuído: são documentos públicos do INFOMED e
reconstroem-se a partir da fonte com as ferramentas de `extra-tools/preparacao`.
O índice do UMLS também não, porque a licença o proíbe — gera-se com o
`construir_indice_mrconso.py` a partir de uma cópia licenciada do MRCONSO.

A base de dados construída (`basedados/huorm.db`, 6 MB) **está** incluída: sem
ela o repositório não seria reproduzível, já que o corpus não vem junto.

## Chave do modelo

O pipeline chama um modelo servido pelo Ollama Cloud. A chave entra por
variável de ambiente e nunca fica no código nem na imagem:

```bash
cp .env.example .env     # e preencher OLLAMA_API_KEY
```
