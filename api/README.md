# API HUORM — Cloudflare Workers + D1

Seis passos. Precisas de uma conta Cloudflare (gratuita) e do Node instalado.
Não precisas de saber nada de Cloudflare: o `wrangler` faz tudo pela linha de
comandos e abre o browser quando precisa que autorizes.

A base tem 5 MB e o plano gratuito do D1 dá 5 GB de armazenamento e 100 000
leituras por dia. Não há cartão de crédito em lado nenhum.

Todos os comandos correm a partir de:

```powershell
cd C:\Users\Utilizador\Desktop\ApresentaçãoV2\FINALV2\api
```

---

## Passo 1 — Entrar na conta

```powershell
npx wrangler login
```

Abre o browser e pede autorização. Uma vez só.

**Se o `npx` não existir**, falta o Node: https://nodejs.org (versão LTS).

---

## Passo 2 — Criar a base no D1

```powershell
npx wrangler d1 create huorm
```

**Deves ver** um bloco com `database_id = "..."`.

**Copia esse id** e cola-o no `wrangler.toml`, na linha que está vazia:

```toml
database_id = "cola-aqui"
```

Sem isso, o passo 4 falha a dizer que não encontra a base.

---

## Passo 3 — Gerar o SQL a partir da base local

Continua dentro de `api\`. Os caminhos são relativos a essa pasta, para não
haver o vaivém de `cd` que faz duplicar `api\api\`.

```powershell
python exportar_para_d1.py ..\basedados\huorm.db huorm_d1.sql
```

**Deves ver** as seis tabelas e, no fim, cerca de **5.0 MB**.

Se `guideline` e `cobertura` aparecerem a 0, a base local ainda é a antiga —
volta ao passo 1 do `PASSO_A_PASSO.md` e reconstrói.

---

## Passo 4 — Carregar os dados

```powershell
npx wrangler d1 execute huorm --remote --file=huorm_d1.sql
```

**Demora alguns minutos.** São cerca de 21 000 linhas.

O `--remote` é obrigatório: sem ele o wrangler escreve numa cópia local, no
teu disco, e depois o Worker publicado não encontra nada. É o erro mais fácil
de cometer aqui.

**Confirmar:**

```powershell
npx wrangler d1 execute huorm --remote --command "SELECT COUNT(*) FROM cobertura"
```

Deve dizer **4887**.

---

## Passo 5 — Publicar

```powershell
npx wrangler deploy
```

**Deves ver** no fim um endereço do género
`https://huorm-api.<o-teu-nome>.workers.dev`

Abre-o no browser: a raiz descreve-se a si própria e lista os endpoints.

---

## Passo 6 — Experimentar

Substitui `<URL>` pelo endereço do passo 5.

**Usa `curl.exe`, com o `.exe`.** No PowerShell 5.1 o `curl` sem extensão é um
apelido para o `Invoke-WebRequest`, que negoceia TLS 1.0 e leva com um
`Não foi possível criar um canal seguro SSL/TLS` da Cloudflare. Não é a API
que está em baixo.

```powershell
curl.exe <URL>/api/estatisticas
curl.exe "<URL>/api/cobertura?gene=CYP2D6&estado=ausente&limite=10"
curl.exe <URL>/api/substancia/tramadol
curl.exe <URL>/api/cobertura/genes
```

O segundo é a pergunta central da tese: fármacos com guideline publicada para
o CYP2D6 cujo RCM não nomeia o gene.

**Manda-me o endereço.** Entra na tese ao lado do repositório de código.

---

## O que fazer se correr mal

| O que aparece | O que é |
|---|---|
| `Couldn't find a D1 DB` | o `database_id` no `wrangler.toml` está vazio ou errado (passo 2) |
| `no such table: cobertura` | fizeste o passo 4 sem `--remote` |
| `Authentication error` | a sessão expirou: `npx wrangler login` outra vez |
| a raiz responde mas `/api/...` dá 500 | os dados não carregaram; repete o passo 4 e confirma a contagem |

---

## Notas de desenho

**Porquê isto, havendo já a página de consulta.** A página descarrega a base
inteira e corre SQL no browser. Serve uma pessoa a olhar para o ecrã; não
serve outro programa. A API tem endpoints com parâmetros e responde JSON, que
é o que permite a um sistema de prescrição, a um script ou a um notebook
perguntarem alguma coisa à base. As duas coisas coexistem e usam a mesma base.

**Segurança.** Todas as consultas são preparadas com `bind()`. Nenhum valor
vindo do pedido é concatenado para dentro de SQL. O Worker só aceita `GET`,
não há escrita, e a mensagem de erro do D1 nunca chega ao cliente — pode
conter o SQL.

**Imutabilidade.** Os dados correspondem a uma corrida datada do pipeline. Não
há endpoint de escrita: para actualizar, refaz-se o passo 3 e o passo 4.
