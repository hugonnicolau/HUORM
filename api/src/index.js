/**
 * HUORM — API de consulta da informacao farmacogenomica dos RCM portugueses.
 *
 * Cloudflare Worker sobre D1. O D1 e SQLite gerido; a base e a mesma que o
 * construir_bd.py produz, exportada pelo exportar_para_d1.py.
 *
 * Porque e que isto existe, havendo ja a pagina de consulta: a pagina
 * descarrega o ficheiro inteiro e corre SQL no browser, o que serve uma
 * pessoa a olhar para o ecra mas nao serve outro programa. Aqui ha
 * endpoints com parametros, resposta em JSON e CORS aberto, que e o que
 * permite a um sistema de prescricao, a um script de investigacao ou a um
 * notebook perguntarem alguma coisa a base.
 *
 * Todas as consultas sao preparadas com bind(). Nenhum valor vindo do
 * pedido e concatenado para dentro de SQL.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (dados, estado = 200) =>
  new Response(JSON.stringify(dados, null, 2), {
    status: estado,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      // 60 segundos, nao uma hora.
      //
      // Com max-age=3600 a Cloudflare guardava a resposta a saida e, depois
      // de recarregar o D1, o endereco continuava a servir os numeros
      // antigos ate a hora passar — bastava acrescentar um parametro
      // qualquer ao URL para ver os novos. Numa base que acompanha uma tese
      // isso e' pior do que nao ter cache: quem confere um numero contra o
      // capitulo 4 ve uma discrepancia que nao existe.
      "Cache-Control": "public, max-age=60",
      ...CORS,
    },
  });

const erro = (mensagem, estado = 400) => json({ erro: mensagem }, estado);

/** Limite de linhas: por omissao 100, nunca acima de 1000. */
function limite(url) {
  const n = parseInt(url.searchParams.get("limite") ?? "100", 10);
  if (Number.isNaN(n) || n < 1) return 100;
  return Math.min(n, 1000);
}

// ---------------------------------------------------------------------
// Indice: a raiz descreve-se a si propria, para a API ser explorável sem
// documentacao a parte.
// ---------------------------------------------------------------------
const INDICE = {
  nome: "HUORM API",
  descricao:
    "Informacao farmacogenomica extraida dos Resumos das Caracteristicas " +
    "do Medicamento portugueses (INFOMED).",
  endpoints: {
    "/api/estatisticas": "contagens globais do corpus",
    "/api/substancias?q=&limite=": "procurar substancias pelo nome ou alias",
    "/api/substancia/:nome": "uma substancia, com identificadores, entidades e cobertura",
    "/api/genes?limite=": "genes por numero de mencoes",
    "/api/gene/:simbolo?limite=": "documentos que mencionam um gene",
    "/api/cobertura?gene=&estado=&fonte=&limite=":
      "cobertura de guidelines; estado e 'coberta' ou 'ausente'",
    "/api/cobertura/genes": "resumo por gene: quantas vezes exigido, quantas em falta",
    "/api/documento/:ficheiro": "um documento, com entidades e passagens",
    "/api/seccoes": "distribuicao das entidades pelas seccoes normativas",
  },
  notas: [
    "Todas as respostas sao JSON. CORS aberto.",
    "'limite' aceita ate 1000; por omissao 100.",
    "Dados imutaveis: correspondem a uma corrida datada do pipeline.",
  ],
};

// ---------------------------------------------------------------------
async function rotear(url, db) {
  const p = url.pathname.replace(/\/+$/, "") || "/";
  const lim = limite(url);

  if (p === "/" || p === "/api") return json(INDICE);

  if (p === "/api/estatisticas") {
    const r = await db
      .prepare(
        `SELECT (SELECT COUNT(*) FROM documento)                      AS documentos,
                (SELECT COUNT(*) FROM substancia)                     AS substancias,
                (SELECT COUNT(*) FROM entidade)                       AS entidades,
                (SELECT SUM(mencoes) FROM entidade)                   AS mencoes,
                (SELECT COUNT(*) FROM passagem)                       AS passagens,
                (SELECT COUNT(*) FROM documento WHERE tem_pgx = 1)    AS documentos_com_pgx,
                (SELECT COUNT(DISTINCT guideline_id) FROM guideline)  AS guidelines,
                (SELECT COUNT(*) FROM cobertura WHERE estado='ausente') AS posicoes_em_falta`
      )
      .first();
    return json(r);
  }

  if (p === "/api/substancias") {
    const q = (url.searchParams.get("q") ?? "").trim();
    const { results } = q
      ? await db
          .prepare(
            `SELECT s.nome, s.cui, s.drugbank, s.mesh,
                    COUNT(d.id) AS documentos
               FROM substancia s
               LEFT JOIN documento d ON d.substancia_id = s.id
              WHERE s.nome LIKE ?1 OR s.aliases LIKE ?1
              GROUP BY s.id ORDER BY documentos DESC LIMIT ?2`
          )
          .bind(`%${q}%`, lim)
          .all()
      : await db
          .prepare(
            `SELECT s.nome, s.cui, s.drugbank, s.mesh,
                    COUNT(d.id) AS documentos
               FROM substancia s
               LEFT JOIN documento d ON d.substancia_id = s.id
              GROUP BY s.id ORDER BY documentos DESC LIMIT ?1`
          )
          .bind(lim)
          .all();
    return json({ total: results.length, substancias: results });
  }

  let m;
  if ((m = p.match(/^\/api\/substancia\/(.+)$/))) {
    const nome = decodeURIComponent(m[1]).toLowerCase();
    const s = await db
      .prepare("SELECT * FROM substancia WHERE nome = ?1")
      .bind(nome)
      .first();
    if (!s) return erro(`substancia nao encontrada: ${nome}`, 404);

    const [docs, ents, cob] = await Promise.all([
      db.prepare(
        `SELECT ficheiro, medicamento, codigo_atc, tem_pgx, tem_entidades
           FROM documento WHERE substancia_id = ?1 ORDER BY ficheiro`
      ).bind(s.id).all(),
      db.prepare(
        `SELECT e.tipo, e.valor, e.gene, SUM(e.mencoes) AS mencoes,
                (SELECT GROUP_CONCAT(DISTINCT es.seccao)
                   FROM entidade_seccao es WHERE es.entidade_id = e.id) AS seccoes
           FROM entidade e JOIN documento d ON d.id = e.documento_id
          WHERE d.substancia_id = ?1
          GROUP BY e.tipo, e.valor, e.gene
          ORDER BY mencoes DESC`
      ).bind(s.id).all(),
      db.prepare(
        `SELECT g.guideline_id, g.fonte, g.gene, c.estado,
                COUNT(DISTINCT d.id) AS documentos
           FROM cobertura c
           JOIN guideline g ON g.id = c.guideline_id
           JOIN documento d ON d.id = c.documento_id
          WHERE d.substancia_id = ?1
          GROUP BY g.guideline_id, g.fonte, g.gene, c.estado
          ORDER BY g.gene`
      ).bind(s.id).all(),
    ]);

    return json({
      substancia: { nome: s.nome, cui: s.cui, drugbank: s.drugbank,
                    mesh: s.mesh, aliases: s.aliases },
      documentos: docs.results,
      entidades: ents.results,
      cobertura: cob.results,
    });
  }

  if (p === "/api/genes") {
    const { results } = await db
      .prepare(
        `SELECT gene, COUNT(DISTINCT documento_id) AS documentos,
                SUM(mencoes) AS mencoes
           FROM entidade WHERE gene IS NOT NULL
          GROUP BY gene ORDER BY mencoes DESC LIMIT ?1`
      )
      .bind(lim)
      .all();
    return json({ total: results.length, genes: results });
  }

  if ((m = p.match(/^\/api\/gene\/(.+)$/))) {
    const gene = decodeURIComponent(m[1]).toUpperCase();
    const { results } = await db
      .prepare(
        `SELECT d.ficheiro, d.medicamento, s.nome AS substancia,
                e.tipo, e.valor, e.mencoes,
                (SELECT GROUP_CONCAT(DISTINCT es.seccao)
                   FROM entidade_seccao es WHERE es.entidade_id = e.id) AS seccoes
           FROM entidade e
           JOIN documento d  ON d.id = e.documento_id
           LEFT JOIN substancia s ON s.id = d.substancia_id
          WHERE e.gene = ?1
          ORDER BY e.mencoes DESC LIMIT ?2`
      )
      .bind(gene, lim)
      .all();
    if (!results.length) return erro(`sem mencoes do gene ${gene}`, 404);
    return json({ gene, total: results.length, mencoes: results });
  }

  if (p === "/api/cobertura") {
    const gene = url.searchParams.get("gene");
    const estado = url.searchParams.get("estado");
    const fonte = url.searchParams.get("fonte");
    if (estado && !["coberta", "ausente"].includes(estado))
      return erro("estado tem de ser 'coberta' ou 'ausente'");

    const { results } = await db
      .prepare(
        `SELECT s.nome AS substancia, g.gene, g.fonte, g.guideline_id,
                c.estado, COUNT(DISTINCT d.id) AS rotulos
           FROM cobertura c
           JOIN guideline g  ON g.id = c.guideline_id
           JOIN documento d  ON d.id = c.documento_id
           LEFT JOIN substancia s ON s.id = d.substancia_id
          WHERE (?1 IS NULL OR g.gene   = ?1)
            AND (?2 IS NULL OR c.estado = ?2)
            AND (?3 IS NULL OR g.fonte  = ?3)
          GROUP BY s.nome, g.gene, g.fonte, g.guideline_id, c.estado
          ORDER BY rotulos DESC LIMIT ?4`
      )
      .bind(gene ? gene.toUpperCase() : null, estado, fonte, lim)
      .all();
    return json({
      filtros: { gene, estado, fonte },
      total: results.length,
      cobertura: results,
    });
  }

  if (p === "/api/cobertura/genes") {
    const { results } = await db
      .prepare(
        `SELECT g.gene,
                COUNT(*)                                              AS exigido_em,
                SUM(CASE WHEN c.estado='coberta' THEN 1 ELSE 0 END)   AS coberto_em,
                SUM(CASE WHEN c.estado='ausente' THEN 1 ELSE 0 END)   AS ausente_em,
                ROUND(100.0 * SUM(CASE WHEN c.estado='coberta' THEN 1 ELSE 0 END)
                      / COUNT(*), 1)                                  AS pct_coberto
           FROM cobertura c JOIN guideline g ON g.id = c.guideline_id
          GROUP BY g.gene ORDER BY exigido_em DESC`
      )
      .all();
    return json({ total: results.length, genes: results });
  }

  if ((m = p.match(/^\/api\/documento\/(.+)$/))) {
    const fich = decodeURIComponent(m[1]);
    const d = await db
      .prepare(
        `SELECT d.*, s.nome AS substancia, s.cui, s.drugbank, s.mesh
           FROM documento d LEFT JOIN substancia s ON s.id = d.substancia_id
          WHERE d.ficheiro = ?1`
      )
      .bind(fich)
      .first();
    if (!d) return erro(`documento nao encontrado: ${fich}`, 404);

    const [ents, pass] = await Promise.all([
      db.prepare(
        `SELECT e.tipo, e.valor, e.gene, e.mencoes, e.pharmgkb_id,
                e.guideline_ids,
                (SELECT GROUP_CONCAT(DISTINCT es.seccao)
                   FROM entidade_seccao es WHERE es.entidade_id = e.id) AS seccoes
           FROM entidade e WHERE e.documento_id = ?1 ORDER BY e.mencoes DESC`
      ).bind(d.id).all(),
      db.prepare(
        "SELECT seccao, texto FROM passagem WHERE documento_id = ?1 ORDER BY seccao"
      ).bind(d.id).all(),
    ]);
    return json({ documento: d, entidades: ents.results, passagens: pass.results });
  }

  if (p === "/api/seccoes") {
    const { results } = await db
      .prepare(
        `SELECT es.seccao,
                COUNT(*)                           AS entidades,
                SUM(es.mencoes)                    AS mencoes,
                COUNT(DISTINCT e.documento_id)     AS documentos
           FROM entidade_seccao es
           JOIN entidade e ON e.id = es.entidade_id
          GROUP BY es.seccao ORDER BY mencoes DESC`
      )
      .all();
    return json({ seccoes: results });
  }

  return erro(`endpoint desconhecido: ${p}. Ver / para a lista.`, 404);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS")
      return new Response(null, { status: 204, headers: CORS });
    if (request.method !== "GET")
      return erro("apenas GET", 405);

    try {
      return await rotear(new URL(request.url), env.DB);
    } catch (e) {
      // A mensagem do D1 pode conter o SQL; nao vai para o cliente.
      console.error(e);
      return erro("erro interno ao consultar a base", 500);
    }
  },
};
