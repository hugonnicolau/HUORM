# Passo a passo — base de dados, página, Docker e repositório

Sete passos por ordem. Cada um diz o comando, o que deves ver, e o que fazer
se não vires isso. Nenhum passo depende de um passo posterior, por isso podes
parar a meio e continuar depois.

Todos os comandos correm no PowerShell, a partir de:

```powershell
cd C:\Users\Utilizador\Desktop\ApresentaçãoV2\FINALV2
```

---

## Passo 1 — Construir a base de dados

```powershell
python basedados\construir_bd.py out_nacional basedados\huorm.db
```

**Demora alguns minutos.** Passa por 5 565 pastas e lê dois ficheiros em cada.

**Deves ver** sete linhas no fim:

```
documentos : 5565
substancias: 1580
entidades  : 2163
ent.×secção: 2669
passagens  : <alguns milhares>
guidelines : 1128
cobertura  : 4887
```

**Se as duas últimas forem 0**, o script não encontrou o
`out_nacional\Analise_Global_PGx.xlsx` — a cobertura vem de lá, porque as
guidelines *em falta* não existem nos JSON por documento. Diz-me e vemos.

**Se `entidades` for 2169 e `passagens` for 0**, estás a correr uma versão
antiga do script — confirma que o ficheiro tem a palavra `passagem` lá dentro.

**Se der erro de ficheiro não encontrado**, confirma que `out_nacional` existe
nessa pasta e tem lá dentro as pastas dos documentos.

---

## Passo 2 — Confirmar que a base ficou bem

```powershell
python basedados\construir_bd.py --verificar basedados\huorm.db
```

**Deves ver** o tamanho do ficheiro, a contagem de cada tabela, e no fim os
genes mais frequentes.

**O teste:** os três primeiros genes devem ser **CYP2D6, CYP2C19 e SLCO1B1**.
São os mesmos do capítulo 4. Se forem outros, alguma coisa correu mal e não
adianta seguir.

**O segundo teste**, agora que a cobertura entrou: no fim aparece uma lista dos
genes mais exigidos por guideline. O **CYP3A4** deve estar a 100% de ausência —
é exigido em 238 rótulos e não é nomeado em nenhum. Se esse número for
diferente, a cobertura não carregou da folha certa.

**O terceiro teste é o que interessa mais.** A verificação imprime:

```
menções de entidades: 5885
o capítulo 4 reporta 5885  <-- BATE
entidades cujas secções não somam o total: 0  (correcto)
```

Se disser **NÃO BATE**, pára e manda-me o número. As menções da base têm de
ser exactamente as da tese; se divergirem, quem cruzar os dois vê a
discrepância.

---

## Passo 3 — Ver a página no teu computador

O logótipo já está em `basedados\site\huorm-logo.png`, copiado do
`huorm2.png` da raiz. Não tens de fazer nada com ele.

```powershell
Copy-Item basedados\huorm.db basedados\site\huorm.db -Force
cd basedados\site
python -m http.server 8000
```

Abre o browser em **http://localhost:8000**

**Deves ver** o título HUORM e, por baixo, uma linha cinzenta com o número de
documentos, entidades e substâncias. Carrega numa das perguntas de exemplo e
deve aparecer uma tabela.

**Se disser "não foi possível carregar"**, é quase de certeza o `huorm.db` não
estar dentro de `site\` — repete a primeira linha.

Para parar o servidor: `Ctrl+C`. Depois `cd ..\..` para voltar a `FINALV2`.

---

## Passo 4 — Construir a imagem Docker

Só se tiveres o Docker Desktop instalado **e aberto** — o `docker build` falha
com `failed to connect to the docker API` enquanto a aplicação não arrancar.

**A primeira linha é a que importa.** O passo 3 deixou-te dentro de
`basedados\site`, e o `Dockerfile` está na raiz do `FINALV2`. Sem voltar atrás,
o Docker responde `failed to read dockerfile: open Dockerfile: no such file or
directory`.

```powershell
cd C:\Users\Utilizador\Desktop\ApresentaçãoV2\FINALV2
docker build -t huorm:2.0.0 .
docker --version
```

**A primeira construção demora**, porque descarrega os modelos do docling. Mas
deve começar depressa: a linha `transferring context` tem de ficar-se pelos
poucos MB. Se disseres que está a transferir gigabytes, o `.dockerignore` não
está a ser lido — pára e diz-me. Esse ficheiro existe por duas razões: manter
o corpus fora da imagem, e manter fora o `RCMprocessor\.env`, que tem a tua
chave do Ollama e ficaria gravado numa camada da imagem se lá entrasse.

**Deves ver** no fim `Successfully tagged huorm:2.0.0`, e depois a versão do
Docker numa linha.

**Guarda essa versão** — é o valor que falta nos dois marcadores
`[[VERSÃO: Docker]]` da tese. Manda-ma e eu preencho.

**Se não quiseres instalar o Docker**, diz-me: em vez de preencher os
marcadores, tiro as duas frases que afirmam que a imagem existe. O que não
pode é a tese afirmar uma coisa que não é verdade.

---

## Passo 5 — Preparar o repositório, com a verificação de segurança

```powershell
cd C:\Users\Utilizador\Desktop\ApresentaçãoV2\FINALV2
git init
git add -A
git status --short | findstr /i ".env umls mrconso node_modules huorm_d1.sql"
```

**Deves ver: nada.** Linha vazia.

**Se aparecer alguma linha, PARA.** Quer dizer que o `.gitignore` deixou
passar um ficheiro que não pode ir — a chave do Ollama, dados do UMLS, as
dependências do wrangler, ou o SQL de 5 MB. Manda-me o que apareceu antes de
fazeres commit.

O `basedados\huorm.db` **aparece de propósito** e não é problema: são 6 MB,
e sem ela ninguém consegue reconstruir nada, porque o `out_nacional` não vai
para o repositório. Confirma que lá está:

```powershell
git status --short | findstr "huorm.db"
```

Se não apareceu nada:

```powershell
git commit -m "Pipeline de extraccao farmacogenomica de RCM portugueses"
```

---

## Passo 6 — Pôr o código no GitHub

O repositório `HUORM` já existe na tua conta.

```powershell
git remote add origin https://github.com/hugonnicolau/HUORM.git
git branch -M main
git push -u origin main
```

**Se pedir autenticação**, o GitHub já não aceita palavra-passe: tens de usar
um token pessoal ou o GitHub CLI. O mais simples é instalar o GitHub CLI e
correr `gh auth login` uma vez.

---

## Passo 7 — Publicar a página

A página é um repositório **separado**, porque o `huorm.db` não vai no
repositório do código.

1. No GitHub, cria um repositório novo: **huorm-consulta**, público.
2. Arrasta para lá os três ficheiros de `basedados\site\`:
   `index.html`, `huorm.db` e `huorm-logo.png`. Dá para fazer pelo site,
   sem git.
3. Nesse repositório: **Settings → Pages**
4. Em **Source**, escolhe **Deploy from a branch**, ramo **main**, pasta
   **/ (root)**. Guarda.
5. Espera um ou dois minutos e abre
   `https://hugonnicolau.github.io/huorm-consulta/`

**Deves ver** a mesma página que viste no passo 3.

Manda-me o endereço final — entra na tese ao lado do repositório de código.

---

## Depois de tudo isto, o que muda na tese

Três coisas, e faço-as eu quando me deres os valores:

1. Os dois `[[VERSÃO: Docker]]`, com a versão do passo 4.
2. O endereço da página, na secção de reprodutibilidade do capítulo 1.
3. O parágrafo da linha 179 do capítulo 4, que hoje diz que a base de dados
   não foi feita. Deixa de ser verdade e tem de ser reescrito — passa a
   descrever o que foi construído e porquê em SQLite em vez de PostgreSQL.

---

## Se alguma coisa correr mal

Manda-me a mensagem de erro tal como aparece, e o número do passo. Não
adaptes nem resumas — a mensagem literal costuma dizer exactamente o que
falta.
