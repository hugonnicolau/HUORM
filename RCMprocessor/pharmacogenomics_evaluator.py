import os
import html
import json
import random
import time
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict
from dotenv import load_dotenv
from ollama import Client

from .markdown_processor import MarkdownProcessor
from .genes_lookup import GenesLookup
from .clinical_variants_lookup import ClinicalVariantsLookup

load_dotenv()


class PharmacogenomicsEvaluator:
    """
    Pipeline principal de avaliação farmacogenómica.

    Responsabilidades:
    - Classificar se cada secção contém informação PGx.
    - Extrair excertos PGx.
    - Extrair genes, star alleles, diplótipos e rsIDs com apoio do modelo.
    - Validar/normalizar entidades com fontes locais ClinPGx/PharmGKB.
    - Contabilizar entidades únicas e menções totais reais.
    - Gerar outputs legíveis:
        - Extended_PGx_Analysis.json: auditoria/resumo do documento
        - Document_Unique_PGx.json: entidades finais, IDs principais e contagens
    """

    def __init__(self, model: str):
        self.model = model

        # O timeout não é opcional numa corrida de dias.
        #
        # Sem ele, um pedido que fica pendurado fica pendurado para sempre: o
        # cliente espera, o backoff nunca é accionado porque não há excepção, e
        # o processo pára sem gastar CPU e sem escrever nada. Aconteceu a
        # 15-09-2026 — um documento ficou mais de uma hora parado com o socket
        # para o ollama.com estabelecido e inactivo, enquanto o resto do lote
        # não avançava. Num corpus de milhares de documentos processado ao
        # longo de dias, um pedido pendurado deita fora tudo o que vinha a
        # seguir.
        self.client = Client(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"},
            timeout=self.LLM_TIMEOUT,
        )

        base_dir = Path(__file__).resolve().parent
        genes_path = self._first_existing_path([
            base_dir / "data" / "clinpgx" / "genes.tsv",
            base_dir / "genes.tsv",
        ])
        vars_path = self._first_existing_path([
            base_dir / "data" / "clinpgx" / "clinicalVariants.tsv",
            base_dir / "clinicalVariants.tsv",
        ])

        self.genes = GenesLookup(genes_path)
        self.clinvars = ClinicalVariantsLookup(vars_path)

        self.prompt_base = """
O texto abaixo pertence a um RCM (Resumo das Características do Medicamento).

Quero que avalies apenas se existe informação FARMACOGENÓMICA ou FARMACOGENÉTICA
relacionada com a resposta ao medicamento.

Responde apenas com:
- "Sim"
ou
- "Não"

Considera como informação relevante apenas referências a:
- genes, variantes, alelos, diplótipos, genótipos ou fenótipos metabólicos que influenciem a resposta ao medicamento;
- enzimas, transportadores ou proteínas envolvidos no metabolismo, transporte ou ação do medicamento, quando associados a variabilidade genética;
- diferenças de eficácia, segurança, toxicidade ou metabolismo em função do genótipo/fenótipo;
- necessidade de genotipagem ou teste genético antes ou durante o tratamento;
- ajuste de dose, contraindicação, precaução ou recomendação clínica baseada em genética/farmacogenómica;
- star alleles, diplótipos, rsIDs ou variantes com impacto farmacológico.

NÃO consideres como suficiente:
- referências a doenças hereditárias ou genética de base que não influenciem a utilização do medicamento;
- referências genéticas gerais sem ligação à resposta ao medicamento;
- biologia molecular/genética sem relevância farmacológica.

Texto:
{texto}
"""

        self.prompt_extracao = """
Recebes um bloco de texto já segmentado de um RCM.

A tua tarefa é extrair, SEM REFORMULAR, SEM RESUMIR e SEM TRADUZIR, todos os excertos contínuos que contenham informação FARMACOGENÓMICA ou FARMACOGENÉTICA relevante para a resposta ao medicamento.

Regras obrigatórias:
- Mantém sempre o texto original exatamente como está.
- Não traduzas.
- Não mudes a língua.
- Não corrijas estilo, gramática ou formatação.
- Não resumas.
- Não expliques.
- Não acrescentes texto novo.

O que deves extrair:
- Extrai o excerto completo e contínuo que pertence ao mesmo tema farmacogenómico.
- Se uma frase mencionar um gene, alelo, genótipo, fenótipo, variante, teste genético ou recomendação farmacogenómica, inclui também as frases seguintes que continuem esse mesmo tema.
- Não pares a extração apenas porque uma frase seguinte já não repete explicitamente o nome do gene ou alelo.
- Continua a extrair enquanto o texto mantiver relação direta com a mesma informação farmacogenómica.
- Se dentro do mesmo bloco houver mais do que um subtópico farmacogenómico consecutivo, inclui todos se forem relevantes.
- Se existirem vários excertos PGx separados por texto não relacionado, devolve-os como lista separada.

Critérios de inclusão:
- genes, variantes, alelos, diplótipos, genótipos ou fenótipos metabólicos com impacto na resposta ao medicamento;
- star alleles, diplótipos ou rsIDs com relevância clínica;
- necessidade de teste genético ou genotipagem;
- recomendação clínica, ajuste posológico, contraindicação, precaução ou evicção baseada em genética;
- risco de segurança, toxicidade, eficácia ou metabolismo associado a uma entidade genética;
- prevalência/frequência de alelos quando ligada a risco, teste, tratamento ou decisão clínica.

Critérios de exclusão:
- metabolismo, inibição, indução ou interação medicamentosa sem contexto genético/farmacogenómico;
- genética geral sem relação com resposta ao medicamento;
- doenças hereditárias sem implicação na utilização do medicamento.

Responde apenas em JSON válido com esta estrutura:

{{
  "excertos": [
    {{
      "texto_original": "...",
      "motivo_extracao": "..."
    }}
  ]
}}

Se não houver informação farmacogenómica relevante, responde:

{{
  "excertos": []
}}

Texto:
{texto}
"""

        self.prompt_substancia_ativa = """
O texto abaixo corresponde à secção 2 de um RCM (Composição qualitativa e quantitativa).

Identifica apenas a substância ativa principal do medicamento.

Regras obrigatórias:
- Responde apenas em JSON válido.
- Usa exatamente esta estrutura:
{{
  "encontrada": "Sim" ou "Não",
  "substancia_ativa": "..."
}}
- No campo "substancia_ativa" devolve apenas o nome da substância ativa.
- NÃO incluas dosagem, concentração, unidades, forma farmacêutica, salvo se fizer parte inseparável do nome.
- Se existirem várias substâncias ativas, devolve apenas os nomes, separados por " + ".
- Não expliques.
- Não adiciones texto fora do JSON.

Texto:
{texto}
"""

        self.prompt_aliases_substancia = """
Recebes o nome de uma substância ativa em português, extraída de um RCM português.

Traduz apenas o nome da substância ativa para inglês, para permitir matching com bases de dados em inglês.

Regras obrigatórias:
- Responde apenas em JSON válido.
- Usa exatamente esta estrutura:
{{
  "aliases": ["..."]
}}
- Inclui apenas a tradução direta de português para inglês.
- Se existirem várias substâncias, mantém todas e separa por " + ".
- Se o nome em inglês for igual ao português, devolve lista vazia.
- Máximo 1 alias traduzido.
- Não expliques nada.

Substância ativa:
{texto}
"""

        self.prompt_extract_entities_model = """
Recebes um excerto farmacogenómico de um RCM.

Extrai apenas entidades farmacogenómicas explicitamente presentes no texto. Não inventes entidades.
Conta quantas vezes cada entidade aparece no excerto recebido.

Responde apenas em JSON válido, exatamente neste formato:
{{
  "genes": [
    {{
      "symbol": "...",
      "original_text": "...",
      "normalized_from_full_name": true ou false,
      "total_mentions": 1
    }}
  ],
  "star_alleles": [
    {{
      "raw_text": "...",
      "normalized": "...",
      "gene": "...",
      "normalization_type": "already_complete|context_reconstructed|format_corrected",
      "total_mentions": 1
    }}
  ],
  "incomplete_star_alleles": [
    {{
      "raw_text": "...",
      "reason": "missing_gene_prefix|ambiguous_context",
      "total_mentions": 1
    }}
  ],
  "diplotypes": [
    {{
      "raw_text": "...",
      "normalized": "...",
      "genes": ["..."],
      "total_mentions": 1
    }}
  ],
  "rsids": [
    {{
      "rsid": "...",
      "gene": "",
      "total_mentions": 1
    }}
  ],
  "normalizacao_tecnica": [
    {{
      "original_text": "...",
      "normalized_text": "...",
      "entity_type": "star_allele|diplotype",
      "normalization_type": "format_correction|diplotype_format_normalization",
      "total_mentions": 1,
      "included_in_entity_total": true
    }}
  ]
}}

Critérios de inclusão:
- Extrai entidades quando o excerto tiver contexto farmacogenómico/genético, como variante, alelo, diplótipo, genótipo, fenótipo metabolizador, polimorfismo, teste genético, recomendação baseada em genética, risco associado a variante/alelo, eficácia, toxicidade, segurança ou dose dependente de informação genética.
- Não extraias genes ou enzimas apenas por aparecerem em contexto geral de metabolismo, inibição, indução, substrato, coadministração, interação medicamentosa ou via enzimática, salvo se houver ligação explícita a variabilidade genética ou farmacogenómica.

Regras para genes:
- "symbol" deve conter o símbolo oficial do gene sempre que seja possível identificá-lo.
- Se o texto mencionar o gene por extenso, converte para o símbolo oficial.
- Nesse caso, coloca "original_text" com o texto original e "normalized_from_full_name": true.
- Se o texto já mencionar o símbolo oficial como gene independente, usa esse símbolo e coloca "normalized_from_full_name": false.
- Não listes como gene autónomo um símbolo que apareça apenas como prefixo/componente de um star allele, diplótipo, genótipo ou variante. Nesses casos, conta a entidade completa na categoria apropriada.
- Não trates famílias genéricas ou classes enzimáticas genéricas como genes específicos. Só extrai um gene quando o texto mencionar uma entidade genética concreta e houver contexto PGx/genético.

Regras obrigatórias para star alleles:
- Um star allele simples representa um único alelo de um gene.
- Quando o texto apresentar gene e alelo juntos, extrai sempre a expressão completa no formato GENE*ALELO.
- Nunca devolvas apenas *ALELO como star allele final se o gene estiver presente no texto.
- Se o texto contiver uma forma compacta, com espaçamento irregular ou com hífen ausente, normaliza para o formato GENE*ALELO e usa normalization_type "format_corrected".
- Se o texto só tiver o alelo isolado mas o gene puder ser reconstruído com segurança pelo contexto da mesma frase, parágrafo ou secção, devolve o alelo completo e usa normalization_type "context_reconstructed".
- Se não for possível reconstruir com segurança, coloca em "incomplete_star_alleles" e não em "star_alleles".
- Não contes separadamente o gene de um star allele, salvo se o gene também aparecer de forma independente no texto.
- Não coloques em "star_alleles" entidades que representem dois alelos do mesmo gene. Essas entidades são diplótipos.

Regras para diplotypes:
- Um diplótipo representa a combinação de dois alelos do mesmo gene.
- Extrai diplótipos completos quando apareçam.
- Se uma entidade representar dois alelos do mesmo gene, coloca-a apenas em "diplotypes" e nunca em "star_alleles".
- Formas como GENE*ALELO*ALELO, GENE*ALELO/*ALELO ou GENE *ALELO / *ALELO devem ser interpretadas como diplótipos quando representarem dois alelos.
- Para diplótipos, usa sempre como forma normalizada standard o formato compacto: GENE*ALELO*ALELO.
- Se encontrares uma combinação de dois alelos do mesmo gene no formato GENE*1/*2, normaliza para GENE*1*2.
- Se encontrares a mesma combinação em formatos equivalentes, por exemplo GENE*1*2 e GENE*1/*2, devolve apenas uma entidade em "diplotypes" com "normalized": "GENE*1*2".
- Nunca devolvas simultaneamente formas equivalentes da mesma combinação.
- Se houver várias formas equivalentes da mesma combinação no texto, soma todas em "total_mentions" da entidade normalizada.
- Mantém a forma original principal no campo "raw_text" e, quando existirem várias formas, lista-as em "observed_forms".
- Se normalizares uma forma com barra, por exemplo GENE*1/*2 → GENE*1*2, adiciona uma entrada em "normalizacao_tecnica" com entity_type "diplotype", normalization_type "diplotype_format_normalization" e included_in_entity_total true.
- Inclui o gene em "genes" dentro do objeto do diplótipo apenas quando estiver explícito ou for inferível com segurança pelo contexto.
- Não transformes diplótipos em genes isolados.
- Antes de responder, verifica se algum item colocado em "star_alleles" contém dois alelos. Se sim, move-o para "diplotypes".

Regras para rsIDs:
- Extrai apenas rsIDs explicitamente mencionados.
- Se o gene associado estiver explícito ou for inferível com segurança, preenche o campo "gene"; caso contrário, deixa vazio.
- Não transformes rsIDs em genes isolados.

Normalização:
- "normalized_from_full_name": true é exclusivo para conversões de nome extenso de gene para símbolo oficial.
- Correções de formato, espaçamento, hífen ou reconstrução contextual de alelos não contam como normalização de nome extenso para símbolo.

Consolidação obrigatória:
- Nunca devolvas a mesma entidade normalizada mais do que uma vez dentro da mesma categoria.
- Se a mesma entidade aparecer várias vezes no excerto, devolve uma única entrada com "total_mentions" igual ao número total de ocorrências.
- Se existirem formas equivalentes ou mal formatadas da mesma entidade, consolida-as numa única entidade normalizada.
- Para diplótipos, se existirem formas com e sem barra para a mesma combinação, usa a forma sem barra como entidade normalizada final e soma as menções.
- Se uma forma corrigida tecnicamente contribuir para o total, essa ocorrência deve estar incluída no "total_mentions" da entidade normalizada.
- Regista a correção técnica quando aplicável, mas não cries uma segunda entidade para a forma original.

Não incluas explicações. Não incluas texto fora do JSON.
Se uma categoria não tiver entidades, devolve lista vazia.

Texto:
{texto}
"""

        self.prompt_review_incomplete_star_alleles = """
Recebes um excerto farmacogenómico e uma lista de star alleles extraídos de forma incompleta.

Tarefa:
- Verifica se, no excerto original, existe a forma completa do alelo com gene associado.
- Corrige apenas quando o gene estiver explicitamente presente no texto ou for claro no contexto da mesma frase, parágrafo ou secção.
- A forma final deve ser GENE*ALELO.
- Não inventes correções.
- Se continuar ambíguo, mantém em "still_incomplete".

Responde apenas em JSON válido neste formato:
{{
  "corrected_star_alleles": [
    {{
      "raw_text": "...",
      "normalized": "...",
      "gene": "...",
      "normalization_type": "corrected_from_incomplete_extraction",
      "total_mentions": 1
    }}
  ],
  "still_incomplete": [
    {{
      "raw_text": "...",
      "reason": "...",
      "total_mentions": 1
    }}
  ]
}}

Excerto original:
{texto}

Star alleles incompletos:
{incompletos}
"""

    @staticmethod
    def _first_existing_path(candidates: list[Path]) -> Path:
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    # Extração tem de ser reprodutível: o default do Ollama é temperature=0.8,
    # o que fazia com que duas execuções sobre o mesmo RCM dessem contagens
    # diferentes. Num estudo isso é indefensável — é preciso poder afirmar que
    # os números se reproduzem.
    LLM_OPTIONS = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "seed": 42,
    }

    # Retentativas com backoff exponencial (ver _invoke_with_backoff)
    LLM_MAX_RETRIES = 5
    LLM_BACKOFF_BASE = 5.0
    LLM_BACKOFF_MAX = 120.0

    # Segundos por chamada. Um bloco de RCM responde em dezenas de segundos;
    # 300 s é folgado o suficiente para não abortar trabalho legítimo e curto
    # o suficiente para transformar um pedido pendurado numa excepção que o
    # backoff sabe tratar.
    LLM_TIMEOUT = 300.0

    # Um limite de pedidos não se resolve a insistir depressa. Quando o
    # serviço devolve 429, a espera parte de um valor mais alto do que a de
    # uma falha transitória qualquer.
    LLM_BACKOFF_RATE_LIMIT = 30.0

    # Erros que não vale a pena repetir: a resposta seria a mesma cinco vezes
    # seguidas. 401/403 é chave inválida ou sem permissões, 404 é modelo
    # inexistente. Falhar depressa e alto é melhor do que gastar 5 tentativas
    # e 3 minutos por bloco para chegar à mesma conclusão.
    LLM_STATUS_SEM_RETENTATIVA = frozenset({400, 401, 403, 404})

    # Versão do pipeline, registada em cada documento processado. Incrementar
    # sempre que uma alteração possa mudar os resultados — é o que permite
    # saber, mais tarde, que documentos foram produzidos com que lógica.
    PIPELINE_VERSION = "2.0.0"

    def _ollama_invoke(self, prompt: str) -> str:
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options=self.LLM_OPTIONS,
        )
        return response.get("message", {}).get("content", "") or ""

    def llm_config(self) -> dict:
        """Configuração do modelo, para registar no output e citar nos métodos."""
        return {"model": self.model, **self.LLM_OPTIONS}

    def pipeline_metadata(self) -> dict:
        """Bloco de proveniência gravado em cada documento.

        Sem isto não é possível responder a "que documentos foram processados
        com que versão do código e que configuração do modelo" — pergunta que
        um júri faz, e que num corpus de 10 400 documentos processados ao longo
        de dias é impossível reconstituir de memória.
        """
        return {
            "pipeline_version": self.PIPELINE_VERSION,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "llm": self.llm_config(),
            "block_max_chars": self.BLOCK_MAX_CHARS,
            "classification_pass": self.USE_CLASSIFICATION_PASS,
        }

    @staticmethod
    def _iter_balanced_spans(text: str, opener: str, closer: str):
        """Devolve os spans de topo equilibrados, ignorando delimitadores dentro de strings."""
        depth = 0
        start = -1
        in_string = False
        escaped = False

        for i, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == opener:
                if depth == 0:
                    start = i
                depth += 1
            elif ch == closer and depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start:i + 1]
                    start = -1

    def _extract_json_object(self, text: str):
        """Extrai o primeiro JSON válido da resposta do modelo.

        A versão anterior usava re.search(r"\\{.*\\}", DOTALL), que é guloso: se o
        modelo devolvesse dois objetos (o JSON pedido mais uma nota final), a
        expressão apanhava do primeiro '{' ao último '}' e o json.loads falhava.
        A resposta era descartada e o pipeline caía no fallback que guarda o
        bloco inteiro de 6000 caracteres como excerto.

        Agora percorrem-se os spans equilibrados e devolve-se o primeiro que
        seja JSON válido.
        """
        if not text:
            return None

        text = text.strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        # Cercas de markdown são o caso mais comum de ruído à volta do JSON.
        fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, flags=re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1).strip())
            except Exception:
                pass

        for opener, closer in (("{", "}"), ("[", "]")):
            for span in self._iter_balanced_spans(text, opener, closer):
                try:
                    return json.loads(span)
                except Exception:
                    continue

        return None

    def _clean_active_substance_name(self, value: str) -> str:
        if not value:
            return ""

        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"(?i)^(cada\s+[^\n,;:]+?\s+cont[eé]m\s+)", "", value).strip()
        value = re.sub(r"(?i)^(subst[aâ]ncia[s]?\s+ativa[s]?[:\s-]+)", "", value).strip()
        value = re.sub(
            r"(?i)\b\d+(?:[.,]\d+)?\s*(mg|g|mcg|µg|microgramas|ml|mg/ml|ui|unidades)\b",
            "",
            value
        ).strip()
        value = re.sub(r"\s{2,}", " ", value)
        value = re.sub(r"^[\s:;,\-.]+|[\s:;,\-.]+$", "", value)
        return value

    def extrair_substancia_ativa(self, texto_secao_2: str) -> dict:
        if not texto_secao_2 or not texto_secao_2.strip():
            return {"encontrada": "Não", "substancia_ativa": ""}

        max_retries = 5
        retry_delay = 10
        resposta_texto = ""

        for attempt in range(max_retries):
            try:
                resposta_texto = self._ollama_invoke(
                    self.prompt_substancia_ativa.format(texto=texto_secao_2)
                )
                break
            except Exception as e:
                print(f"⚠️ Erro na extração da substância ativa: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        if not resposta_texto:
            return {"encontrada": "Não", "substancia_ativa": ""}

        parsed = self._extract_json_object(resposta_texto)
        if not isinstance(parsed, dict):
            return {"encontrada": "Não", "substancia_ativa": ""}

        encontrada = str(parsed.get("encontrada", "Não")).strip()
        substancia = self._clean_active_substance_name(
            str(parsed.get("substancia_ativa", "")).strip()
        )

        if not substancia:
            encontrada = "Não"

        return {
            "encontrada": "Sim" if encontrada.lower() == "sim" and substancia else "Não",
            "substancia_ativa": substancia if substancia else ""
        }

    def gerar_aliases_substancia_ativa(self, substancia_ativa: str) -> list[str]:
        if not substancia_ativa or not substancia_ativa.strip():
            return []

        max_retries = 4
        retry_delay = 6
        resposta_texto = ""

        for attempt in range(max_retries):
            try:
                resposta_texto = self._ollama_invoke(
                    self.prompt_aliases_substancia.format(texto=substancia_ativa)
                )
                break
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        aliases = []
        parsed = self._extract_json_object(resposta_texto) if resposta_texto else None

        if isinstance(parsed, dict):
            raw_aliases = parsed.get("aliases")
            if isinstance(raw_aliases, list):
                for item in raw_aliases:
                    cleaned = self._clean_active_substance_name(str(item).strip())
                    if cleaned:
                        aliases.append(cleaned)
        elif isinstance(parsed, list):
            for item in parsed:
                cleaned = self._clean_active_substance_name(str(item).strip())
                if cleaned:
                    aliases.append(cleaned)

        original = self._clean_active_substance_name(substancia_ativa)

        final = []
        seen = set()

        for alias in aliases:
            key = alias.lower()
            if key == original.lower():
                continue
            if key not in seen:
                seen.add(key)
                final.append(alias)

        return final[:1]

    # =====================================================
    # Extração/normalização de entidades com modelo
    # =====================================================
    def _as_positive_int(self, value, default: int = 1) -> int:
        try:
            n = int(value)
            return n if n > 0 else default
        except Exception:
            return default

    def _clean_entity_value(self, value: str, uppercase: bool = True) -> str:
        if not value:
            return ""
        value = str(value).strip().strip(" ;,.")
        value = re.sub(r"\s+", "", value)
        return value.upper() if uppercase else value

    def _split_gene_from_allele(self, value: str) -> str:
        if not value or "*" not in value:
            return ""
        prefix = value.split("*", 1)[0].strip().upper()
        return prefix if prefix else ""

    def _canonical_star_allele(self, value: str) -> str:
        """Normalização técnica de formato, não extração: agrega variantes visualmente iguais.

        Exemplos: HLAB*1502 -> HLA-B*1502; HLA‐B*1502 -> HLA-B*1502.
        """
        raw = str(value or "").strip()
        if not raw:
            return ""

        raw = unicodedata.normalize("NFKC", raw)
        for ch in ["‐", "‑", "‒", "–", "—", "−"]:
            raw = raw.replace(ch, "-")
        raw = re.sub(r"\s+", "", raw).upper().strip(" ;,.")
        raw = raw.replace("HLA_", "HLA-")

        # Caso comum em RCMs/modelo: HLAB*1502 sem hífen.
        if raw.startswith("HLA") and "*" in raw and not raw.startswith("HLA-"):
            before, after = raw.split("*", 1)
            locus = before[3:]
            if locus:
                raw = f"HLA-{locus}*{after}"

        return raw

    def _canonical_entity_key(self, value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or ""))
        for ch in ["‐", "‑", "‒", "–", "—", "−"]:
            value = value.replace(ch, "-")
        return re.sub(r"\s+", "", value).upper().strip(" ;,.")

    def _canonical_text_for_counting(self, value: str) -> str:
        """Normaliza texto apenas para contagem de entidades já extraídas pelo modelo.

        Não é usado para descobrir novas entidades; serve só para contar, de forma
        robusta, ocorrências de uma entidade normalizada já aceite.

        Antes removia TODOS os espaços. Isso resolvia "CYP2D6 *1" mas colava
        tokens vizinhos ("CYP2D6*1 e CYP2C19*2" -> "CYP2D6*1ECYP2C19*2"),
        impossibilitando qualquer verificação de fronteira na contagem. Agora
        removem-se apenas os espaços adjacentes a '*' e '-', preservando os
        restantes como separadores.
        """
        value = unicodedata.normalize("NFKC", str(value or ""))
        for ch in ["‐", "‑", "‒", "–", "—", "−"]:
            value = value.replace(ch, "-")
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"\s*([*\-])\s*", r"\1", value)
        return value.upper().strip()

    def _star_allele_count_forms(self, variant: str) -> list[str]:
        canonical = self._canonical_star_allele(variant)
        if not canonical:
            return []

        forms = [canonical]

        # Variantes de escrita da mesma entidade HLA, ex. HLA-B*1502:
        #   HLAB*1502   (sem hífen)
        #   HLA B*1502  (espaço em vez de hífen, comum na extração do docling)
        # São formas de contagem de uma entidade já extraída, não extração
        # independente por regex. Cada ocorrência no texto corresponde a
        # exatamente uma destas formas, pelo que somá-las não duplica.
        #
        # A forma com espaço passou a ser necessária quando
        # _canonical_text_for_counting deixou de remover todos os espaços —
        # antes "HLA B*1502" colapsava sozinho para a forma compacta.
        if canonical.startswith("HLA-") and "*" in canonical:
            forms.append("HLA" + canonical[4:])
            forms.append("HLA " + canonical[4:])

        # Remover duplicados preservando ordem.
        out = []
        seen = set()
        for form in forms:
            key = self._canonical_text_for_counting(form)
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    # ------------------------------------------------------------------
    # Símbolos de gene que colidem com palavras portuguesas
    # ------------------------------------------------------------------
    #
    # Medido sobre 3,5 milhões de caracteres de RCM real: destes símbolos,
    # menos de metade das ocorrências aparecem sequer em maiúsculas, e as que
    # aparecem não são o gene.
    #
    #   POR   2 572 ocorrências, 3 em maiúsculas — e as 3 são "INJEÇÃO POR
    #         BÓLUS", preposição em cabeçalho de tabela
    #   AR    1 577 ocorrências, 1 em maiúsculas — "artrite reumatoide (AR)"
    #   TES   4 461 ocorrências, 0 do gene
    #
    # São todos genes verdadeiros do ClinPGx. O risco não é o modelo extraí-los
    # — o prompt exige contexto farmacogenómico — mas a CONTAGEM: bastaria uma
    # identificação legítima num documento para lhe atribuir todas as
    # preposições do texto, dezenas de menções fabricadas.
    #
    # Exigir maiúsculas não chega, como os exemplos acima mostram. É preciso
    # contexto genético na vizinhança.
    #
    # Nota: genes PGx curtos mas inequívocos — TPMT, DPYD, COMT, CFTR, MTHFR,
    # NAT2, RYR1 — não constam desta lista e não são afetados.
    AMBIGUOUS_GENE_SYMBOLS = frozenset({
        "POR", "ADO", "AR", "ADA", "INA", "DES", "PELO", "ICOS", "TES", "TAT",
        "MIA", "MICA", "PAM", "GEM", "GAL", "MAL", "SMO", "MOS", "SI", "MAX",
        "HAL", "TRA", "LIAS", "TRO", "LTA", "RIDA", "CRIPT", "RARA", "DERA",
    })

    # Vocabulário que confirma que a ocorrência é genética e não linguística.
    GENETIC_CONTEXT = re.compile(
        r"(?i)\b(gene|genes|gen[ée]tic\w*|gen[óo]tipo\w*|genotip\w*|alelo\w*|"
        r"polimorf\w*|variante\w*|muta[çc]\w*|hapl[óo]tipo\w*|dipl[óo]tipo\w*|"
        r"enzim\w*|isoenzim\w*|metaboliz\w*|expressão\s+g[ée]nica|"
        r"farmacogen\w*|codifica\w*|cromossom\w*|CYP\d[A-Z]\d+|"
        r"transportador\w*|recetor\w*\s+g[ée]nic\w*|deficiência\s+de)\b"
    )

    # Janela em torno da ocorrência onde se procura esse vocabulário.
    GENETIC_CONTEXT_WINDOW = 160

    @classmethod
    def _mention_has_genetic_context(cls, text: str, start: int, end: int) -> bool:
        """Há vocabulário genético à volta desta ocorrência?"""
        janela = text[max(0, start - cls.GENETIC_CONTEXT_WINDOW):
                      end + cls.GENETIC_CONTEXT_WINDOW]
        return bool(cls.GENETIC_CONTEXT.search(janela))

    @classmethod
    def _count_ambiguous_symbol(cls, original_text: str, symbol: str) -> int:
        """Conta um símbolo ambíguo, exigindo maiúsculas E contexto genético.

        Corre sobre o texto ORIGINAL, não sobre a forma canónica: a distinção
        entre "POR" e "por" é precisamente o que interessa preservar, e
        `_canonical_text_for_counting` apaga-a ao normalizar para maiúsculas.
        """
        if not original_text or not symbol:
            return 0

        total = 0
        for m in re.finditer(rf"\b{re.escape(symbol)}\b", original_text):
            if cls._mention_has_genetic_context(original_text, m.start(), m.end()):
                total += 1
        return total

    @staticmethod
    def _is_token_boundary(text: str, index: int) -> bool:
        """True se a posição estiver fora do texto ou não for alfanumérica."""
        if index < 0 or index >= len(text):
            return True
        return not text[index].isalnum()

    def _count_non_overlapping(self, text: str, needle: str) -> int:
        """Conta ocorrências de `needle` respeitando fronteiras de token.

        Sem a verificação de fronteira, a contagem por substring inflacionava
        alelos curtos: CYP2D6*1 é substring de CYP2D6*10, *17 e *100, por isso
        um texto com "CYP2D6*10, CYP2D6*17, CYP2D6*1, CYP2D6*100" contava 4
        menções de CYP2D6*1 quando existe apenas 1. Como CYP2D6*1 é o alelo
        selvagem e *10/*17 são dos mais frequentes, o erro atingia precisamente
        as entidades mais comuns do corpus.

        A fronteira também exclui alelos de duplicação: CYP2D6*2 não é contado
        dentro de CYP2D6*2xN, que é uma entidade distinta.
        """
        if not text or not needle:
            return 0

        count = 0
        start = 0
        while True:
            idx = text.find(needle, start)
            if idx < 0:
                break
            end = idx + len(needle)
            if self._is_token_boundary(text, idx - 1) and self._is_token_boundary(text, end):
                count += 1
            start = end
        return count

    def _count_star_allele_mentions_in_text(self, variant: str, text: str) -> tuple[int, dict[str, int]]:
        """Conta ocorrências reais de uma entidade star allele já identificada.

        Exemplo: para HLA-B*1502, conta HLA-B*1502 e a forma técnica
        equivalente HLAB*1502. A entidade final continua a ser uma só.
        """
        canonical_text = self._canonical_text_for_counting(text)
        forms = self._star_allele_count_forms(variant)
        counts = {form: self._count_non_overlapping(canonical_text, form) for form in forms}
        return sum(counts.values()), counts

    def _merge_counted_note(self, notes: list[dict], seen: dict, note: dict) -> None:
        original_text = (note.get("original_text") or "").strip()
        normalized_text = (note.get("normalized_text") or note.get("normalized_symbol") or "").strip()
        entity_type = (note.get("entity_type") or "").strip()
        if not original_text or not normalized_text:
            return

        key = (original_text.lower(), normalized_text.upper(), entity_type)
        mentions = self._as_positive_int(note.get("total_mentions"), 1)
        if key in seen:
            idx = seen[key]
            notes[idx]["total_mentions"] = int(notes[idx].get("total_mentions", 0) or 0) + mentions
            if note.get("included_in_entity_total"):
                notes[idx]["included_in_entity_total"] = True
            return

        clean = dict(note)
        clean["original_text"] = original_text
        if "normalized_symbol" in clean:
            clean["normalized_symbol"] = normalized_text
        else:
            clean["normalized_text"] = normalized_text
        clean["entity_type"] = entity_type
        clean["total_mentions"] = mentions
        seen[key] = len(notes)
        notes.append(clean)

    def _extract_entities_model(self, text: str) -> dict:
        empty = {
            "genes": [],
            "gene_normalization_notes": [],
            "star_alleles": [],
            "incomplete_star_alleles": [],
            "diplotypes": [],
            "rsids": [],
            "normalizacao_tecnica": [],
        }

        if not text or not text.strip():
            return empty

        max_retries = 5
        retry_delay = 8
        resposta_texto = ""

        for attempt in range(max_retries):
            try:
                resposta_texto = self._ollama_invoke(
                    self.prompt_extract_entities_model.format(texto=text)
                )
                break
            except Exception as e:
                print(f"⚠️ Erro na extração de entidades PGx por modelo: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        parsed = self._extract_json_object(resposta_texto) if resposta_texto else None
        if not isinstance(parsed, dict):
            return empty

        genes, notes = self._parse_gene_items(parsed.get("genes") or [])
        star_alleles, incomplete, technical_notes = self._parse_star_allele_items(
            parsed.get("star_alleles") or []
        )

        for item in parsed.get("incomplete_star_alleles") or []:
            if isinstance(item, dict):
                raw = str(item.get("raw_text") or "").strip()
                if raw:
                    incomplete.append({
                        "raw_text": raw,
                        "reason": str(item.get("reason") or "missing_gene_prefix"),
                        "total_mentions": self._as_positive_int(item.get("total_mentions"), 1),
                    })
            elif isinstance(item, str) and item.strip():
                incomplete.append({
                    "raw_text": item.strip(),
                    "reason": "missing_gene_prefix",
                    "total_mentions": 1,
                })

        if incomplete:
            reviewed = self._review_incomplete_star_alleles_model(text, incomplete)
            star_alleles.extend(reviewed.get("corrected_star_alleles") or [])
            incomplete = reviewed.get("still_incomplete") or incomplete
            for corrected in reviewed.get("corrected_star_alleles") or []:
                raw = corrected.get("raw_text") or ""
                norm = corrected.get("normalized") or ""
                if raw and norm and raw != norm:
                    technical_notes.append({
                        "original_text": raw,
                        "normalized_text": norm,
                        "entity_type": "star_allele",
                        "normalization_type": corrected.get("normalization_type") or "corrected_from_incomplete_extraction",
                        "total_mentions": self._as_positive_int(corrected.get("total_mentions"), 1),
                        "included_in_entity_total": True,
                    })

        return {
            "genes": genes,
            "gene_normalization_notes": notes,
            "star_alleles": star_alleles,
            "incomplete_star_alleles": incomplete,
            "diplotypes": self._parse_diplotype_items(parsed.get("diplotypes") or []),
            "rsids": self._parse_rsid_items(parsed.get("rsids") or []),
            "normalizacao_tecnica": technical_notes,
        }

    def _review_incomplete_star_alleles_model(self, text: str, incomplete: list[dict]) -> dict:
        if not incomplete:
            return {"corrected_star_alleles": [], "still_incomplete": []}

        max_retries = 2
        retry_delay = 4
        resposta_texto = ""

        for attempt in range(max_retries):
            try:
                resposta_texto = self._ollama_invoke(
                    self.prompt_review_incomplete_star_alleles.format(
                        texto=text,
                        incompletos=json.dumps(incomplete, ensure_ascii=False),
                    )
                )
                break
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        parsed = self._extract_json_object(resposta_texto) if resposta_texto else None
        if not isinstance(parsed, dict):
            return {"corrected_star_alleles": [], "still_incomplete": incomplete}

        corrected, still_incomplete, _technical = self._parse_star_allele_items(
            parsed.get("corrected_star_alleles") or []
        )

        final_incomplete = []
        for item in parsed.get("still_incomplete") or []:
            if isinstance(item, dict):
                raw = str(item.get("raw_text") or "").strip()
                if raw:
                    final_incomplete.append({
                        "raw_text": raw,
                        "reason": str(item.get("reason") or "missing_gene_prefix"),
                        "total_mentions": self._as_positive_int(item.get("total_mentions"), 1),
                    })
            elif isinstance(item, str) and item.strip():
                final_incomplete.append({
                    "raw_text": item.strip(),
                    "reason": "missing_gene_prefix",
                    "total_mentions": 1,
                })

        return {
            "corrected_star_alleles": corrected,
            "still_incomplete": final_incomplete,
        }

    def _parse_gene_items(self, genes_raw: list) -> tuple[list[dict], list[dict]]:
        genes = []
        notes = []

        for item in genes_raw:
            if isinstance(item, str):
                raw = item.strip()
                if not raw:
                    continue
                genes.append({
                    "symbol": raw,
                    "original_text": raw,
                    "normalized_from_full_name": False,
                    "total_mentions": 1,
                })
                continue

            if not isinstance(item, dict):
                continue

            symbol = str(item.get("symbol") or "").strip()
            original_text = str(item.get("original_text") or symbol).strip()
            normalized_from_full_name = bool(item.get("normalized_from_full_name", False))
            total_mentions = self._as_positive_int(item.get("total_mentions"), 1)

            if not symbol:
                continue

            genes.append({
                "symbol": symbol,
                "original_text": original_text or symbol,
                "normalized_from_full_name": normalized_from_full_name,
                "total_mentions": total_mentions,
            })

            if normalized_from_full_name and original_text:
                notes.append({
                    "original_text": original_text,
                    "normalized_symbol": symbol,
                    "entity_type": "gene",
                    "total_mentions": total_mentions,
                })

        return genes, notes

    def _parse_star_allele_items(self, values: list) -> tuple[list[dict], list[dict], list[dict]]:
        complete = []
        incomplete = []
        technical_notes = []

        for item in values:
            if isinstance(item, str):
                raw_text = item.strip()
                normalized = raw_text
                gene = self._split_gene_from_allele(raw_text)
                total_mentions = 1
                normalization_type = "already_complete"
            elif isinstance(item, dict):
                raw_text = str(item.get("raw_text") or item.get("variant") or item.get("normalized") or "").strip()
                normalized = str(item.get("normalized") or item.get("variant") or raw_text).strip()
                gene = str(item.get("gene") or "").strip()
                total_mentions = self._as_positive_int(item.get("total_mentions"), 1)
                normalization_type = str(item.get("normalization_type") or "already_complete").strip()
            else:
                continue

            if not raw_text and not normalized:
                continue

            normalized_clean = self._canonical_star_allele(normalized or raw_text)
            gene_clean = self._clean_entity_value(gene, uppercase=True) if gene else self._split_gene_from_allele(normalized_clean)
            if gene_clean and gene_clean.startswith("HLA") and not gene_clean.startswith("HLA-") and len(gene_clean) > 3:
                gene_clean = f"HLA-{gene_clean[3:]}"

            # Controlo de qualidade: um star allele final tem de ter gene associado.
            if not normalized_clean or normalized_clean.startswith("*") or "*" not in normalized_clean or not gene_clean:
                incomplete.append({
                    "raw_text": raw_text or normalized,
                    "reason": "missing_gene_prefix",
                    "total_mentions": total_mentions,
                })
                continue

            complete.append({
                "raw_text": raw_text or normalized_clean,
                "normalized": normalized_clean,
                "gene": gene_clean,
                "normalization_type": normalization_type or "already_complete",
                "total_mentions": total_mentions,
            })

            if raw_text and self._canonical_star_allele(raw_text) != normalized_clean:
                technical_notes.append({
                    "original_text": raw_text,
                    "normalized_text": normalized_clean,
                    "entity_type": "star_allele",
                    "normalization_type": normalization_type or "format_corrected",
                    "total_mentions": total_mentions,
                    "included_in_entity_total": True,
                })

        return complete, incomplete, technical_notes

    def _parse_diplotype_items(self, values: list) -> list[dict]:
        parsed = []

        for item in values:
            if isinstance(item, str):
                raw_text = item.strip()
                normalized = raw_text
                genes = []
                total_mentions = 1
            elif isinstance(item, dict):
                raw_text = str(item.get("raw_text") or item.get("variant") or item.get("normalized") or "").strip()
                normalized = str(item.get("normalized") or item.get("variant") or raw_text).strip()
                raw_genes = item.get("genes") or []
                genes = [str(g).strip() for g in raw_genes if str(g).strip()] if isinstance(raw_genes, list) else []
                total_mentions = self._as_positive_int(item.get("total_mentions"), 1)
            else:
                continue

            normalized_clean = self._clean_entity_value(normalized or raw_text, uppercase=True)
            if not normalized_clean:
                continue

            parsed.append({
                "raw_text": raw_text or normalized_clean,
                "normalized": normalized_clean,
                "genes": sorted(set(self._clean_entity_value(g, uppercase=True) for g in genes if g)),
                "total_mentions": total_mentions,
            })

        return parsed

    def _parse_rsid_items(self, values: list) -> list[dict]:
        parsed = []

        for item in values:
            if isinstance(item, str):
                rsid = item.strip()
                gene = ""
                total_mentions = 1
            elif isinstance(item, dict):
                rsid = str(item.get("rsid") or item.get("variant") or "").strip()
                gene = str(item.get("gene") or "").strip()
                total_mentions = self._as_positive_int(item.get("total_mentions"), 1)
            else:
                continue

            rsid_clean = rsid.lower().strip(" ;,.")
            if not rsid_clean.startswith("rs"):
                continue

            parsed.append({
                "rsid": rsid_clean,
                "gene": self._clean_entity_value(gene, uppercase=True) if gene else "",
                "total_mentions": total_mentions,
            })

        return parsed

    def _normalize_gene_symbol(self, value: str) -> str:
        raw = (str(value).strip() if value is not None else "")
        if not raw:
            return ""

        # Se o modelo colocar um alelo completo no campo de gene, fica apenas o gene.
        if "*" in raw:
            raw = raw.split("*", 1)[0]

        compact_upper = re.sub(r"\s+", "", raw).upper().strip(" ;,.")
        resolved = self.genes.resolve_symbol(raw) or self.genes.resolve_symbol(compact_upper)

        if resolved:
            rec = self.genes.get(resolved)
            if rec:
                return rec.symbol
            return resolved

        return compact_upper

    # =====================================================
    # Enriquecimento e evidência
    # =====================================================
    def _build_gene_summary_item(self, gene_symbol: str) -> dict:
        rec = self.genes.get(gene_symbol)

        if rec:
            return {
                "symbol": rec.symbol,
                "ncbi_gene_id": rec.ncbi_gene_id,
                "pharmgkb_id": rec.pharmgkb_id,
                "hgnc_id": rec.hgnc_id,
                "ensembl_id": rec.ensembl_id,
                "name": rec.name,
            }

        return {"symbol": gene_symbol}

    def _clinical_variant_matches(
        self,
        variant: str,
        active_substance: str | None = None,
        active_substance_aliases: list[str] | None = None,
    ) -> list[dict]:
        matches = self.clinvars.get_all_matches(
            variant,
            active_substance=active_substance,
            aliases=active_substance_aliases,
        )

        return [
            {
                "variant": rec.variant,
                "gene": rec.gene,
                "type": rec.type,
                "level_of_evidence": rec.level_of_evidence,
                "chemicals": rec.chemicals,
                "phenotypes": rec.phenotypes,
            }
            for rec in matches
        ]

    def _gene_has_clinical_variant_evidence(
        self,
        gene: str,
        active_substance: str | None,
        active_substance_aliases: list[str] | None,
    ) -> bool:
        if hasattr(self.clinvars, "get_all_matches_for_gene"):
            return bool(self.clinvars.get_all_matches_for_gene(
                gene,
                active_substance=active_substance,
                aliases=active_substance_aliases,
            ))
        return False

    def _iter_strings_recursive(self, obj):
        if isinstance(obj, dict):
            for value in obj.values():
                yield from self._iter_strings_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                yield from self._iter_strings_recursive(item)
        elif isinstance(obj, str):
            yield obj

    def _norm_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").lower()).strip()

    def _guideline_matches_for_gene(self, gene: str, refs: dict | None) -> list[dict]:
        if not gene:
            return []

        clinpgx = (refs or {}).get("clinpgx") or {}
        matches = clinpgx.get("matches") or []
        gene_norm = self._norm_text(gene)
        out = []
        seen = set()

        for match in matches:
            related_genes = match.get("related_genes") or []
            matched = False

            for related in related_genes:
                symbol = self._norm_text(related.get("symbol") if isinstance(related, dict) else "")
                name = self._norm_text(related.get("name") if isinstance(related, dict) else "")
                if gene_norm and gene_norm in {symbol, name}:
                    matched = True
                    break

            if not matched:
                for s in self._iter_strings_recursive(match):
                    if self._norm_text(s) == gene_norm:
                        matched = True
                        break

            if matched:
                gid = match.get("guideline_id") or match.get("source_file") or ""
                key = str(gid)
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "guideline_id": match.get("guideline_id"),
                        "source_file": match.get("source_file"),
                        "guideline_name": match.get("guideline_name"),
                        "source": match.get("source"),
                    })

        return out

    def _guideline_matches_for_entity(
        self,
        entity: str,
        gene: str | None,
        refs: dict | None,
    ) -> list[dict]:
        clinpgx = (refs or {}).get("clinpgx") or {}
        matches = clinpgx.get("matches") or []
        entity_norm = self._norm_text(entity)
        out = []
        seen = set()

        for match in matches:
            matched = False
            if entity_norm:
                for s in self._iter_strings_recursive(match):
                    if entity_norm == self._norm_text(s) or entity_norm in self._norm_text(s):
                        matched = True
                        break

            if not matched and gene:
                matched = bool(self._guideline_matches_for_gene(gene, {"clinpgx": {"matches": [match]}}))

            if matched:
                gid = match.get("guideline_id") or match.get("source_file") or ""
                key = str(gid)
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "guideline_id": match.get("guideline_id"),
                        "source_file": match.get("source_file"),
                        "guideline_name": match.get("guideline_name"),
                        "source": match.get("source"),
                    })

        return out

    def _guideline_ids(self, guideline_matches: list[dict]) -> list[str]:
        values = []
        seen = set()
        for item in guideline_matches or []:
            value = item.get("guideline_id") or item.get("source_file")
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        return values

    def _extract_active_substance_identifiers(
        self,
        active_substance_external_references: dict | None,
    ) -> dict:
        refs = active_substance_external_references or {}

        mesh_id = ""
        drugbank_id = ""
        mrconso_cui = ""

        mesh = refs.get("mesh") or {}
        mesh_results = mesh.get("results_by_substance") or {}
        for result in mesh_results.values():
            mesh_unique_id = (result.get("mesh_unique_id") or "").strip()
            if mesh_unique_id:
                mesh_id = mesh_unique_id
                break

        # MRCONSO é a fonte principal para DrugBank ID + UMLS CUI da substância ativa.
        #
        # `best_match_global` já arbitrou entre todas as consultas e privilegia
        # a correspondência exacta. Sem ele, percorria-se os resultados pela
        # ordem das consultas e o primeiro ganhava: o alias "metoxifluorane",
        # que só tinha parciais, impunha o CUI da leucina sobre o CUI correcto
        # que o nome original tinha por exacta.
        mrconso = refs.get("mrconso") or {}
        global_best = mrconso.get("best_match_global") or {}
        if global_best:
            mrconso_cui = (global_best.get("cui") or "").strip()
            drugbank_id = (global_best.get("drugbank_id") or "").strip()

        mr_results = mrconso.get("results_by_substance") or {}
        for result in mr_results.values():
            best = result.get("best_match") or {}
            if not mrconso_cui:
                mrconso_cui = (best.get("cui") or "").strip()
            if not drugbank_id:
                drugbank_id = (best.get("drugbank_id") or "").strip()
            if mrconso_cui and drugbank_id:
                break

        return {
            "mesh_id": mesh_id,
            "drugbank_id": drugbank_id,
            "mrconso_cui": mrconso_cui,
        }

    def _has_any_entities(self, n_genes: int, n_star_alleles: int, n_diplotypes: int, n_rsids: int) -> bool:
        return any([n_genes > 0, n_star_alleles > 0, n_diplotypes > 0, n_rsids > 0])

    def _sanitize_external_references(self, refs: dict | None) -> dict:
        """Remove detalhes técnicos dos cruzamentos externos antes de escrever outputs.

        Em particular, não expõe paths locais como data/umls/MRCONSO.RRF.
        """
        if not isinstance(refs, dict):
            return {}
        clean = json.loads(json.dumps(refs, ensure_ascii=False))

        def strip_keys(obj):
            if isinstance(obj, dict):
                for key in list(obj.keys()):
                    if key.lower().endswith("path") or key.lower() in {"mrconso_path"}:
                        obj.pop(key, None)
                    else:
                        strip_keys(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    strip_keys(item)

        strip_keys(clean)
        return clean

    def _extract_document_metadata_from_sections(self, seccoes: list) -> dict:
        metadata = {
            "nome_medicamento": "",
            "grupo_farmacoterapeutico": "",
            # Código hierárquico do Infarmed (ex. "8.5.1.2"). É a chave estável
            # do grupo: o rótulo textual varia em maiúsculas, hifenização e
            # espaçamento entre RCMs, gerando 472 "grupos" distintos para
            # apenas 121 códigos reais.
            "grupo_farmacoterapeutico_codigo": "",
            "codigo_atc": "",
        }

        for sec in seccoes or []:
            titulo = (sec.get("titulo") or "").strip().lower()
            content = (sec.get("content") or "").strip()
            if not content:
                continue

            if titulo == "nome do medicamento":
                metadata["nome_medicamento"] = content
            elif titulo == "grupo farmacoterapêutico" or titulo == "grupo farmacoterapeutico":
                metadata["grupo_farmacoterapeutico"] = content
                metadata["grupo_farmacoterapeutico_codigo"] = (sec.get("codigo") or "").strip()
            elif titulo == "atc":
                metadata["codigo_atc"] = content

        return metadata

    def _build_counts(self, gene_items, star_items, diplotype_items, rsid_items) -> dict:
        def count_guideline(items):
            return sum(1 for x in items if x.get("evidence_flags", {}).get("has_guideline"))

        return {
            "genes_unicos_total": len(gene_items),
            "genes_mencoes_total": sum(int(x.get("total_mentions", 0) or 0) for x in gene_items),
            "star_alleles_unicos_total": len(star_items),
            "star_alleles_mencoes_total": sum(int(x.get("total_mentions", 0) or 0) for x in star_items),
            "diplotipos_unicos_total": len(diplotype_items),
            "diplotipos_mencoes_total": sum(int(x.get("total_mentions", 0) or 0) for x in diplotype_items),
            "rsids_unicos_total": len(rsid_items),
            "rsids_mencoes_total": sum(int(x.get("total_mentions", 0) or 0) for x in rsid_items),
            "entidades_unicas_total": len(gene_items) + len(star_items) + len(diplotype_items) + len(rsid_items),
            "entidades_mencoes_total": (
                sum(int(x.get("total_mentions", 0) or 0) for x in gene_items)
                + sum(int(x.get("total_mentions", 0) or 0) for x in star_items)
                + sum(int(x.get("total_mentions", 0) or 0) for x in diplotype_items)
                + sum(int(x.get("total_mentions", 0) or 0) for x in rsid_items)
            ),
            "genes_com_guideline_total": count_guideline(gene_items),
            "star_alleles_com_guideline_total": count_guideline(star_items),
            "diplotipos_com_guideline_total": count_guideline(diplotype_items),
            "rsids_com_guideline_total": count_guideline(rsid_items),
        }

    def _build_entity_items(
        self,
        gene_counter: Counter,
        star_counter: Counter,
        diplotype_counter: Counter,
        rsid_counter: Counter,
        gene_sections: dict,
        star_sections: dict,
        diplotype_sections: dict,
        rsid_sections: dict,
        star_gene_map: dict,
        diplotype_gene_map: dict,
        rsid_gene_map: dict,
        active_substance: str | None,
        active_substance_aliases: list[str] | None,
        refs: dict | None,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        gene_items = []
        for gene, mentions in gene_counter.items():
            base = self._build_gene_summary_item(gene)
            guideline_matches = self._guideline_matches_for_gene(gene, refs)
            has_clinvar = self._gene_has_clinical_variant_evidence(gene, active_substance, active_substance_aliases)
            base.update({
                "entity": gene,
                "total_mentions": mentions,
                "sections": sorted(gene_sections.get(gene, [])),
                "source_matches": {
                    "genes_tsv": bool(self.genes.get(gene)),
                    "clinicalVariants_tsv": has_clinvar,
                    "clinpgx_guideline_json": bool(guideline_matches),
                },
                "evidence_flags": {
                    "is_known_pgx_gene": bool(self.genes.get(gene)),
                    "has_clinical_variant_evidence": has_clinvar,
                    "has_guideline": bool(guideline_matches),
                },
                "guideline_ids": self._guideline_ids(guideline_matches),
                "guideline_matches": guideline_matches,
            })
            gene_items.append(base)

        star_items = []
        for variant, mentions in star_counter.items():
            gene = star_gene_map.get(variant) or self._split_gene_from_allele(variant)
            matches = self._clinical_variant_matches(variant, active_substance, active_substance_aliases)
            guideline_matches = self._guideline_matches_for_entity(variant, gene, refs)
            star_items.append({
                "entity": variant,
                "variant": variant,
                "gene": gene,
                "total_mentions": mentions,
                "sections": sorted(star_sections.get(variant, [])),
                "clinical_variant_matches": matches,
                "source_matches": {
                    "genes_tsv": bool(self.genes.get(gene)) if gene else False,
                    "clinicalVariants_tsv": bool(matches),
                    "clinpgx_guideline_json": bool(guideline_matches),
                },
                "evidence_flags": {
                    "is_known_pgx_gene": bool(self.genes.get(gene)) if gene else False,
                    "has_clinical_variant_evidence": bool(matches),
                    "has_guideline": bool(guideline_matches),
                },
                "guideline_ids": self._guideline_ids(guideline_matches),
                "guideline_matches": guideline_matches,
            })

        diplotype_items = []
        for variant, mentions in diplotype_counter.items():
            genes = sorted(diplotype_gene_map.get(variant, set()))
            matches = self._clinical_variant_matches(variant, active_substance, active_substance_aliases)
            guideline_matches = []
            for gene in genes:
                guideline_matches.extend(self._guideline_matches_for_entity(variant, gene, refs))
            if not genes:
                guideline_matches.extend(self._guideline_matches_for_entity(variant, None, refs))
            guideline_ids = self._guideline_ids(guideline_matches)
            diplotype_items.append({
                "entity": variant,
                "variant": variant,
                "genes": genes,
                "total_mentions": mentions,
                "sections": sorted(diplotype_sections.get(variant, [])),
                "clinical_variant_matches": matches,
                "source_matches": {
                    "genes_tsv": any(bool(self.genes.get(g)) for g in genes),
                    "clinicalVariants_tsv": bool(matches),
                    "clinpgx_guideline_json": bool(guideline_ids),
                },
                "evidence_flags": {
                    "is_known_pgx_gene": any(bool(self.genes.get(g)) for g in genes),
                    "has_clinical_variant_evidence": bool(matches),
                    "has_guideline": bool(guideline_ids),
                },
                "guideline_ids": guideline_ids,
                "guideline_matches": guideline_matches,
            })

        rsid_items = []
        for rsid, mentions in rsid_counter.items():
            gene = rsid_gene_map.get(rsid) or ""
            matches = self._clinical_variant_matches(rsid, active_substance, active_substance_aliases)
            guideline_matches = self._guideline_matches_for_entity(rsid, gene, refs)
            rsid_items.append({
                "entity": rsid,
                "variant": rsid,
                "gene": gene,
                "total_mentions": mentions,
                "sections": sorted(rsid_sections.get(rsid, [])),
                "clinical_variant_matches": matches,
                "source_matches": {
                    "genes_tsv": bool(self.genes.get(gene)) if gene else False,
                    "clinicalVariants_tsv": bool(matches),
                    "clinpgx_guideline_json": bool(guideline_matches),
                },
                "evidence_flags": {
                    "is_known_pgx_gene": bool(self.genes.get(gene)) if gene else False,
                    "has_clinical_variant_evidence": bool(matches),
                    "has_guideline": bool(guideline_matches),
                },
                "guideline_ids": self._guideline_ids(guideline_matches),
                "guideline_matches": guideline_matches,
            })

        return (
            sorted(gene_items, key=lambda x: x.get("entity", "")),
            sorted(star_items, key=lambda x: x.get("entity", "")),
            sorted(diplotype_items, key=lambda x: x.get("entity", "")),
            sorted(rsid_items, key=lambda x: x.get("entity", "")),
        )


    def _compact_unique_entities(self, gene_items, star_items, diplotype_items, rsid_items) -> dict:
        """Constrói a versão compacta do Document_Unique_PGx.json.

        Este output é deliberadamente simples: entidades finais, IDs principais,
        contagens reais de menções e secções. A auditoria completa fica em
        Extended_PGx_Analysis.json.
        """

        def clean_ids(ids: dict) -> dict:
            return {k: v for k, v in (ids or {}).items() if v not in (None, "", [], {})}

        def sections(item: dict) -> list:
            return sorted(item.get("sections") or [])

        def clinical_variant_ids(item: dict) -> list:
            values = []
            seen = set()
            for match in item.get("clinical_variant_matches") or []:
                if not isinstance(match, dict):
                    continue
                value = (match.get("variant") or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
            return values

        compact_genes = []
        for item in gene_items or []:
            if not isinstance(item, dict):
                continue
            entity = (item.get("entity") or item.get("symbol") or "").strip()
            if not entity:
                continue
            compact_genes.append({
                "entity": entity,
                "name": item.get("name") or "",
                "ids": clean_ids({
                    "pharmgkb_id": item.get("pharmgkb_id"),
                    "ncbi_gene_id": item.get("ncbi_gene_id"),
                    "hgnc_id": item.get("hgnc_id"),
                    "ensembl_id": item.get("ensembl_id"),
                    # Os genes eram a ÚNICA categoria sem guideline_ids aqui,
                    # ao contrário de star alleles, diplótipos e rsIDs. Como a
                    # análise global determina "tem guideline" a partir deste
                    # ficheiro compacto, nenhum gene era alguma vez associado a
                    # uma guideline: 222 de 222 linhas de gene saíam com "Não"
                    # e "Menções de genes com guidelines" dava sempre 0, apesar
                    # de CYP2D6 e CYP2C19 terem guidelines CPIC evidentes.
                    "guideline_ids": item.get("guideline_ids") or [],
                    "clinical_variants": clinical_variant_ids(item),
                }),
                "total_mentions": int(item.get("total_mentions", 0) or 0),
                "sections": sections(item),
            })

        compact_star_alleles = []
        for item in star_items or []:
            if not isinstance(item, dict):
                continue
            entity = (item.get("entity") or item.get("variant") or "").strip()
            if not entity:
                continue
            compact_star_alleles.append({
                "entity": entity,
                "gene": item.get("gene") or "",
                "ids": clean_ids({
                    "clinical_variants": clinical_variant_ids(item),
                    "guideline_ids": item.get("guideline_ids") or [],
                }),
                "total_mentions": int(item.get("total_mentions", 0) or 0),
                "sections": sections(item),
            })

        compact_diplotypes = []
        for item in diplotype_items or []:
            if not isinstance(item, dict):
                continue
            entity = (item.get("entity") or item.get("variant") or "").strip()
            if not entity:
                continue
            compact_diplotypes.append({
                "entity": entity,
                "genes": item.get("genes") or [],
                "ids": clean_ids({
                    "clinical_variants": clinical_variant_ids(item),
                    "guideline_ids": item.get("guideline_ids") or [],
                }),
                "total_mentions": int(item.get("total_mentions", 0) or 0),
                "sections": sections(item),
            })

        compact_rsids = []
        for item in rsid_items or []:
            if not isinstance(item, dict):
                continue
            entity = (item.get("entity") or item.get("variant") or "").strip()
            if not entity:
                continue
            compact_rsids.append({
                "entity": entity,
                "gene": item.get("gene") or "",
                "ids": clean_ids({
                    "clinical_variants": clinical_variant_ids(item),
                    "guideline_ids": item.get("guideline_ids") or [],
                }),
                "total_mentions": int(item.get("total_mentions", 0) or 0),
                "sections": sections(item),
            })

        return {
            "genes": compact_genes,
            "star_alleles": compact_star_alleles,
            "diplotypes": compact_diplotypes,
            "rsids": compact_rsids,
        }

    def avaliar_documento(
        self,
        seccoes: list,
        output_dir: Path,
        active_substance: str | None = None,
        active_substance_aliases: list[str] | None = None,
        active_substance_queries: list[str] | None = None,
        active_substance_external_references: dict | None = None,
    ) -> dict:
        print("\nA avaliar informação farmacogenómica...")

        contem_farmacogenomica = False
        sections_summary = []
        metadata = self._extract_document_metadata_from_sections(seccoes)

        gene_counter = Counter()
        star_counter = Counter()
        diplotype_counter = Counter()
        rsid_counter = Counter()

        gene_sections = defaultdict(set)
        star_sections = defaultdict(set)
        diplotype_sections = defaultdict(set)
        rsid_sections = defaultdict(set)

        star_gene_map = {}
        diplotype_gene_map = defaultdict(set)
        rsid_gene_map = {}

        # Menções repartidas por origem. As chaves não são exclusivas: uma
        # entidade que apareça no texto e numa tabela conta nas duas, e o total
        # do documento continua a ser o do gene_counter.
        origin_counter = {"content": Counter(), "tabelas": Counter()}

        extraction_failures_doc = 0
        reassembled_excerpts_doc = 0
        unfound_excerpts_doc = 0
        gene_normalization_notes_doc = []
        technical_normalization_notes_doc = []
        incomplete_star_alleles_doc = []
        seen_gene_normalization_notes = {}
        seen_technical_notes = {}

        log_lines = []

        for sec in seccoes:
            titulo = sec.get("titulo", "secao_sem_titulo")
            numero = sec.get("numero")
            nome_ficheiro = MarkdownProcessor.normalizar_nome_ficheiro(titulo) + ".json"
            json_path = (Path(output_dir) / nome_ficheiro).resolve()

            if not json_path.exists():
                continue

            data = json.loads(json_path.read_text(encoding="utf-8"))
            texto = (data.get("content") or "").strip()
            tabelas_secao = data.get("tabelas") or []

            if not texto and not tabelas_secao:
                continue

            avaliacao = self._avaliar_texto(texto, tabelas=tabelas_secao)
            data["avaliacao_farmacogenomica"] = avaliacao

            # Dois indicadores distintos de saúde da extração:
            #   falhas      -> blocos cuja resposta não era JSON utilizável.
            #                  O que houvesse de PGx nesses blocos perdeu-se,
            #                  logo as contagens podem estar SUBESTIMADAS.
            #   não-verbatim -> excertos que o modelo devolveu mas que não
            #                  constam literalmente do bloco. Foram
            #                  parafraseados, e ficam fora da contagem.
            extraction_failures_doc += int(avaliacao.get("n_falhas_extracao", 0) or 0)
            reassembled_excerpts_doc += int(avaliacao.get("n_excertos_recompostos", 0) or 0)
            unfound_excerpts_doc += int(avaliacao.get("n_excertos_nao_encontrados", 0) or 0)

            section_genes_min = []
            section_stars_min = []
            section_diplotypes_min = []
            section_rsids_min = []
            section_incomplete_stars = []

            contem_secao = avaliacao.get("contem_farmacogenomica", "Não")
            label = f"{numero}. {titulo}" if numero else titulo
            log_lines.append(f"{label} - {contem_secao}")

            if contem_secao == "Sim":
                contem_farmacogenomica = True
                # Só os excertos fiáveis alimentam a extração de entidades.
                # Antes usava-se `informacao_farmacogenomica or texto`, o que
                # tinha dois problemas: incluía os blocos de fallback de 6000
                # caracteres, e — quando não havia excerto nenhum — passava a
                # SECÇÃO INTEIRA ao extrator, contando entidades em texto que a
                # extração nunca chegou a validar.
                ner_text = avaliacao.get("texto_para_entidades") or ""
                if not ner_text.strip():
                    extracted = {}
                else:
                    extracted = self._extract_entities_model(ner_text)

                section_label = str(numero or titulo)

                for note in extracted.get("gene_normalization_notes") or []:
                    original_text = (note.get("original_text") or "").strip()
                    normalized_symbol = self._normalize_gene_symbol(note.get("normalized_symbol") or "")
                    if not original_text or not normalized_symbol:
                        continue
                    self._merge_counted_note(
                        gene_normalization_notes_doc,
                        seen_gene_normalization_notes,
                        {
                            "original_text": original_text,
                            "normalized_symbol": normalized_symbol,
                            "entity_type": "gene",
                            "total_mentions": self._as_positive_int(note.get("total_mentions"), 1),
                        },
                    )

                for note in extracted.get("normalizacao_tecnica") or []:
                    self._merge_counted_note(
                        technical_normalization_notes_doc,
                        seen_technical_notes,
                        {
                            "original_text": note.get("original_text") or "",
                            "normalized_text": note.get("normalized_text") or "",
                            "entity_type": note.get("entity_type") or "",
                            "normalization_type": note.get("normalization_type") or "format_corrected",
                            "total_mentions": self._as_positive_int(note.get("total_mentions"), 1),
                            "included_in_entity_total": bool(note.get("included_in_entity_total", False)),
                        },
                    )

                # Contagem por origem: o modelo identifica as entidades uma só
                # vez, sobre texto e tabelas juntos; a repartição das menções
                # entre as duas origens é feita aqui, deterministicamente, com
                # o mesmo contador usado em todo o lado. Evita duplicar as
                # chamadas ao modelo só para saber de onde veio cada menção.
                bruto_content = avaliacao.get("texto_de_content") or ""
                bruto_tabelas = avaliacao.get("texto_de_tabelas") or ""
                texto_content = self._canonical_text_for_counting(bruto_content)
                texto_tabelas = self._canonical_text_for_counting(bruto_tabelas)

                def contar(entidade: str, canonico: str, bruto: str) -> int:
                    """Conta menções, com regra reforçada para símbolos ambíguos."""
                    if entidade.upper() in self.AMBIGUOUS_GENE_SYMBOLS:
                        return self._count_ambiguous_symbol(bruto, entidade.upper())
                    return self._count_non_overlapping(
                        canonico, self._canonical_text_for_counting(entidade))

                for gene_item in extracted.get("genes") or []:
                    symbol = self._normalize_gene_symbol(gene_item.get("symbol") if isinstance(gene_item, dict) else gene_item)
                    if not symbol:
                        continue
                    mentions = self._as_positive_int(gene_item.get("total_mentions") if isinstance(gene_item, dict) else 1, 1)
                    gene_counter[symbol] += mentions
                    gene_sections[symbol].add(section_label)
                    section_genes_min.append({"symbol": symbol, "total_mentions": mentions})

                    origin_counter["content"][symbol] += contar(
                        symbol, texto_content, bruto_content)
                    origin_counter["tabelas"][symbol] += contar(
                        symbol, texto_tabelas, bruto_tabelas)

                section_star_counter = Counter()
                section_star_gene_map = {}
                section_technical_notes = []
                section_seen_technical_notes = {}

                for star_item in extracted.get("star_alleles") or []:
                    variant = self._canonical_star_allele(star_item.get("normalized") if isinstance(star_item, dict) else star_item)
                    if not variant or variant.startswith("*") or "*" not in variant:
                        continue

                    model_mentions = self._as_positive_int(star_item.get("total_mentions") if isinstance(star_item, dict) else 1, 1)
                    text_mentions, form_counts = self._count_star_allele_mentions_in_text(variant, ner_text)
                    mentions = text_mentions if text_mentions > 0 else model_mentions

                    gene = self._clean_entity_value(star_item.get("gene") if isinstance(star_item, dict) else "", uppercase=True) or self._split_gene_from_allele(variant)
                    if gene.startswith("HLA") and not gene.startswith("HLA-") and len(gene) > 3:
                        gene = f"HLA-{gene[3:]}"

                    # Se o modelo devolver a mesma entidade mais do que uma vez,
                    # não somamos totais já recalculados a partir do texto; ficamos
                    # com a maior contagem consolidada para a secção.
                    section_star_counter[variant] = max(section_star_counter.get(variant, 0), mentions)
                    if gene:
                        section_star_gene_map[variant] = gene

                    # Regista normalização técnica de formas compactas equivalentes,
                    # por exemplo HLAB*1502 -> HLA-B*1502, quando presentes no texto.
                    forms = self._star_allele_count_forms(variant)
                    canonical_form = forms[0] if forms else ""
                    for form, count in form_counts.items():
                        if not count or form == canonical_form:
                            continue
                        note_payload = {
                            "original_text": form,
                            "normalized_text": variant,
                            "entity_type": "star_allele",
                            "normalization_type": "format_correction",
                            "total_mentions": count,
                            "included_in_entity_total": True,
                        }
                        self._merge_counted_note(
                            technical_normalization_notes_doc,
                            seen_technical_notes,
                            note_payload,
                        )
                        self._merge_counted_note(
                            section_technical_notes,
                            section_seen_technical_notes,
                            note_payload,
                        )

                for variant, mentions in section_star_counter.items():
                    gene = section_star_gene_map.get(variant) or self._split_gene_from_allele(variant)
                    star_counter[variant] += mentions
                    star_sections[variant].add(section_label)
                    if gene:
                        star_gene_map[variant] = gene
                    section_stars_min.append({"variant": variant, "gene": gene, "total_mentions": mentions})

                    for forma in self._star_allele_count_forms(variant):
                        origin_counter["content"][variant] += \
                            self._count_non_overlapping(texto_content, forma)
                        origin_counter["tabelas"][variant] += \
                            self._count_non_overlapping(texto_tabelas, forma)

                for diplotype_item in extracted.get("diplotypes") or []:
                    variant = self._clean_entity_value(diplotype_item.get("normalized") if isinstance(diplotype_item, dict) else diplotype_item, uppercase=True)
                    if not variant:
                        continue
                    mentions = self._as_positive_int(diplotype_item.get("total_mentions") if isinstance(diplotype_item, dict) else 1, 1)
                    genes = diplotype_item.get("genes") if isinstance(diplotype_item, dict) else []
                    genes = [self._normalize_gene_symbol(g) for g in genes or [] if self._normalize_gene_symbol(g)]
                    diplotype_counter[variant] += mentions
                    diplotype_sections[variant].add(section_label)
                    for gene in genes:
                        diplotype_gene_map[variant].add(gene)
                    section_diplotypes_min.append({"variant": variant, "genes": genes, "total_mentions": mentions})

                    alvo = self._canonical_text_for_counting(variant)
                    origin_counter["content"][variant] += \
                        self._count_non_overlapping(texto_content, alvo)
                    origin_counter["tabelas"][variant] += \
                        self._count_non_overlapping(texto_tabelas, alvo)

                for rsid_item in extracted.get("rsids") or []:
                    rsid = (rsid_item.get("rsid") if isinstance(rsid_item, dict) else rsid_item or "").strip().lower()
                    if not rsid.startswith("rs"):
                        continue
                    mentions = self._as_positive_int(rsid_item.get("total_mentions") if isinstance(rsid_item, dict) else 1, 1)
                    gene = self._normalize_gene_symbol(rsid_item.get("gene") if isinstance(rsid_item, dict) else "")
                    rsid_counter[rsid] += mentions
                    rsid_sections[rsid].add(section_label)
                    if gene:
                        rsid_gene_map[rsid] = gene
                    section_rsids_min.append({"variant": rsid, "gene": gene, "total_mentions": mentions})

                    alvo = self._canonical_text_for_counting(rsid)
                    origin_counter["content"][rsid] += \
                        self._count_non_overlapping(texto_content, alvo)
                    origin_counter["tabelas"][rsid] += \
                        self._count_non_overlapping(texto_tabelas, alvo)

                for item in extracted.get("incomplete_star_alleles") or []:
                    raw_text = item.get("raw_text") if isinstance(item, dict) else str(item)
                    if raw_text:
                        entry = {
                            "raw_text": raw_text,
                            "reason": item.get("reason") if isinstance(item, dict) else "missing_gene_prefix",
                            "total_mentions": self._as_positive_int(item.get("total_mentions") if isinstance(item, dict) else 1, 1),
                            "section": section_label,
                        }
                        section_incomplete_stars.append(entry)
                        incomplete_star_alleles_doc.append(entry)

                data["avaliacao_farmacogenomica"]["pgx_entidades"] = {
                    "genes": section_genes_min,
                    "star_alleles": section_stars_min,
                    "diplotypes": section_diplotypes_min,
                    "rsids": section_rsids_min,
                    "incomplete_star_alleles": section_incomplete_stars,
                }
                data["avaliacao_farmacogenomica"]["normalizacao"] = {
                    "nome_extenso_para_simbolo": extracted.get("gene_normalization_notes") or [],
                    "normalizacao_tecnica": section_technical_notes,
                }

                sections_summary.append({
                    "section_title": titulo,
                    "section_number": numero,
                    "json_file": nome_ficheiro,
                    "has_pgx": True,
                    "contagens_secao": {
                        "genes_mencoes_total": sum(x.get("total_mentions", 0) for x in section_genes_min),
                        "star_alleles_mencoes_total": sum(x.get("total_mentions", 0) for x in section_stars_min),
                        "diplotipos_mencoes_total": sum(x.get("total_mentions", 0) for x in section_diplotypes_min),
                        "rsids_mencoes_total": sum(x.get("total_mentions", 0) for x in section_rsids_min),
                    },
                    "entidades_secao": {
                        "genes": section_genes_min,
                        "star_alleles": section_stars_min,
                        "diplotypes": section_diplotypes_min,
                        "rsids": section_rsids_min,
                        "incomplete_star_alleles": section_incomplete_stars,
                    },
                    "normalizacao_secao": {
                        "nome_extenso_para_simbolo": extracted.get("gene_normalization_notes") or [],
                        "normalizacao_tecnica": section_technical_notes,
                    },
                })

            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"A avaliar: {json_path.name} → {contem_secao}")

        active_substance_identifiers = self._extract_active_substance_identifiers(active_substance_external_references)

        gene_items, star_items, diplotype_items, rsid_items = self._build_entity_items(
            gene_counter=gene_counter,
            star_counter=star_counter,
            diplotype_counter=diplotype_counter,
            rsid_counter=rsid_counter,
            gene_sections=gene_sections,
            star_sections=star_sections,
            diplotype_sections=diplotype_sections,
            rsid_sections=rsid_sections,
            star_gene_map=star_gene_map,
            diplotype_gene_map=diplotype_gene_map,
            rsid_gene_map=rsid_gene_map,
            active_substance=active_substance,
            active_substance_aliases=active_substance_aliases,
            refs=active_substance_external_references,
        )

        contagens_documento = self._build_counts(gene_items, star_items, diplotype_items, rsid_items)
        contagens_documento["genes_normalizados_nome_extenso_para_simbolo_total"] = len(gene_normalization_notes_doc)
        contagens_documento["normalizacoes_tecnicas_total"] = len(technical_normalization_notes_doc)
        contagens_documento["star_alleles_incompletos_total"] = len(incomplete_star_alleles_doc)

        has_entities = self._has_any_entities(
            n_genes=len(gene_items),
            n_star_alleles=len(star_items),
            n_diplotypes=len(diplotype_items),
            n_rsids=len(rsid_items),
        )

        documento_block = {
            "nome_medicamento": metadata.get("nome_medicamento", ""),
            "substancia_ativa": active_substance or "",
            "aliases_substancia_ativa": active_substance_aliases or [],
            "grupo_farmacoterapeutico": metadata.get("grupo_farmacoterapeutico", ""),
            "grupo_farmacoterapeutico_codigo": metadata.get("grupo_farmacoterapeutico_codigo", ""),
            "codigo_atc": metadata.get("codigo_atc", ""),
        }

        entidades_com_guideline = {
            "genes": [x for x in gene_items if x.get("evidence_flags", {}).get("has_guideline")],
            "star_alleles": [x for x in star_items if x.get("evidence_flags", {}).get("has_guideline")],
            "diplotypes": [x for x in diplotype_items if x.get("evidence_flags", {}).get("has_guideline")],
            "rsids": [x for x in rsid_items if x.get("evidence_flags", {}).get("has_guideline")],
        }
        entidades_sem_guideline = {
            "genes": [x for x in gene_items if not x.get("evidence_flags", {}).get("has_guideline")],
            "star_alleles": [x for x in star_items if not x.get("evidence_flags", {}).get("has_guideline")],
            "diplotypes": [x for x in diplotype_items if not x.get("evidence_flags", {}).get("has_guideline")],
            "rsids": [x for x in rsid_items if not x.get("evidence_flags", {}).get("has_guideline")],
        }

        resumo_extended = {
            "documento": documento_block,
            "classificacao": {
                "has_pgx": contem_farmacogenomica,
                "has_entities": has_entities,
                "seccoes_com_pgx_total": len(sections_summary),
            },
            "identificadores_substancia": active_substance_identifiers,
            "contagens_documento": contagens_documento,
            "frequencias_entidades": {
                "genes": gene_items,
                "star_alleles": star_items,
                "diplotypes": diplotype_items,
                "rsids": rsid_items,
            },
            "entidades_com_guideline": entidades_com_guideline,
            "entidades_sem_guideline": entidades_sem_guideline,
            "normalizacao": {
                "nome_extenso_para_simbolo": sorted(
                    gene_normalization_notes_doc,
                    key=lambda x: (x.get("normalized_symbol", ""), x.get("original_text", "")),
                ),
                "normalizacao_tecnica": sorted(
                    technical_normalization_notes_doc,
                    key=lambda x: (x.get("entity_type", ""), x.get("normalized_text", "")),
                ),
                "star_alleles_incompletos": incomplete_star_alleles_doc,
            },
            "seccoes": sections_summary,
            "fontes_cruzamento": {
                "genes_tsv": True,
                "clinicalVariants_tsv": True,
                "clinpgx_guideline_json": bool((active_substance_external_references or {}).get("clinpgx", {}).get("matches")),
                "mesh": bool(active_substance_identifiers.get("mesh_id")),
                "mrconso": bool(active_substance_identifiers.get("drugbank_id") or active_substance_identifiers.get("mrconso_cui")),
            },
            # Campos legacy mínimos para compatibilidade com código antigo.
            "has_pgx": contem_farmacogenomica,
            "has_entities": has_entities,
            "active_substance": active_substance,
            "active_substance_aliases": active_substance_aliases or [],
            "active_substance_external_references": self._sanitize_external_references(active_substance_external_references),
        }

        pgx_outputs_dir = (Path(output_dir) / "pgx_outputs").resolve()
        pgx_outputs_dir.mkdir(parents=True, exist_ok=True)

        resumo_path = (pgx_outputs_dir / "Extended_PGx_Analysis.json").resolve()
        resumo_path.write_text(json.dumps(resumo_extended, ensure_ascii=False, indent=2), encoding="utf-8")

        document_unique_entities = self._compact_unique_entities(
            gene_items,
            star_items,
            diplotype_items,
            rsid_items,
        )

        document_unique = {
            "pipeline": self.pipeline_metadata(),
            "documento": documento_block,
            "identificadores_substancia": active_substance_identifiers,
            "entidades": document_unique_entities,
            "contagens": contagens_documento,
            # Repartição das menções entre texto corrido e tabelas.
            # As entidades únicas por origem somam mais do que o total quando a
            # mesma entidade aparece nas duas — é informação, não erro.
            "origem_entidades": {
                "texto": {
                    "entidades_unicas": sum(1 for v in origin_counter["content"].values() if v),
                    "mencoes": sum(origin_counter["content"].values()),
                },
                "tabelas": {
                    "entidades_unicas": sum(1 for v in origin_counter["tabelas"].values() if v),
                    "mencoes": sum(origin_counter["tabelas"].values()),
                },
                # O que só existe em tabelas: seria perdido sem esta alteração.
                "exclusivas_de_tabelas": sorted(
                    e for e, n in origin_counter["tabelas"].items()
                    if n and not origin_counter["content"].get(e)
                ),
            },
            "qualidade_extracao": {
                # 0 = toda a extração devolveu JSON utilizável.
                "falhas_extracao": extraction_failures_doc,
                # 0 = todos os excertos constam literalmente do RCM.
                # Texto existe no RCM, mas em partes não contíguas.
                "excertos_recompostos": reassembled_excerpts_doc,
                # Contém texto que não existe no bloco: indício de paráfrase.
                "excertos_nao_encontrados": unfound_excerpts_doc,
            },
        }

        document_unique_path = (pgx_outputs_dir / "Document_Unique_PGx.json").resolve()
        document_unique_path.write_text(json.dumps(document_unique, ensure_ascii=False, indent=2), encoding="utf-8")

        log_lines.append("")
        log_lines.append(f"O RCM contém informação farmacogenómica: {'Sim' if contem_farmacogenomica else 'Não'}")
        log_lines.append(f"O RCM contém entidades farmacogenómicas: {'Sim' if has_entities else 'Não'}")
        log_lines.append(f"Genes únicos: {contagens_documento['genes_unicos_total']}")
        log_lines.append(f"Menções totais de genes: {contagens_documento['genes_mencoes_total']}")
        log_lines.append(f"Star alleles únicos: {contagens_documento['star_alleles_unicos_total']}")
        log_lines.append(f"Menções totais de star alleles: {contagens_documento['star_alleles_mencoes_total']}")
        log_lines.append(f"Diplótipos únicos: {contagens_documento['diplotipos_unicos_total']}")
        log_lines.append(f"Menções totais de diplótipos: {contagens_documento['diplotipos_mencoes_total']}")

        log_path = (Path(output_dir) / "Log_Avaliacao_PGx.txt").resolve()
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

        return resumo_extended

    # Caracteres invisíveis que a extração de PDF injeta e que nada significam.
    _INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"), None)

    @staticmethod
    def _normalise_for_verbatim_check(text: str) -> str:
        """Forma comparável, tolerante a artefactos da extração.

        Medido nos 17 RCMs do subset: 8 excertos foram marcados não-verbatim, e
        NENHUM era paráfrase. Eram diferenças introduzidas pelo docling, que o
        modelo corrigiu ao devolver o texto:

            docling              modelo
            c.521T &gt; C        c.521T > C        entidade HTML por converter
            &lt;5%               <5%               idem
            recémnascidos        recém-nascidos    hífen perdido na extração
            dia                  di[U+00AD]a       soft hyphen injetado

        Todos semanticamente idênticos. Comparar sem os neutralizar produzia
        falsos alarmes de infidelidade e retirava excertos legítimos da
        contagem de entidades.

        O que continua a NÃO ser tolerado: palavras diferentes, omitidas ou
        acrescentadas — que é o que "verbatim" deve garantir.
        """
        text = html.unescape(str(text or ""))
        text = unicodedata.normalize("NFKC", text)
        text = text.translate(PharmacogenomicsEvaluator._INVISIBLE)

        for ch in ["‐", "‑", "‒", "–", "—", "−"]:
            text = text.replace(ch, "-")

        # Hífens são pura pontuação de quebra de linha e de composição; a sua
        # presença ou ausência não muda o conteúdo clínico.
        text = re.sub(r"\s*-\s*", "", text)

        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    # Fração mínima do excerto que tem de existir no bloco para o considerar
    # recomposto em vez de inventado.
    REASSEMBLY_MIN_COVERAGE = 0.85

    def _fidelity(self, excerpt: str, source_block: str) -> str:
        """Classifica a fidelidade do excerto ao bloco de origem.

        Três estados, por ordem decrescente de confiança:

          "verbatim"       cópia contígua e literal. É o que o prompt pede.
          "recomposto"     o conteúdo existe no bloco, mas em partes não
                           contíguas que o modelo juntou. Acontece quando o
                           docling emite tabelas fora da ordem de leitura.
                           O texto é real; a citação é que não é literal.
          "nao_encontrado" há conteúdo que não consta do bloco. É o único
                           estado que indicia paráfrase ou invenção.

        Medido nos 17 RCMs do subset: 37 verbatim, 2 recompostos, 0 não
        encontrados. Distinguir os dois últimos importa porque um excerto
        recomposto continua a ser prova válida de que o RCM menciona a
        entidade — só não serve para citação direta.
        """
        if not excerpt or not source_block:
            return "nao_encontrado"

        needle = self._normalise_for_verbatim_check(excerpt)
        haystack = self._normalise_for_verbatim_check(source_block)

        if not needle:
            return "nao_encontrado"
        if needle in haystack:
            return "verbatim"

        # Consome o excerto em fragmentos: quanto dele existe no bloco?
        matched = 0
        rest = needle
        while rest:
            lo, hi = 0, len(rest)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if rest[:mid] in haystack:
                    lo = mid
                else:
                    hi = mid - 1
            if lo < 20:            # fragmento curto demais para ser informativo
                break
            matched += lo
            rest = rest[lo:].lstrip()

        coverage = matched / len(needle)
        return "recomposto" if coverage >= self.REASSEMBLY_MIN_COVERAGE else "nao_encontrado"

    def _is_verbatim(self, excerpt: str, source_block: str) -> bool:
        """Compatibilidade: True apenas para cópia contígua e literal."""
        return self._fidelity(excerpt, source_block) == "verbatim"

    @staticmethod
    def _is_affirmative(answer: str) -> bool:
        """Interpreta a resposta Sim/Não do classificador.

        Antes fazia `"sim" in answer.lower()`, um teste por substring que dava
        positivo em "simplesmente", "similar", "assim" e "simultaneamente" —
        todas palavras que aparecem naturalmente numa resposta negativa
        ("Não. O texto refere-se simplesmente ao metabolismo hepático."). Cada
        falso positivo arrastava um bloco inteiro para a extração e para a
        contagem de entidades.

        Agora procura-se um token isolado, e a negação tem precedência.
        """
        if not answer:
            return False

        normalized = unicodedata.normalize("NFKD", answer.lower())
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))

        # A primeira linha não vazia carrega o veredicto; o resto é justificação.
        for line in normalized.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.search(r"\bnao\b", line):
                return False
            if re.search(r"\bsim\b", line):
                return True
            break

        return bool(re.search(r"\bsim\b", normalized)) and not re.search(r"\bnao\b", normalized)

    # Tamanho alvo de cada bloco enviado ao modelo.
    BLOCK_MAX_CHARS = 6000

    # Passagem de classificação Sim/Não antes da extração. Desligada por
    # omissão — ver _avaliar_texto para o motivo.
    USE_CLASSIFICATION_PASS = False

    @classmethod
    def _split_into_blocks(cls, text: str, max_chars: int | None = None) -> list[str]:
        """Divide o texto em blocos que respeitam fronteiras naturais.

        A versão anterior fazia `texto[i:i + 6000]`, um corte cego que partia a
        meio de frase e a meio de palavra. Uma afirmação farmacogenómica que
        atravessasse a fronteira era separada em duas metades, e cada metade
        seguia para o modelo sem o contexto da outra — o que contradiz
        diretamente a instrução do prompt de "continua a extrair enquanto o
        texto mantiver relação com a mesma informação farmacogenómica".

        Estratégia, do mais para o menos desejável:
          1. agrupar parágrafos inteiros até ao limite;
          2. se um parágrafo sozinho exceder o limite, partir por frases;
          3. se uma frase sozinha exceder o limite, partir à força.

        Sem sobreposição entre blocos, deliberadamente. Sobrepor daria mais
        contexto ao modelo, mas o mesmo excerto seria extraído duas vezes e a
        contagem de menções — que corre sobre a concatenação dos excertos —
        ficaria inflacionada. Fronteiras de parágrafo já resolvem o essencial,
        porque uma afirmação PGx raramente atravessa um parágrafo.
        """
        max_chars = max_chars or cls.BLOCK_MAX_CHARS
        if not text or not text.strip():
            return []

        def hard_split(chunk: str) -> list[str]:
            return [chunk[i:i + max_chars] for i in range(0, len(chunk), max_chars)]

        def by_sentence(paragraph: str) -> list[str]:
            sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
            out: list[str] = []
            for sentence in sentences:
                if len(sentence) > max_chars:
                    out.extend(hard_split(sentence))
                else:
                    out.append(sentence)
            return out

        # Unidades atómicas: parágrafos, ou frases quando o parágrafo é grande.
        units: list[str] = []
        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) > max_chars:
                units.extend(by_sentence(paragraph))
            else:
                units.append(paragraph)

        blocks: list[str] = []
        current: list[str] = []
        size = 0

        for unit in units:
            unit_size = len(unit) + 2  # separador "\n\n"
            if current and size + unit_size > max_chars:
                blocks.append("\n\n".join(current))
                current, size = [], 0
            current.append(unit)
            size += unit_size

        if current:
            blocks.append("\n\n".join(current))

        return [b for b in blocks if b.strip()]

    @staticmethod
    def classificar_erro_llm(exc: Exception) -> tuple[str, int | None]:
        """Rótulo e código HTTP de uma falha na chamada ao modelo.

        Três falhas parecem-se no terminal e são problemas completamente
        diferentes:

        - **429** — estás a bater no limite de pedidos da conta. Insistir
          depressa piora; a espera tem de partir de um valor mais alto.
        - **502/503** — o modelo na cloud está inacessível. É transitório e
          vale a pena repetir com o backoff normal.
        - **timeout** — o pedido não respondeu dentro de ``LLM_TIMEOUT``.
          Antes de haver timeout isto não existia como erro: o processo
          simplesmente parava.

        Sem esta distinção, o log de uma corrida de dias não permite dizer se
        o problema foi a conta, o serviço ou a rede — e essa é a primeira
        pergunta quando os números não fecham.
        """
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            if status == 429:
                return "limite de pedidos (429)", status
            if status in (502, 503, 504):
                return f"serviço indisponível ({status})", status
            return f"HTTP {status}", status

        texto = str(exc).lower()
        if "timeout" in texto or "timed out" in texto:
            return "timeout", None
        if "429" in texto:
            return "limite de pedidos (429)", 429
        if "502" in texto:
            return "serviço indisponível (502)", 502
        if "connect" in texto or "connection" in texto:
            return "falha de ligação", None
        return type(exc).__name__, None

    def _invoke_with_backoff(self, prompt: str, *, describe: str) -> str:
        """Chama o modelo com backoff exponencial.

        Antes eram 8 tentativas com 20 s fixos — até 160 s por bloco falhado,
        sem jitter, e sem distinguir uma falha transitória de um serviço em
        baixo. Com 10 400 documentos, esperas fixas somam horas.

        A partir de 15-09-2026 a espera depende também do tipo de falha, e os
        erros que não mudam com a repetição (chave inválida, modelo
        inexistente) falham à primeira em vez de gastarem cinco tentativas.
        """
        last_error: Exception | None = None

        for attempt in range(self.LLM_MAX_RETRIES):
            try:
                return self._ollama_invoke(prompt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                rotulo, status = self.classificar_erro_llm(exc)

                if status in self.LLM_STATUS_SEM_RETENTATIVA:
                    print(f"❌ {describe}: {rotulo} — não se repete.")
                    return ""

                if attempt == self.LLM_MAX_RETRIES - 1:
                    break

                base = (self.LLM_BACKOFF_RATE_LIMIT if status == 429
                        else self.LLM_BACKOFF_BASE)
                delay = min(base * (2 ** attempt), self.LLM_BACKOFF_MAX)
                delay += random.uniform(0, delay * 0.25)
                print(
                    f"⚠️ {describe}: tentativa {attempt + 1}/{self.LLM_MAX_RETRIES} "
                    f"falhou — {rotulo}. A esperar {delay:.0f}s."
                )
                time.sleep(delay)

        rotulo, _ = self.classificar_erro_llm(last_error) if last_error else ("?", None)
        print(f"❌ {describe}: esgotadas as tentativas — {rotulo} ({last_error})")
        return ""

    @staticmethod
    def _table_units(tabelas: list | None) -> list[tuple[str, str]]:
        """Prepara as tabelas da secção como unidades independentes.

        Devolve pares (origem, texto). A legenda vai colada ao corpo: sem ela o
        modelo vê colunas sem saber o que significam. No siponimod, a diferença
        é entre uma grelha de números e "Efeito do genótipo CYP2C9 na depuração
        sistémica e exposição sistémica".

        Porquê separado do `content`, e não reinserido nele:
          * o `content` fica só com prosa, e a verificação de fidelidade
            compara texto corrido com texto corrido;
          * cada tabela tem orçamento próprio de caracteres, portanto nunca
            empurra prosa para outro bloco nem é partida por causa dela;
          * a legenda fica garantidamente junto do corpo, em vez de depender
            de onde calha a fronteira da segmentação.
        """
        units: list[tuple[str, str]] = []

        for tabela in tabelas or []:
            if not isinstance(tabela, dict):
                continue
            corpo = (tabela.get("texto") or "").strip()
            if not corpo:
                continue

            numero = str(tabela.get("numero") or len(units) + 1).strip()
            titulo = (tabela.get("titulo") or "").strip()
            cabecalho = f"Tabela {numero}" + (f" - {titulo}" if titulo else "")
            units.append((f"tabela_{numero}", f"{cabecalho}\n{corpo}"))

        return units

    def _avaliar_texto(self, texto: str, tabelas: list | None = None) -> dict:
        """Extrai excertos PGx do texto de uma secção e das suas tabelas.

        Uma chamada ao modelo por bloco. A passagem de classificação Sim/Não
        que existia antes era redundante: o prompt de extração já devolve
        `{"excertos": []}` quando não há nada relevante, e aplica os mesmos
        critérios de inclusão e exclusão. Duas chamadas por bloco duplicavam o
        custo — em 10 400 documentos, dias de compute.

        A redundância era pior do que apenas cara: as duas passagens podiam
        discordar. Quando a classificação dizia "Sim" e a extração devolvia
        vazio, o código guardava o BLOCO INTEIRO como excerto para não "perder"
        conteúdo. Com uma só passagem essa contradição deixa de existir —
        `contem_farmacogenomica` passa a ser, por definição, "o modelo extraiu
        pelo menos um excerto".

        Pôr USE_CLASSIFICATION_PASS = True repõe o comportamento antigo.

        As TABELAS são avaliadas a seguir ao texto corrido, como unidades
        próprias. Antes eram removidas do `content` pelo MarkdownProcessor e
        nunca lidas por ninguém: no subset de 17 RCMs isso custou os seis
        diplótipos CYP2C9*1*1 a *3*3 do siponimod, com frequências
        populacionais e impacto na exposição — o núcleo PGx do fármaco.

        Cada excerto fica marcado com a origem, e a verificação de fidelidade
        corre contra essa origem. Comparar um excerto de tabela com o `content`
        daria sempre "não encontrado", já que a tabela não está lá.
        """
        excertos_extraidos: list[dict] = []
        falhas_extracao: list[dict] = []

        # content primeiro, tabelas depois
        unidades: list[tuple[str, str]] = [
            ("content", bloco) for bloco in self._split_into_blocks(texto)
        ] + self._table_units(tabelas)

        # NOTA sobre a fidelidade, para não se voltar a tentar "corrigir".
        #
        # A verificação corre contra o BLOCO de onde a chamada partiu, e é o
        # correcto. Chegou a suspeitar-se de que os 7 excertos marcados
        # "nao_encontrado" nos 64 documentos eram falsos alarmes causados por
        # citações a atravessar a fronteira entre blocos — todos eles estavam
        # em secções multi-bloco.
        #
        # Testou-se: comparando contra a secção inteira, ZERO dos 20 excertos
        # não-verbatim passa a verbatim. São alterações reais do modelo:
        #
        #   azatioprina    "que inibem a TPMT"      fonte: "que inibam"
        #   carbamazepina  "dois cromossomos"       fonte: "cromossomas"
        #   clopidogrel    "hipoglicemia grace"     fonte: "grave"
        #   clopidogrel    "extensos ou intermédios" fonte: "extenso ou intermédio"
        #
        # Alargar o palheiro à secção inteira só tornaria mais provável um
        # falso "verbatim", sem corrigir nada.

        for indice, (origem, bloco) in enumerate(unidades):
            if self.USE_CLASSIFICATION_PASS:
                resposta = self._invoke_with_backoff(
                    self.prompt_base.format(texto=bloco),
                    describe="classificação PGx",
                )
                if not self._is_affirmative(resposta):
                    continue

            extracao_texto = self._invoke_with_backoff(
                self.prompt_extracao.format(texto=bloco),
                describe="extração PGx",
            )

            parsed = self._extract_json_object(extracao_texto) if extracao_texto else None

            # Resposta inutilizável. NÃO se fabrica um excerto a partir dela:
            # `texto_original` tem de conter sempre texto literal do RCM, e a
            # resposta do modelo não é isso. Regista-se como falha, à parte.
            if not isinstance(parsed, dict):
                if extracao_texto and extracao_texto.strip():
                    falhas_extracao.append({
                        "bloco_indice": indice,
                        "erro": "json_invalido",
                        "resposta_bruta_modelo": extracao_texto.strip(),
                    })
                elif not extracao_texto:
                    falhas_extracao.append({
                        "bloco_indice": indice,
                        "erro": "sem_resposta",
                        "resposta_bruta_modelo": "",
                    })
                continue

            raw_excertos = parsed.get("excertos") or []
            if not isinstance(raw_excertos, list):
                continue

            for item in raw_excertos:
                if isinstance(item, dict):
                    texto_original = str(item.get("texto_original") or "").strip()
                    motivo = str(item.get("motivo_extracao") or "").strip()
                else:
                    texto_original = str(item or "").strip()
                    motivo = ""

                if not texto_original:
                    continue

                # `motivo_extracao` fica exclusivamente com a razão dada pelo
                # modelo. O estado do pipeline vive em campos próprios.
                #
                # A fidelidade é verificada contra a unidade de ORIGEM: um
                # excerto de tabela procurado no `content` daria sempre
                # "não encontrado", porque a tabela não está lá.
                fidelidade = self._fidelity(texto_original, bloco)
                excertos_extraidos.append({
                    "texto_original": texto_original,
                    "motivo_extracao": motivo,
                    "bloco_indice": indice,
                    "origem": origem,
                    "fidelidade": fidelidade,
                    "verbatim": fidelidade == "verbatim",
                })

        if not excertos_extraidos:
            resultado = {"contem_farmacogenomica": "Não"}
            if falhas_extracao:
                resultado["falhas_extracao"] = falhas_extracao
            return resultado

        def join(excerpts) -> str:
            return "\n\n".join(
                e["texto_original"].strip()
                for e in excerpts
                if e.get("texto_original", "").strip()
            )

        # Alimentam a contagem de entidades os excertos cujo conteúdo existe
        # mesmo no RCM — verbatim ou recomposto. Um excerto recomposto é
        # citação imperfeita mas prova válida de que o documento menciona a
        # entidade. Ficam de fora apenas os que contêm texto inexistente no
        # bloco, que é o único caso que indicia paráfrase ou invenção.
        confiaveis = [e for e in excertos_extraidos
                      if e.get("fidelidade") in ("verbatim", "recomposto")]
        contagem = Counter(e.get("fidelidade") for e in excertos_extraidos)

        de_texto = [e for e in confiaveis if e.get("origem") == "content"]
        de_tabela = [e for e in confiaveis if e.get("origem", "").startswith("tabela")]

        return {
            "contem_farmacogenomica": "Sim",
            # Todos os excertos devolvidos pelo modelo.
            "informacao_farmacogenomica": join(excertos_extraidos),
            # Os que existem mesmo no documento. Alimentam a extração de
            # entidades — uma só chamada, sobre texto e tabelas juntos.
            "texto_para_entidades": join(confiaveis),
            # Separados por origem: a contagem de menções por origem é feita
            # a jusante, de forma determinística, sem chamadas extra ao modelo.
            "texto_de_content": join(de_texto),
            "texto_de_tabelas": join(de_tabela),
            "excertos_farmacogenomicos": excertos_extraidos,
            "falhas_extracao": falhas_extracao,
            "n_falhas_extracao": len(falhas_extracao),
            "n_excertos_verbatim": contagem.get("verbatim", 0),
            "n_excertos_recompostos": contagem.get("recomposto", 0),
            "n_excertos_nao_encontrados": contagem.get("nao_encontrado", 0),
            "n_excertos_de_tabelas": len(de_tabela),
        }
