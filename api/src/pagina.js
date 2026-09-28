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
  .logo { height:96px; width:auto; max-width:100%; object-fit:contain; object-position:left; display:block; margin:0 0 12px -4px; }
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
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th,td { border-bottom:1px solid #eee; padding:9px 12px; text-align:left;
          vertical-align:middle; }
  th { background:var(--fundo); font-weight:600; position:sticky; top:0;
       font-size:11px; text-transform:uppercase; letter-spacing:.05em;
       color:var(--suave); border-bottom:1px solid var(--linha); }
  tbody tr:last-child td { border-bottom:none; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }
  td.mono, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
                   font-size:12.5px; }
  .sel { display:inline-block; padding:2px 8px; border-radius:11px;
         font-size:11.5px; font-weight:600; letter-spacing:.02em; }
  .sel.ok   { background:#e6f4ea; color:#1a7f37; }
  .sel.mau  { background:#fdecea; color:#b3261e; }
  .sel.meio { background:#fdf3e2; color:#8a5a00; }
  .sel.neutro { background:#eef1f4; color:#44505c; }
  .seccao { display:inline-block; padding:1px 6px; margin:0 3px 2px 0;
            border:1px solid var(--linha); border-radius:4px; font-size:11.5px;
            color:var(--suave); font-variant-numeric:tabular-nums; }
  .vazio { color:#ccc; }
  .logo { cursor:pointer; }
  .grafico { margin-top:20px; }
  .grafico svg { width:100%; height:auto; display:block; }
  .grafico .g-nome { font-size:11.5px; fill:var(--tinta); font-weight:600; }
  .grafico .g-val  { font-size:10.5px; fill:var(--suave); }
  .grafico g.barra { cursor:pointer; }
  .grafico g.barra:hover .g-nome { text-decoration:underline; }
  .grafico g.barra:hover rect.fundo { stroke:var(--tinta); }
  .legenda { display:flex; gap:18px; margin-top:14px; font-size:12px;
             color:var(--suave); align-items:center; flex-wrap:wrap; }
  .legenda i { width:11px; height:11px; border-radius:2px; display:inline-block;
               margin-right:5px; vertical-align:-1px; }
  .alternar { margin-left:auto; background:none; border:none; padding:0;
              color:var(--suave); font-size:12px; text-decoration:underline;
              cursor:pointer; font-family:inherit; }
  .alternar:hover { color:var(--tinta); }
  .rolo { max-height:560px; overflow:auto; border:1px solid var(--linha);
          border-radius:6px; margin-top:18px; }
  .rolo table { margin:0; }
  .contagem { margin-top:12px; color:var(--suave); font-size:13px; }
  tr.abre { cursor:pointer; }
  tr.abre:hover td { background:var(--fundo); }
  tr.abre td:first-child { font-weight:600; }
  td.accao { text-align:right; white-space:nowrap; width:1%; }
  button.info { padding:3px 10px; font-size:12px; border-radius:5px;
                border:1px solid var(--linha); background:#fff;
                color:var(--tinta); cursor:pointer; }
  tr.abre:hover button.info { border-color:var(--tinta); }
  .bloco h3 { font-size:13px; text-transform:uppercase; letter-spacing:.06em;
              color:var(--suave); margin:22px 0 0; font-weight:600; }
  .voltar { margin-top:16px; background:#fff; border:1px solid var(--linha);
            padding:7px 12px; font-size:13px; border-radius:6px; }
  .url { font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
         color:var(--suave); word-break:break-all; margin-top:10px; }
  footer { margin-top:52px; padding-top:20px; border-top:1px solid var(--linha);
           color:var(--suave); font-size:13px; }
  a { color:var(--tinta); }
</style>
</head>
<body>
<div class="caixa">

  <img src="data:image/png;base64,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" alt="HUORM Data Base" class="logo">
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
    Dados de uma corrida datada do pipeline, sobre 5 551 RCM do INFOMED.
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

const MONO = new Set(["valor","gene","guideline_id","cui","drugbank","mesh",
                      "ficheiro","codigo_atc","genes_em_falta"]);
const SIMNAO = new Set(["tem_pgx","tem_entidades"]);

/** Como se desenha o conteudo de uma celula, consoante a coluna. */
function celula(col, v) {
  if (v === null || v === undefined || v === "")
    return '<td><span class="vazio">&mdash;</span></td>';

  // 1/0 nao diz nada a quem le; Sim/Nao diz.
  if (SIMNAO.has(col))
    return '<td>' + (Number(v)
      ? '<span class="sel ok">sim</span>'
      : '<span class="sel neutro">não</span>') + '</td>';

  if (col === "estado") {
    const c = v === "coberta" ? "ok" : v === "ausente" ? "mau" : "meio";
    return \`<td><span class="sel \${c}">\${esc(v)}</span></td>\`;
  }

  if (col === "tipo")
    return \`<td><span class="sel neutro">\${esc(v)}</span></td>\`;

  // as seccoes vinham coladas: "4.2,4.4,5.2". Uma etiqueta por seccao.
  if (col === "seccoes" || col === "seccao")
    return "<td>" + String(v).split(/[,;]\\s*/).filter(Boolean)
      .map(s => \`<span class="seccao">\${esc(s.trim())}</span>\`).join("") + "</td>";

  if (typeof v === "number")
    return \`<td class="num">\${num(v)}</td>\`;

  return \`<td class="\${MONO.has(col) ? "mono" : ""}">\${esc(v)}</td>\`;
}
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

/**
 * Uma tabela a partir de uma lista de objectos.
 *
 * 'destino' recebe uma linha e devolve o endereco que ela abre, ou null se
 * nao abrir nada. Assim a regra e' dos dados e nao de quem chama: uma linha
 * com ficheiro abre o documento, uma linha com nome de substancia abre a
 * substancia, e as restantes ficam quietas.
 */
function destinoDe(l) {
  if (l.ficheiro) return "/api/documento/" + encodeURIComponent(l.ficheiro);
  if (l.nome && l.cui !== undefined)
    return "/api/substancia/" + encodeURIComponent(l.nome);
  return null;
}

function tabela(linhas, comLigacoes = false) {
  if (!linhas || !linhas.length)
    return '<p class="contagem">Sem resultados.</p>';
  // ordem_tipo so serve para ordenar do lado do servidor; nao se mostra.
  const cols = [...new Set(linhas.flatMap(Object.keys))]
    .filter(c => c !== "ordem_tipo");
  const destinos = comLigacoes ? linhas.map(destinoDe) : linhas.map(() => null);
  const algum = destinos.some(Boolean);
  return '<div class="rolo"><table><thead><tr>'
    + cols.map(c => \`<th>\${esc(c.replace(/_/g, " "))}</th>\`).join("")
    + (algum ? "<th></th>" : "")
    + "</tr></thead><tbody>"
    + linhas.map((l, i) => \`<tr\${destinos[i] ? \` class="abre" data-url="\${esc(destinos[i])}"\` : ""}>\`
        + cols.map(c => celula(c, l[c])).join("")
        // A linha toda abre, mas sem um botao visivel ninguem adivinha que
        // abre. O botao e' a pista; o clique na linha e' a rede de seguranca.
        + (algum ? '<td class="accao">'
             + (destinos[i] ? '<button class="info">+ info</button>' : "")
             + "</td>" : "")
        + "</tr>").join("")
    + "</tbody></table></div>"
    + \`<p class="contagem">\${linhas.length.toLocaleString("pt-PT")}\`
    + \` \${linhas.length === 1 ? "linha" : "linhas"}.</p>\`;
}

/**
 * Cobertura gene a gene, em barras empilhadas. SVG escrito a mao: uma
 * biblioteca de graficos por um grafico so seria mais codigo do que isto, e
 * ficava presa a um CDN que tem de continuar a existir daqui a anos.
 *
 * Cada barra e' um gene: a largura total sao as posicoes em que a guideline
 * o exige, a parte verde as que o rotulo cobre, a vermelha as que faltam.
 */
function grafico(genes) {
  const top = genes.slice(0, 12);
  const max = Math.max(...top.map(g => g.exigido_em));
  const L = 92, R = 58, alt = 26, topo = 8;   // margens e passo
  const larg = 700, util = larg - L - R;
  const altura = topo + top.length * alt + 4;

  const barras = top.map((g, i) => {
    const y = topo + i * alt;
    const w = Math.max(1, g.exigido_em / max * util);
    const wc = g.exigido_em ? w * (g.coberto_em / g.exigido_em) : 0;
    const pct = g.pct_coberto;
    return \`<g class="barra" data-gene="\${esc(g.gene)}">
      <title>\${esc(g.gene)}: exigido em \${num(g.exigido_em)} posições, \${num(g.coberto_em)} cobertas, \${num(g.ausente_em)} em falta</title>
      <text class="g-nome" x="\${L - 8}" y="\${y + 13}" text-anchor="end">\${esc(g.gene)}</text>
      <rect class="fundo" x="\${L}" y="\${y + 3}" width="\${w}" height="14" rx="3"
            fill="#f7ccc7" stroke="none"/>
      <rect x="\${L}" y="\${y + 3}" width="\${wc}" height="14" rx="3" fill="#a9d8b8"/>
      <text class="g-val" x="\${L + w + 7}" y="\${y + 14}">\${pct}\u2009%</text>
    </g>\`;
  }).join("");

  return \`<div class="grafico">
    <svg viewBox="0 0 \${larg} \${altura}" role="img"
         aria-label="Cobertura das guidelines por gene">\${barras}</svg>
    <div class="legenda">
      <span><i style="background:#a9d8b8"></i>o rótulo nomeia o gene</span>
      <span><i style="background:#f7ccc7"></i>não nomeia</span>
      <span>largura = número de rótulos em que uma guideline o exige</span>
      <button class="alternar" id="alternar">ver como tabela</button>
    </div>
  </div>\`;
}

function mostrar(dados, url) {
  caixaU.textContent = new URL(url, location.origin).href;

  // Detalhe de uma substancia: sao tres listas e nao uma. Mostrar so a
  // primeira deixava a pergunta "que documentos tem esta substancia" sem
  // resposta, que foi o que aconteceu ao procurar siponimod.
  if (dados.substancia) {
    const s = dados.substancia;
    saida.innerHTML =
      \`<div class="bloco"><h3>\${esc(s.nome)}</h3>\`
      + \`<p class="contagem">UMLS \${esc(s.cui)} · DrugBank \${esc(s.drugbank)}\`
      + \` · MeSH \${esc(s.mesh)}\${s.aliases ? " · também: " + esc(s.aliases) : ""}</p>\`
      + "<h3>Documentos</h3>" + tabela(dados.documentos, true)
      + "<h3>Entidades extraídas</h3>" + tabela(dados.entidades)
      + "<h3>Cobertura de guidelines</h3>" + tabela(dados.cobertura)
      + '<button class="voltar" id="voltar">Voltar à procura</button></div>';
    const v = document.getElementById("voltar");
    if (v) v.addEventListener("click", voltar);
    ligarLinhas();
    return;
  }

  if (dados.documento) {
    const d = dados.documento;
    saida.innerHTML =
      \`<div class="bloco"><h3>\${esc(d.medicamento || d.ficheiro)}</h3>\`
      + \`<p class="contagem">\${esc(d.ficheiro)}\`
      + \`\${d.substancia ? " · " + esc(d.substancia) : ""}\`
      + \`\${d.codigo_atc ? " · ATC " + esc(d.codigo_atc) : ""}</p>\`
      + "<h3>Entidades extraídas</h3>" + tabela(dados.entidades)
      + "<h3>Passagens farmacogenómicas</h3>" + tabela(dados.passagens)
      + '<button class="voltar" id="voltar">Voltar</button></div>';
    const v = document.getElementById("voltar");
    if (v) v.addEventListener("click", voltar);
    return;
  }

  const linhas = linhasDe(dados);

  // A cobertura por gene abre em grafico; a tabela fica a um clique.
  const ehCobertura = url.includes("/api/cobertura/genes")
    && linhas.length && linhas[0].pct_coberto !== undefined;
  if (ehCobertura && !verTabela) {
    saida.innerHTML = grafico(linhas);
    const alt = document.getElementById("alternar");
    if (alt) alt.addEventListener("click", () => {
      verTabela = true; mostrar(dados, url);
    });
    // O destino de uma barra e' a cobertura daquele gene, nao as suas
    // mencoes. Num grafico de cobertura a pergunta seguinte e' "que rotulos
    // deviam nomea-lo", e essa tem resposta para os 38 genes; as mencoes so
    // existem para os que chegaram a ser extraidos, e genes como o HMGCR ou
    // o SLC6A4 --- precisamente os que estao a zero, e os mais interessantes
    // de abrir --- davam um beco sem saida.
    saida.querySelectorAll("g.barra").forEach(g =>
      g.addEventListener("click", () =>
        pedir("/api/cobertura?limite=300&gene=" + encodeURIComponent(g.dataset.gene))));
    return;
  }

  saida.innerHTML = tabela(linhas, true);
  ligarLinhas();
  if (ehCobertura) {
    const b = document.createElement("button");
    b.className = "alternar"; b.textContent = "ver como gráfico";
    b.style.marginTop = "10px"; b.style.display = "block";
    b.addEventListener("click", () => { verTabela = false; mostrar(dados, url); });
    saida.appendChild(b);
  }

}

/** Liga o clique de todas as linhas que tenham destino. */
function ligarLinhas() {
  saida.querySelectorAll("tr.abre").forEach(tr =>
    tr.addEventListener("click", () => pedir(tr.dataset.url)));
}

let ultimaProcura = null;
let verTabela = false;   // a cobertura por gene abre em grafico

// Pilha de onde se veio. O history.back() do browser nao serve: nunca
// empurramos estados para la, e mesmo que empurrassemos levava quem entrou
// directamente no endereco para fora do sitio.
const anteriores = [];
let urlActual = null;

function voltar() {
  const anterior = anteriores.pop();
  if (anterior) pedir(anterior, false);
  else inicio();
}

/** Estado inicial da pagina, para onde o logotipo volta. */
function inicio() {
  verTabela = false;
  anteriores.length = 0;
  document.getElementById("q").value = "";
  document.getElementById("g").value = "";
  urlActual = null;
  pedir("/api/cobertura/genes", false);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function pedir(url, guardar = true) {
  if (url.startsWith("/api/substancias")) ultimaProcura = url;
  if (guardar && urlActual && urlActual !== url) anteriores.push(urlActual);
  urlActual = url;
  saida.innerHTML = '<p class="contagem">A consultar…</p>';
  caixaU.textContent = "";
  try {
    const resposta = await fetch(url);
    const dados = await resposta.json();
    if (dados.erro) {
      saida.innerHTML = \`<p class="contagem">\${esc(dados.erro)}</p>\`
        + '<button class="voltar" id="voltar">Voltar</button>';
      const v = document.getElementById("voltar");
      if (v) v.addEventListener("click", voltar);
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

document.querySelector(".logo").addEventListener("click", inicio);
inicio();
</script>
</body>
</html>`;
