-- Esquema da base de dados farmacogenomica extraida dos RCM portugueses.
--
-- SQLite, e nao PostgreSQL, por uma razao de longevidade: o ficheiro .db e
-- estatico, cabe no GitHub Pages, nao precisa de servidor e continua a
-- funcionar quando o plano gratuito de um alojamento qualquer mudar de
-- condicoes. Com 13 mil linhas e 2,5 MB, um servidor seria infraestrutura
-- para nada.
--
-- Povoado a partir dos Document_Unique_PGx.json produzidos pelo pipeline.
-- O JSON continua a ser a saida primaria; esta base e a forma consultavel
-- da mesma informacao.
--
-- Tres decisoes de desenho:
--
-- 1. A substancia e tabela propria. O MeSH, o DrugBank e o CUI sao
--    propriedades do farmaco e nao do rotulo: varios documentos partilham
--    substancia, e repeti-los convidaria a que divergissem.
--
-- 2. A entidade guarda o gene a que pertence. CYP2C19*2 e um alelo de
--    CYP2C19, e sem essa coluna qualquer pergunta por gene teria de
--    interpretar a cadeia de caracteres em tempo de consulta.
--
-- 3. A passagem e por seccao e nao por entidade, porque e assim que o
--    pipeline a produz: o modelo extrai o trecho farmacogenomico de cada
--    seccao normativa, e as entidades sao reconhecidas dentro dele. Ligar a
--    passagem a uma so entidade seria inventar uma correspondencia que a
--    extraccao nao estabelece.

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS entidade_completa;
DROP TABLE IF EXISTS cobertura;
DROP TABLE IF EXISTS passagem;
DROP TABLE IF EXISTS entidade_seccao;
DROP TABLE IF EXISTS entidade;
DROP TABLE IF EXISTS documento;
DROP TABLE IF EXISTS guideline;
DROP TABLE IF EXISTS substancia;


CREATE TABLE substancia (
    id        INTEGER PRIMARY KEY,
    nome      TEXT NOT NULL UNIQUE,
    cui       TEXT,      -- UMLS, presente em 100% das substancias
    drugbank  TEXT,      -- 89%
    mesh      TEXT,      -- 63%
    aliases   TEXT       -- lista separada por " ; "
);

CREATE TABLE documento (
    id              INTEGER PRIMARY KEY,
    ficheiro        TEXT NOT NULL UNIQUE,
    medicamento     TEXT,
    substancia_id   INTEGER REFERENCES substancia(id),
    codigo_atc      TEXT,
    grupo_codigo    TEXT,   -- classificacao portuguesa, quando presente
    grupo_nome      TEXT,
    tem_pgx         INTEGER NOT NULL DEFAULT 0,
    tem_entidades   INTEGER NOT NULL DEFAULT 0,
    versao_pipeline TEXT,
    modelo          TEXT,
    processado_em   TEXT
);

-- Uma linha por documento e entidade. As mencoes sao as do DOCUMENTO.
--
-- A versao anterior tinha aqui uma coluna 'seccao' e escrevia uma linha por
-- seccao, repetindo em cada uma o total do documento. SUM(mencoes) contava
-- entao a dobrar ou a triplicar: uma entidade nomeada 4 vezes e espalhada
-- por tres seccoes aparecia como 12. Dava 9 570 mencoes no corpus, contra as
-- 5 885 que o pipeline conta. As seccoes passaram para a tabela abaixo.
CREATE TABLE entidade (
    id            INTEGER PRIMARY KEY,
    documento_id  INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL
                  CHECK (tipo IN ('gene','alelo','diplotipo','rsid')),
    valor         TEXT NOT NULL,
    gene          TEXT,
    mencoes       INTEGER NOT NULL DEFAULT 1,
    pharmgkb_id   TEXT,
    ncbi_gene_id  TEXT,
    hgnc_id       TEXT,
    guideline_ids TEXT,          -- lista separada por " ; "
    UNIQUE (documento_id, tipo, valor)
);

-- Em que seccoes a entidade ocorre, e quantas vezes em cada uma. As
-- entidades sao lidas seccao a seccao, por isso a contagem e real e nao
-- estimada: SUM(mencoes) aqui reproduz entidade.mencoes.
CREATE TABLE entidade_seccao (
    entidade_id   INTEGER NOT NULL REFERENCES entidade(id) ON DELETE CASCADE,
    seccao        TEXT NOT NULL,
    mencoes       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (entidade_id, seccao)
);
CREATE INDEX idx_entidade_seccao ON entidade_seccao(seccao);

-- O trecho farmacogenomico que o modelo extraiu de cada seccao normativa.
-- E a prova textual: qualquer entidade da mesma seccao e sustentada por ele.
CREATE TABLE passagem (
    id            INTEGER PRIMARY KEY,
    documento_id  INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    seccao        TEXT NOT NULL,
    texto         TEXT NOT NULL,
    UNIQUE (documento_id, seccao)
);

CREATE TABLE guideline (
    id            INTEGER PRIMARY KEY,
    guideline_id  TEXT NOT NULL,   -- identificador ClinPGx, ex. PA166104931
    fonte         TEXT NOT NULL,   -- CPIC, DPWG, RNPGx, ...
    farmaco       TEXT NOT NULL,
    gene          TEXT NOT NULL,
    UNIQUE (guideline_id, farmaco, gene)
);

CREATE TABLE cobertura (
    documento_id   INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    guideline_id   INTEGER NOT NULL REFERENCES guideline(id) ON DELETE CASCADE,
    estado         TEXT NOT NULL
                   CHECK (estado IN ('coberta','parcial','ausente')),
    genes_em_falta TEXT,
    PRIMARY KEY (documento_id, guideline_id)
);


CREATE INDEX idx_entidade_gene   ON entidade (gene);
CREATE INDEX idx_entidade_valor  ON entidade (valor);
CREATE INDEX idx_entidade_tipo   ON entidade (tipo);
CREATE INDEX idx_documento_atc   ON documento (codigo_atc);
CREATE INDEX idx_documento_subst ON documento (substancia_id);
CREATE INDEX idx_substancia_cui  ON substancia (cui);
CREATE INDEX idx_guideline_gene  ON guideline (gene);


-- Vista de conveniencia: uma linha por entidade com o contexto todo.
-- E daqui que a maioria das perguntas parte, por isso existe.
CREATE VIEW entidade_completa AS
SELECT e.id,
       e.tipo,
       e.valor,
       e.gene,
       -- as seccoes onde ocorre, juntas numa so celula para a vista
       -- continuar a ter uma linha por entidade
       (SELECT GROUP_CONCAT(es.seccao, ' ; ')
          FROM entidade_seccao es WHERE es.entidade_id = e.id) AS seccoes,
       e.mencoes,
       d.ficheiro,
       d.medicamento,
       d.codigo_atc,
       d.grupo_codigo,
       s.nome     AS substancia,
       s.cui,
       s.drugbank
FROM entidade e
JOIN documento d       ON d.id = e.documento_id
LEFT JOIN substancia s ON s.id = d.substancia_id;
