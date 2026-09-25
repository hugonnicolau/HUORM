/**
 * A pagina de consulta, servida pelo proprio Worker na raiz.
 *
 * Porque nao a do basedados/site/: essa descarrega o huorm.db inteiro, 6 MB,
 * e corre SQL no browser com o sql.js. Funciona, mas obriga a alojar o
 * ficheiro noutro sitio e a esperar pelo descarregamento antes da primeira
 * pergunta. Esta pergunta aos endpoints que ja existem ao lado, por isso
 * responde de imediato e vive no mesmo endereco.
 *
 * As duas nao se anulam: a do sql.js aceita SQL livre, esta so as perguntas
 * que a API expoe. Quem quiser SQL arbitrario descarrega a base.
 */

export const PAGINA = `<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUORM: informação farmacogenómica dos RCM portugueses</title>
<style>
  :root { --tinta:#1a1a1a; --suave:#666; --linha:#e0e0e0; --fundo:#fafafa; }
  * { box-sizing:border-box; }
  body { font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         color:var(--tinta); margin:0; background:#fff; }
  .caixa { max-width:1060px; margin:0 auto; padding:32px 20px 64px; }
  h1 { font-size:25px; margin:0 0 6px; font-weight:600; letter-spacing:-.01em; }
  .sub { color:var(--suave); margin:0 0 22px; max-width:62ch; }
  .estado { padding:10px 14px; background:var(--fundo); border:1px solid var(--linha);
            border-radius:6px; color:var(--suave); margin-bottom:26px; font-size:14px; }
  .estado.erro { background:#fff4f4; border-color:#f0c0c0; color:#a33; }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.07em;
       color:var(--suave); margin:26px 0 10px; font-weight:600; }
  .perguntas { display:grid; gap:6px; }
  button { text-align:left; background:#fff; color:var(--tinta);
           border:1px solid var(--linha); border-radius:6px;
           padding:10px 13px; font-size:14px; cursor:pointer; font-family:inherit; }
  button:hover { border-color:var(--tinta); }
  button small { color:var(--suave); }
  .procura { display:flex; gap:8px; margin-top:6px; }
  .procura input { flex:1; padding:10px 12px; border:1px solid var(--linha);
                   border-radius:6px; font:inherit; }
  .procura button { flex:0 0 auto; background:var(--tinta); color:#fff;
                    border-color:var(--tinta); }
  table { border-collapse:collapse; width:100%; margin-top:18px; font-size:13px; }
  th,td { border-bottom:1px solid var(--linha); padding:7px 10px; text-align:left;
          vertical-align:top; }
  th { background:var(--fundo); font-weight:600; position:sticky; top:0; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .rolo { max-height:560px; overflow:auto; border:1px solid var(--linha);
          border-radius:6px; margin-top:18px; }
  .rolo table { margin:0; }
  .contagem { margin-top:12px; color:var(--suave); font-size:13px; }
  .url { font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
         color:var(--suave); word-break:break-all; margin-top:10px; }
  footer { margin-top:52px; padding-top:20px; border-top:1px solid var(--linha);
           color:var(--suave); font-size:13px; }
  a { color:var(--tinta); }
</style>
</head>
<body>
<div class="caixa">

  <h1>HUORM</h1>
  <p class="sub">Informação farmacogenómica extraída dos Resumos das
  Características do Medicamento portugueses. As perguntas abaixo são feitas
  à API pública desta mesma página. Cada uma mostra o endereço que usou, para
  poder ser repetida a partir de qualquer programa.</p>

  <div class="estado" id="estado">A carregar…</div>

  <h2>Perguntas</h2>
  <div class="perguntas">
    <button data-url="/api/cobertura/genes">Cobertura das guidelines, gene a gene
      <small>quantas vezes cada gene é exigido e quantas está em falta no rótulo</small></button>

    <button data-url="/api/cobertura?estado=ausente&limite=200">Onde o rótulo fica aquém da guideline
      <small>fármacos com guideline publicada cujo gene o RCM não nomeia</small></button>

    <button data-url="/api/genes?limite=40">Genes mais mencionados
      <small>contando alelos e diplótipos para o gene a que pertencem</small></button>

    <button data-url="/api/seccoes">Onde é que a farmacogenómica aparece
      <small>distribuição pelas secções normativas do RCM</small></button>
  </div>

  <h2>Procurar uma substância</h2>
  <div class="procura">
    <input id="q" placeholder="tramadol, clopidogrel, sinvastatina…"
           autocomplete="off" spellcheck="false">
    <button id="procurar">Procurar</button>
  </div>

  <h2>Um gene em concreto</h2>
  <div class="procura">
    <input id="g" placeholder="CYP2D6, G6PD, SLCO1B1…"
           autocomplete="off" spellcheck="false">
    <button id="verGene">Ver</button>
  </div>

  <div class="url" id="url"></div>
  <div id="saida"></div>

  <footer>
    Dados de uma corrida datada do pipeline, sobre 5 565 RCM do INFOMED.
    A API é pública e devolve JSON. <a href="/api">Ver os endereços</a>.
    <br>Dissertação de mestrado em Bioinformática e Biologia Computacional,
    Faculdade de Ciências da Universidade de Lisboa.
  </footer>

</div>

<script type="module">
const estado = document.getElementById("estado");
const saida  = document.getElementById("saida");
const caixaU = document.getElementById("url");

const num = v => typeof v === "number" ? v.toLocaleString("pt-PT") : v;
const esc = v => v === null || v === undefined
  ? '<span style="color:#bbb">—</span>'
  : String(v).replace(/[<>&]/g, c => ({ "<":"&lt;", ">":"&gt;", "&":"&amp;" }[c]));

try {
  const r = await (await fetch("/api/estatisticas")).json();
  estado.textContent =
    num(r.documentos) + " documentos, " + num(r.substancias) + " substâncias, "
    + num(r.mencoes) + " menções de entidades, "
    + num(r.documentos_com_pgx) + " documentos com conteúdo farmacogenómico";
} catch (e) {
  estado.className = "estado erro";
  estado.textContent = "Não foi possível falar com a API: " + e.message;
}

/** Encontra a lista de resultados venha ela com o nome que vier. */
function linhasDe(dados) {
  if (Array.isArray(dados)) return dados;
  for (const k of ["cobertura","genes","substancias","seccoes","mencoes",
                   "entidades","documentos"]) {
    if (Array.isArray(dados[k])) return dados[k];
  }
  return [dados];
}

function mostrar(dados, url) {
  caixaU.textContent = new URL(url, location.origin).href;
  const linhas = linhasDe(dados);
  if (!linhas.length) {
    saida.innerHTML = '<p class="contagem">Sem resultados.</p>';
    return;
  }
  const cols = [...new Set(linhas.flatMap(Object.keys))];
  saida.innerHTML =
    '<div class="rolo"><table><thead><tr>'
    + cols.map(c => \`<th>\${esc(c.replace(/_/g, " "))}</th>\`).join("")
    + "</tr></thead><tbody>"
    + linhas.map(l => "<tr>" + cols.map(c => {
        const v = l[c];
        return \`<td class="\${typeof v === "number" ? "num" : ""}">\${esc(num(v))}</td>\`;
      }).join("") + "</tr>").join("")
    + "</tbody></table></div>"
    + \`<p class="contagem">\${linhas.length.toLocaleString("pt-PT")} linhas.</p>\`;
}

async function pedir(url) {
  saida.innerHTML = '<p class="contagem">A consultar…</p>';
  caixaU.textContent = "";
  try {
    const resposta = await fetch(url);
    const dados = await resposta.json();
    if (dados.erro) {
      saida.innerHTML = \`<p class="contagem" style="color:#a33">\${esc(dados.erro)}</p>\`;
      return;
    }
    mostrar(dados, url);
  } catch (e) {
    saida.innerHTML = \`<p class="contagem" style="color:#a33">\${esc(e.message)}</p>\`;
  }
}

document.querySelectorAll(".perguntas button").forEach(b =>
  b.addEventListener("click", () => pedir(b.dataset.url)));

const q = document.getElementById("q");
const g = document.getElementById("g");
const procurar = () => q.value.trim() &&
  pedir("/api/substancias?limite=100&q=" + encodeURIComponent(q.value.trim()));
const verGene = () => g.value.trim() &&
  pedir("/api/gene/" + encodeURIComponent(g.value.trim()) + "?limite=200");

document.getElementById("procurar").addEventListener("click", procurar);
document.getElementById("verGene").addEventListener("click", verGene);
q.addEventListener("keydown", e => { if (e.key === "Enter") procurar(); });
g.addEventListener("keydown", e => { if (e.key === "Enter") verGene(); });

pedir("/api/cobertura/genes");
</script>
</body>
</html>`;
