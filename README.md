<img src="logo.png" alt="HUORM" width="380">

A pipeline, based on a large language model, for extracting pharmacogenomic
information from Portuguese Summaries of Product Characteristics (SmPCs,
*Resumos das Características do Medicamento*).

MSc dissertation in Bioinformatics and Computational Biology, Faculdade de
Ciências da Universidade de Lisboa, 2026.

**Public query interface:** <https://huorm-api.hugonnicolau.workers.dev>

The same address serves both: the root is a search page, and `/api` returns
the same information as JSON, without credentials, to be read by another
program. The figures reported in the dissertation can be reproduced from it by
direct query.

---

## Structure

```
RCMprocessor/       The pipeline. This is what the dissertation describes.
basedados/          SQLite schema (esquema.sql), builder and the database (huorm.db).
api/                Public API (Cloudflare Workers + D1).
extra-tools/        Everything that is not the pipeline.
  preparacao/         before the run: UMLS index, guideline recomputation
  analise/            after the run: the numbers reported in the dissertation
  testes/             199 automated tests
  dados/              saved outputs in CSV
Dockerfile          Pinned execution environment.
```

The split follows one rule: `RCMprocessor/` contains only the modules the run
imports. Everything run by hand, to prepare or analyse, is in `extra-tools/`,
because it is not part of the method described in the dissertation.

Folder, file, table and column names are in Portuguese, as referenced in the
dissertation. The prompts are in Portuguese because the SmPCs are.

## Corpus

5,605 SmPCs from INFOMED, deduplicated by exact textual identity; 5,551 were
analysed (54 had no usable text after conversion). They yielded 5,831 mentions
of pharmacogenomic entities, and 3,131 documents have pharmacogenomic content.

## Running the tests

```bash
python extra-tools/testes/run_all.py
```

All 199 should pass.

## What is not included

The SmPC corpus is not redistributed. The documents are public on INFOMED.

The UMLS index is not included either, because the UMLS licence forbids it.
It is generated with `extra-tools/preparacao/construir_indice_mrconso.py` from
a licensed copy of MRCONSO.

The ClinPGx files are not included; they are downloaded from
<https://www.clinpgx.org/downloads>, and the download dates used are stated in
the dissertation.

The database (`basedados/huorm.db`, 6 MB) is included. Without it the
repository would not be reproducible, since the corpus is not.

## Model key

The pipeline calls a model served by Ollama Cloud. The key is read from an
environment variable and is never stored in the code or in the image:

```bash
cp .env.example .env     # then fill in OLLAMA_API_KEY
```
