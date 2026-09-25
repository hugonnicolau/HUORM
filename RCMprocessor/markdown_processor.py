import re
import unicodedata
from langchain_text_splitters import MarkdownHeaderTextSplitter


class MarkdownProcessor:
    """Turn the Markdown extracted from an SmPC into a usable structure.

    Responsibilities:
      - normalise headings and section numbering;
      - extract tables and figures;
      - identify the normative sections (4.2, 4.3, 4.4, 4.5, 4.8, 5.1, 5.2);
      - extract the special fields (medicine name, pharmacotherapeutic group,
        ATC code);
      - expose section 2 for active-substance identification;
      - produce clean file names for export.
    """

    SECCOES_NUMERICAS = ["4.2", "4.3", "4.4", "4.5", "4.8", "5.1", "5.2"]

    # Title-based recognition, for badly numbered SmPCs.
    #
    # Some SmPCs number the 4.x subsections as top-level sections. In the
    # ketamine label, "Interações medicamentosas" appears as "5.", "Efeitos
    # indesejáveis" as "8.", and the number "5." collides with
    # "5. PROPRIEDADES FARMACOLÓGICAS". As a result, 4.5, 4.8 and 4.2 were never
    # found at all, even though the text is there — and they are three of the
    # sections where pharmacogenomics most often appears.
    #
    # The patterns are deliberately anchored at the start of the title and
    # require the distinctive terms of each normative section. A title must
    # match exactly ONE pattern; ambiguous matches are discarded, so that
    # unrelated sections are not dragged in.
    TITULOS_SECCAO = {
        # "Posologia" alone, or followed by "e modo de administração".
        # A bare prefix will not do: "Posologia pediátrica recomendada" is a
        # subheading inside 4.2, not the section itself.
        "4.2": re.compile(r"(?i)^posologia(\s*$|\s+e\s+(modo\s+de\s+)?administra)"),
        "4.3": re.compile(r"(?i)^contra[- ]?indica[çc]"),
        "4.4": re.compile(r"(?i)^advert[êe]ncias?\s+e\s+precau"),
        "4.5": re.compile(r"(?i)^intera[çc][õo]es\s+(medicamentosas|com\s+outros)"),
        "4.8": re.compile(r"(?i)^efeitos\s+indesej"),
        "5.1": re.compile(r"(?i)^propriedades\s+farmacodin"),
        "5.2": re.compile(r"(?i)^propriedades\s+farmacocin"),
    }

    @classmethod
    def _numero_por_titulo(cls, titulo: str) -> str | None:
        """Infer the normative section number from the title.

        Returns None when the title matches more than one pattern: an
        ambiguous heading must not be forced into a section.
        """
        titulo = (titulo or "").strip()
        if not titulo:
            return None
        correspondencias = [n for n, p in cls.TITULOS_SECCAO.items() if p.search(titulo)]
        return correspondencias[0] if len(correspondencias) == 1 else None

    @classmethod
    def _corrigir_numeracao_seccoes(cls, md_text: str) -> str:
        """Rewrite the headings of badly numbered normative sections.

        Runs before segmentation. A heading of any level whose title matches
        exactly one normative section is rewritten in the canonical form
        `### N.N Title`.

        It only acts when the numbering is missing or wrong: if the label
        already says `### 4.5 Interações medicamentosas`, nothing changes. And
        each number is assigned once — first occurrence wins — so a document
        that repeats the title later does not end up with two 4.5 sections.

        Motivation: the ketamine SmPC numbers the 4.x subsections as
        top-level sections ("# 5. Interações medicamentosas", "# 8. Efeitos
        indesejáveis") and even carries two distinct "5." headings. Without
        this correction, 4.2, 4.5 and 4.8 were never found.
        """
        if not md_text:
            return md_text

        # Numbers already correct in the document are left untouched.
        ja_corretos = {
            m.group(1)
            for m in re.finditer(r"(?m)^#{1,6}\s+(\d+\.\d+)\b", md_text)
            if m.group(1) in cls.SECCOES_NUMERICAS
        }
        atribuidos = set(ja_corretos)
        linhas = md_text.split("\n")

        for i, linha in enumerate(linhas):
            m = re.match(r"^(#{1,6})\s+(.*)$", linha)
            if not m:
                continue

            titulo_bruto = m.group(2).strip()

            # Already correctly numbered.
            if re.match(r"^\d+\.\d+\b", titulo_bruto):
                continue

            # Strip a top-level numeric prefix ("5. Interações…"): in these
            # documents it is wrong and cannot be trusted.
            titulo = re.sub(r"^\d+\.?\s*", "", titulo_bruto).strip()
            numero = cls._numero_por_titulo(titulo)

            if not numero or numero in atribuidos:
                continue

            atribuidos.add(numero)
            linhas[i] = f"### {numero} {titulo}"

        return "\n".join(linhas)

    def __init__(self, md_text: str):
        """Store the raw SmPC Markdown and normalise its headings at once.

        Args:
            md_text: Markdown produced by Docling.
        """
        self.md_text = self._normalizar_titulos(self._traduzir_simbolos(md_text))

    # =====================================================
    #   SYMBOL FONT CHARACTERS (Unicode Private Use Area)
    # =====================================================
    #
    # PDFs that use Adobe's Symbol font emit codepoints in the Unicode
    # Private Use Area (U+F000-U+F0FF) instead of the characters they stand
    # for. Extraction returns them raw, and they are unreadable.
    #
    # Observed in the anaesthetics batch:
    #   "incidência de U+F0B3 5%"          ->  "incidência de >= 5%"
    #   "concentrações de 16-160 U+F06D g" ->  "16-160 ug"   (micrograma!)
    #   "24 horas a 25 U+F0B0 C"           ->  "25 °C"
    #   "2,5 U+F0B1 1 l/kg"                ->  "2,5 ± 1 l/kg"
    #
    # The mapping is the Symbol font's own and is deterministic. The two that
    # matter most are micro (doses) and greater-or-equal (frequencies and
    # exposure ratios).
    SIMBOLOS_PUA = {
        "": " ", "": "+", "": "-", "": "<",
        "": "=", "": ">",
        "": "α", "": "β", "": "γ", "": "δ",
        "": "ε", "": "η", "": "κ", "": "λ",
        "": "µ", "": "π", "": "σ", "": "τ",
        "": "ω", "": "Δ", "": "Ω",
        "": "≤", "": "≥", "": "≠", "": "≈",
        "": "±", "": "×", "": "÷", "": "°",
        "": "•", "": "•", "": "•", "": "•",
        "": "→", "": "←", "": "↑", "": "↓",
        "": "∞", "": "√", "": "Σ",
    }

    @classmethod
    def _traduzir_simbolos(cls, md_text: str) -> str:
        """Convert Private Use Area codepoints into the real symbols.

        Applied before anything else, so that no downstream step —
        segmentation, extraction, or the Markdown kept for auditing — ever
        sees unreadable characters.
        """
        if not md_text:
            return md_text

        for código, símbolo in cls.SIMBOLOS_PUA.items():
            if código in md_text:
                md_text = md_text.replace(código, símbolo)

        # Private Use Area leftovers with no known equivalent: these are
        # decorative list glyphs. A space beats an empty box.
        return re.sub(r"[-]", " ", md_text)

    # =====================================================
    #            DOCUMENT HEADING NORMALISATION
    # =====================================================
    def _normalizar_titulos(self, md_text: str) -> str:
        """Normalise the numeric headings typical of SmPCs after Docling.

        Rules applied:
        - turn 'X.Y …' into '### X.Y …'
        - turn 'X. …' into '# X. …'
        - never promote broken lines, noise or table rows to headings

        Returns:
            Markdown with consistently structured headings.
        """

        linhas = md_text.splitlines()
        novas = []

        for linha in linhas:
            original = linha

            linha_limpa = (
                linha.replace("•", "")
                     .replace("▪", "")
                     .replace("●", "")
                     .replace("–", "-")
                     .replace("—", "-")
                     .lstrip("#-• \t")
                     .lstrip()
            )

            # Docling renders the top-level headings as an ordered list and
            # emits its own marker. When the source already carries the number
            # WITHOUT a space after the dot — "2.COMPOSIÇÃO QUALITATIVA E
            # QUANTITATIVA", exactly as printed in the Fludex/indapamida SmPC
            # approved by INFARMED on 28-01-2022 — the conversion produces
            # "2. 2.COMPOSIÇÃO". The compaction just below then reads it as
            # "2.2": section 2 stops existing, and with it the active
            # substance, which is the anchor for every external lookup. The
            # document came out INCOMPLETE in all three models tested, so the
            # cause is the conversion and not the model.
            #
            # Only a number repeated identically is collapsed, and never when
            # a digit follows — "5. 5.2 Propriedades" and "2. 2,5 mg" are left
            # alone.
            linha_limpa = re.sub(r'^(\d+)\.\s+\1\.(?!\d)', r'\1.', linha_limpa)

            # Some PDFs come out of conversion with spaces around the
            # punctuation: "## 4 . 2 Posologia e modo de administração"
            # instead of "4.2". In the folic acid SmPC that made all SEVEN
            # normativas — nem o número casava, nem o reconhecimento por título,
            # because stripping the "4 " prefix left ". 2 Posologia".
            # The number is compacted before anything else.
            linha_limpa = re.sub(r'^(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\b',
                                 r'\1.\2.\3', linha_limpa)
            linha_limpa = re.sub(r'^(\d+)\s*\.\s*(\d+)\b', r'\1.\2', linha_limpa)
            linha_limpa = re.sub(r'^(\d+)\s+\.\s*', r'\1. ', linha_limpa)

            # X.Y sections (e.g. 4.4 Advertências...)
            m = re.match(r'^(?:\d+\.\s*)?(\d+)\.(\d+)\s*(.*)$', linha_limpa)
            if m:
                n1, n2, resto = m.groups()
                resto = resto.strip()

                # Trailing dot on the number: "4.2. Posologia" and
                # "4.5.Interacções" are common spellings in older SmPCs. The
                # dot belongs to the number, it is not mid-sentence
                # punctuation, so it has to be removed BEFORE the
                # suspicious-start check — otherwise the title is rejected and
                # the section is lost.
                #
                # Measured on the lornoxicam SmPC (2007 format): without this,
                # 4.5 and 5.1 were lost, which is where pharmacogenomics
                # lives. Only a single dot is stripped: "..Posologia" stays
                # suspicious.
                resto = re.sub(r"^\.(?!\.)\s*", "", resto)

                suspicious_start = resto.startswith((")", "|", "]", "}", ">", ".", ",", ";", ":"))
                has_letters = bool(re.search(r"[A-Za-zÀ-ÿ]", resto))
                looks_like_table = "|" in resto[:20]

                # A cross-reference in running text, not a heading.
                #
                # SmPC bodies are full of "(ver secção 5.2 Biotransformação)".
                # When conversion breaks the line at that point, what is left
                # is "5.2 Biotransformação)." — it starts with a number and a
                # letter, and was promoted to a heading. The result is worse
                # than losing the section: the real 5.2 was replaced by a
                # sentence fragment, and the content analysed was whatever
                # followed the cross-reference.
                #
                # The tell is a closing parenthesis with no opening one. A
                # legitimate title may contain parentheses, but balanced.
                fecha_a_mais = resto.count(")") > resto.count("(")

                if (resto and has_letters and not suspicious_start
                        and not looks_like_table and not fecha_a_mais):
                    novas.append(f"### {n1}.{n2} {resto}".rstrip())
                    continue

            # X. sections (e.g. 1. Nome do medicamento)
            m = re.match(r'^(?:\d+\.\s*)?(\d+)\.\s*(.*)$', linha_limpa)
            if m:
                n1, resto = m.groups()
                resto = resto.strip()

                suspicious_start = resto.startswith((")", "|", "]", "}", ">", ".", ",", ";", ":"))
                has_letters = bool(re.search(r"[A-Za-zÀ-ÿ]", resto))
                looks_like_table = "|" in resto[:20]

                if resto and has_letters and not suspicious_start and not looks_like_table:
                    novas.append(f"# {n1}. {resto}".rstrip())
                    continue

            novas.append(original)

        return "\n".join(novas)

    def get_markdown_normalizado(self) -> str:
        """
        Return the normalised Markdown, for export or debugging.
        """
        return self.md_text

    # =====================================================
    #              TABLE AND FIGURE EXTRACTION
    # =====================================================
    def extrair_tabelas_e_figuras(self, conteudo: str):
        """
        Find and extract the tables and figures present in a Markdown section.

        - identifies table captions such as "Tabela 1 – ..."
        - extracts table bodies in Markdown form
        - removes duplicates, keeping the most complete caption
        - identifies figures ("Figura 1 – …")

        Args:
            conteudo (str): Texto Markdown bruto da secção.

        Returns:
            tuple: (conteudo_sem_tabelas, tabelas_extraidas, figuras_extraidas)
        """
        tabelas, figuras = [], []

        padrao_tabela_titulo = re.compile(
            r"(Tabela\s*(?:n[ºo\.]?\s*)?(?P<num>\d+)[\.\s:-]*(?P<titulo>[^\n]*))",
            flags=re.IGNORECASE,
        )

        padrao_tabela_markdown = re.compile(
            r"(\|.+\|\n(?:\|[-:]+[-|:]+\|\n)?(?:\|.*\|\n?)+)",
            flags=re.MULTILINE,
        )

        for m in padrao_tabela_titulo.finditer(conteudo):
            numero = m.group("num")
            titulo = m.group("titulo").strip()
            resto = conteudo[m.end():]

            corpo_match = padrao_tabela_markdown.search(resto)
            corpo = (
                corpo_match.group(1).strip()
                if corpo_match and corpo_match.start() < 600
                else ""
            )

            tabelas.append({"numero": numero, "titulo": titulo, "texto": corpo})

        tabelas_final = {}
        for t in tabelas:
            num = t["numero"]
            if num not in tabelas_final or len(t["titulo"]) > len(tabelas_final[num]["titulo"]):
                tabelas_final[num] = t
        tabelas = list(tabelas_final.values())

        conteudo = padrao_tabela_titulo.sub("", conteudo)
        conteudo = padrao_tabela_markdown.sub("", conteudo)

        padrao_figura = re.compile(
            r"(Figura\s*(?P<num>\d+)[\.\s:-]*(?P<descricao>[^\n]+))",
            flags=re.IGNORECASE,
        )

        for m in padrao_figura.finditer(conteudo):
            figuras.append({
                "numero": m.group("num"),
                "descricao": m.group("descricao").strip(),
            })

        conteudo = padrao_figura.sub("", conteudo)
        conteudo = re.sub(r"\n{3,}", "\n\n", conteudo).strip()

        return conteudo, tabelas, figuras

    # =====================================================
    #                4.x AND 5.x SECTION EXTRACTION
    # =====================================================
    def extrair_seccoes_numericas(self):
        """
        Extract the normative sections (4.2, 4.3, 4.4, 4.5, 4.8, 5.1, 5.2),
        using MarkdownHeaderTextSplitter to segment the text by heading.

        Returns:
            The sections found, each with:
                  - number
                  - title
                  - content
                  - tabelas
                  - figuras
        """
        print("🔍 A extrair secções normativas...")

        # Fix the numbering BEFORE segmenting, rather than widening the
        # splitter's heading levels. Widening them would break sections at
        # their "##" subheadings (in the ketamine SmPC, "## Gerais" and
        # "## Utilização de longa duração" are subheadings of 4.4) and
        # truncate the content.
        texto = self._corrigir_numeracao_seccoes(self.md_text)

        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("###", "section")])
        sections = splitter.split_text(texto)
        seccoes = []
        vistos: set[str] = set()

        for sec in sections:
            header = sec.metadata.get("section", "").strip()
            m = re.match(r"^(\d+\.\d+)\s*(.*)$", header)

            if not m:
                continue

            numero, titulo = m.groups()
            titulo = titulo.strip()

            if (
                not titulo
                or titulo.startswith((")", "|", "]", "}", ">", ".", ",", ";", ":"))
                or "|" in titulo
                or not re.search(r"[A-Za-zÀ-ÿ]", titulo)
            ):
                continue

            if numero not in self.SECCOES_NUMERICAS:
                continue

            # The numeric route takes precedence: if 4.5 was already found by
            # number, a similar title further down does not replace it.
            if numero in vistos:
                continue
            vistos.add(numero)

            conteudo = sec.page_content.strip()
            conteudo, tabelas, figuras = self.extrair_tabelas_e_figuras(conteudo)

            conteudo = re.sub(r"^###\s*.*", "", conteudo, flags=re.MULTILINE).strip()

            seccoes.append({
                "numero": numero,
                "titulo": titulo or f"Secção {numero}",
                "content": conteudo,
                "tabelas": tabelas,
                "figuras": figuras,
            })

            print(f"✅ Secção encontrada: {numero} — {titulo or '(sem título)'}")

        if not seccoes:
            print("⚠️ Nenhuma secção normativa detetada.")

        return seccoes

    # =====================================================
    #              MAIN SECTION BLOCK EXTRACTION
    # =====================================================
    def extrair_bloco_secao_principal(self, numero_secao: str) -> str | None:
        """
        Extract the content of a top-level section such as '# 2. ...'
        up to the next top-level section '# X. ...'.
        """
        padrao_header = re.compile(
            rf"^#\s*{re.escape(numero_secao)}\.\s*.*$",
            flags=re.MULTILINE
        )
        m = padrao_header.search(self.md_text)

        if not m:
            return None

        inicio = m.end()
        resto = self.md_text[inicio:]

        prox = re.search(r"^#\s*\d+\.\s*", resto, flags=re.MULTILINE)
        if prox:
            resto = resto[:prox.start()]

        conteudo = resto.strip()
        return conteudo or None

    def extrair_secao_2(self) -> str | None:
        """
        Extract section 2 specifically (qualitative and quantitative
        composition), which is where the active substance is declared.
        """
        return self.extrair_bloco_secao_principal("2")

    # =====================================================
    #                MEDICINE NAME EXTRACTION
    # =====================================================
    def _extrair_nome_medicamento_por_header(self) -> str | None:
        """
        Read the medicine name from section '1. Nome do Medicamento',
        assuming the heading is '# 1. ...' and the name follows immediately.
        """
        padrao_header = re.compile(r"^#\s*1\.\s*(.*)$", flags=re.MULTILINE)
        m = padrao_header.search(self.md_text)

        if not m:
            return None

        inicio = m.end()
        resto = self.md_text[inicio:]

        prox = re.search(r"^#\s*\d+\.", resto, flags=re.MULTILINE)
        if prox:
            resto = resto[:prox.start()]

        nome = resto.strip().split("\n", 1)[0].strip()
        nome = re.sub(r"\s{2,}", " ", nome)

        return nome or None

    # =====================================================
    #            SPECIAL SmPC FIELD EXTRACTION
    # =====================================================
    def extrair_campos_especiais(self):
        """
        Extract the standard SmPC fields:
        - medicine name
        - pharmacotherapeutic group
        - ATC code

        Returns:
            One dictionary per extracted field.
        """
        print("🔍 A procurar campos específicos...")
        resultados = []

        # Nome do Medicamento
        nome = self._extrair_nome_medicamento_por_header()
        if nome:
            resultados.append({
                "numero": "1",
                "titulo": "Nome do Medicamento",
                "content": nome,
                "tabelas": [],
                "figuras": [],
            })

        # Grupo farmacoterapêutico
        grupo, codigo_grupo = self._extrair_grupo_farmacoterapeutico()
        if grupo:
            resultados.append({
                "numero": None,
                "titulo": "Grupo farmacoterapêutico",
                "content": grupo,
                "codigo": codigo_grupo,
                "tabelas": [],
                "figuras": [],
            })

        # Código ATC
        padrao_atc = re.compile(
            r"(?i)ATC[:\s-]*([A-Z][0-9]{2}[A-Z](?:\s?[A-Z0-9]{2,3}))\b"
        )
        m_atc = padrao_atc.search(self.md_text)
        if m_atc:
            resultados.append({
                "numero": None,
                "titulo": "ATC",
                "content": m_atc.group(1).strip(),
                "tabelas": [],
                "figuras": [],
            })

        return resultados

    # =====================================================
    #        GRUPO FARMACOTERAPÊUTICO
    # =====================================================

    # The group label. Every variant below was observed in the 637-SmPC
    # corpus; the earlier version accepted only "Grupo farmacoterapêutico" and
    # failed on 44 documents:
    #   "Grupos farmacoterapêuticos"      (plural)
    #   "Classificação farmacoterapêutica" / "Classe" / "Categoria"
    #   "Grupo fármaco-terapêutico"       (acento + hífen)
    #   "Grupo Fármaco - Terapêutico"     (espaços à volta do hífen)
    _RE_GRUPO_LABEL = re.compile(
        r"(?i)\b(?:grupos?|classifica[çc][ãa]o|classe|categoria)\s+"
        r"f[áa]rmaco\s*[-–—]?\s*terap[êe]utic[oa]s?\b"
    )

    # The ATC label ends the group block. Deliberately without a leading \b:
    # extraction often glues the words together ("dorzolamidaCódigo ATC").
    _RE_ATC_CUT = re.compile(r"(?i)c[oó]digo\s*[-–]?\s*ATC|\bATC\s*:")

    _RE_TRIM = re.compile(r"^[\s:;.\-–—]+|[\s:;,.\-–—]+$")

    # Infarmed hierarchical code at the start of the group, e.g. "8.5.1.2".
    _RE_GRUPO_CODIGO = re.compile(r"^\s*(\d+(?:\.\d+)*)")

    def _extrair_grupo_farmacoterapeutico(self) -> tuple[str | None, str | None]:
        """
        Extract the pharmacotherapeutic group and its hierarchical code.

        Unlike the earlier version, the value is NOT truncated at the first
        line break. Infarmed group names are long and almost always span 2-3
        lines; cutting at the first line fragmented
        77% dos grupos extraídos, inflando artificialmente o número de grupos
        distintos na análise global.

        Returns:
            (grupo, codigo) - ambos None se o rótulo não for encontrado.
        """
        match = self._RE_GRUPO_LABEL.search(self.md_text)
        if not match:
            return None, None

        # Generous window: the longest group in the corpus is ~200 chars.
        bloco = self.md_text[match.end():match.end() + 600]

        # Boundaries, in order of precedence.
        bloco = re.split(r"\n\s*\n", bloco)[0]     # fim do parágrafo
        bloco = self._RE_ATC_CUT.split(bloco)[0]   # antes do código ATC

        # Rejoin hyphenated words split across a line break
        # ("Anti-\nhistamínicos" -> "Anti-histamínicos").
        bloco = re.sub(r"-\s*\n\s*", "-", bloco)

        grupo = re.sub(r"\s+", " ", bloco.replace("\n", " "))

        # Trimming the ends comes FIRST: the block typically starts at
        # ": 4.1.2 …" and, without removing the colon, the code compaction
        # below (anchored on ^\d) never matches.
        grupo = self._RE_TRIM.sub("", grupo)

        # Compact the hierarchical code at the start of the label.
        #
        # Some PDFs come out of conversion with spaces around the dots:
        # "4 . 1 . 2 -Sangue. Antianémicos" instead of "4.1.2". The code is
        # the ONLY stable grouping key — the textual label yields 473 distinct
        # forms for 121 real groups — so one stray space separates documents
        # that belong to the same group, and regrouping after the workbook is
        # built would mean redoing the whole aggregation.
        #
        # Measured on 71 documents: 1 case (folic acid), ~1.4%. Across the
        # 7 800 of the corpus that projects to about 110.
        grupo = re.sub(r"^\s*(\d+)((?:\s*\.\s*\d+)+)",
                       lambda m: m.group(1) + re.sub(r"\s*\.\s*", ".", m.group(2)),
                       grupo)

        # Space before punctuation, also a conversion artefact:
        # "Fertilidade , gravidez" -> "Fertilidade, gravidez". Cosmetic — the
        # label groups nothing — but it saves cleaning the sheets by hand.
        grupo = re.sub(r"\s+([.,;:])", r"\1", grupo)
        grupo = re.sub(r"([.,;:])(?=[^\s\d])", r"\1 ", grupo)
        grupo = re.sub(r"\s{2,}", " ", grupo)

        grupo = self._RE_TRIM.sub("", grupo)

        if not grupo:
            return None, None

        m_codigo = self._RE_GRUPO_CODIGO.match(grupo)
        codigo = m_codigo.group(1) if m_codigo else None

        return grupo, codigo

    # =====================================================
    #        FILE NAME NORMALISATION FOR JSON
    # =====================================================
    @staticmethod
    def normalizar_nome_ficheiro(titulo: str) -> str:
        """
        Turn a title into a safe file name:
        - strip accents;
        - drop special characters;
        - replace spaces with underscores.

        Returns:
            A clean, filesystem-safe name.
        """
        titulo = unicodedata.normalize("NFKD", titulo)
        titulo = "".join(c for c in titulo if not unicodedata.combining(c))
        titulo = re.sub(r"[^a-zA-Z0-9_ ]+", "", titulo)
        titulo = titulo.strip().replace(" ", "_")
        return titulo or "secao_sem_titulo"