# Base de dados e página de consulta — como montar

Três passos. Nenhum precisa de servidor, de conta paga, ou de manutenção
depois de estar feito.

---

## 1. Construir a base de dados

Na tua máquina, a partir de `FINALV2`:

```powershell
python basedados\construir_bd.py out_nacional basedados\huorm.db
```

Lê os `Document_Unique_PGx.json` e os `Extended_PGx_Analysis.json` de cada
documento processado e escreve `huorm.db`. Demora alguns minutos — passa por
5 565 pastas.

Confirmar que ficou bem:

```powershell
python basedados\construir_bd.py --verificar basedados\huorm.db
```

Imprime o número de linhas de cada tabela e os genes mais frequentes. Se os
genes forem CYP2D6, CYP2C19 e SLCO1B1, está certo — batem com o capítulo 4.

**Se voltares a correr o pipeline**, corres isto outra vez e a base
acompanha. Não há nada a migrar à mão.

---

## 2. Ver a página no teu computador

O browser não deixa uma página local ler ficheiros vizinhos, por isso é
preciso um servidor local de um comando:

```powershell
copy basedados\huorm.db basedados\site\huorm.db
cd basedados\site
python -m http.server 8000
```

Abre `http://localhost:8000`. Deves ver o número de documentos no topo e as
perguntas de exemplo a funcionar.

Se não carregar, é quase sempre o `huorm.db` não estar dentro de `site/`.

---

## 3. Publicar

### GitHub Pages

1. Cria um repositório novo — por exemplo `huorm-consulta`.
2. Põe lá dentro o conteúdo de `basedados/site/`: o `index.html` e o `huorm.db`.
3. No repositório: **Settings → Pages → Source: Deploy from a branch →
   main / (root)** e guarda.
4. Um ou dois minutos depois fica em
   `https://hugonnicolau.github.io/huorm-consulta/`.

### Cloudflare Pages

Igual em substância: ligas o repositório, deixas o comando de build vazio e
indicas a pasta de saída. Dá um domínio `.pages.dev`.

**Qual escolher.** Para isto tanto faz. O GitHub Pages é menos um sítio onde
ter conta, já que o código vai para lá de qualquer maneira.

---

## O que dizer na tese

O endereço entra ao lado do repositório de código, na secção de
reprodutibilidade do capítulo 1. E o capítulo 4, na linha 179, tem um
parágrafo a dizer que a base de dados **não** foi feita — esse tem de ser
reescrito, porque deixou de ser verdade.

---

## Limites, ditos antes que alguém pergunte

**Não é uma API com endpoints HTTP.** É uma base de dados consultável no
browser. Quem quiser acesso programático descarrega o `huorm.db` e usa-o
localmente, que para 2,5 MB é mais prático do que chamar um serviço.

**O ficheiro é descarregado inteiro** ao abrir a página. Com este tamanho
não se nota. Se a base crescer muito — dez vezes, digamos — vale a pena
passar a `sql.js-httpvfs`, que só busca as páginas necessárias.

**As consultas são só de leitura** na prática: cada visitante tem a sua
cópia em memória e nada do que escreva afecta seja quem for.
