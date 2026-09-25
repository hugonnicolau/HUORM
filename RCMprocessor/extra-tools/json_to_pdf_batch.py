#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
json_to_pdf_batch.py
====================

Converte, em batch, os ficheiros JSON produzidos pelo pipeline RCM/PGx num
PDF consolidado por medicamento, pensado para ser lido por pessoas que não
percebem de JSON.

Modo LEITURA (por defeito)
--------------------------
Cada PDF apresenta o CONTEÚDO dos documentos como um texto legível:
  * uma secção de cada vez, pela ordem do RCM (campo ``numero``);
  * o bloco de texto da secção (campo ``content``), com os cabeçalhos ``##``
    e as tabelas em markdown convertidos;
  * quando a secção tem informação farmacogenómica: o(s) excerto(s)
    extraído(s), o respetivo motivo da extração, e as entidades encontradas
    (genes, alelos *, diplótipos, rsIDs) e normalizações;
  * no fim: um resumo farmacogenómico do documento (entidades únicas).
São omitidos os metadados técnicos (contagens brutas, flags, IDs de base de
dados, listas de auditoria, etc.).

Modo RAW (``--raw``)
--------------------
Despeja todo o JSON de forma estruturada (chave/valor, tabelas, aninhamento).

Estrutura de input esperada:

    <input_root>/
        <medicamento_1>/
            <secção>.json ...
            pgx_outputs/
                Extended_PGx_Analysis.json
                Document_Unique_PGx.json
        <medicamento_2>/ ...

Uso:
    python json_to_pdf_batch.py <input_root> [opções]
    python json_to_pdf_batch.py ./outputs
    python json_to_pdf_batch.py ./outputs --inside
    python json_to_pdf_batch.py ./outputs -o ./pdfs --overwrite
    python json_to_pdf_batch.py ./outputs --raw

Dependências:  pip install reportlab
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from time import perf_counter

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
]


def _first_existing(paths, extra=None):
    if extra and Path(extra).exists():
        return str(extra)
    for c in paths:
        if Path(c).exists():
            return c
    return None


def register_fonts(font_path):
    regular = _first_existing(FONT_CANDIDATES, font_path)
    bold = _first_existing(FONT_BOLD_CANDIDATES, None)
    mono = _first_existing(FONT_MONO_CANDIDATES, None)
    mono_name = "Courier"
    if regular:
        try:
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold or regular))
            if mono:
                pdfmetrics.registerFont(TTFont("Body-Mono", mono))
                mono_name = "Body-Mono"
            return "Body", "Body-Bold", mono_name, True
        except Exception as exc:  # pragma: no cover
            print(f"⚠️  Falha ao registar TTF ({exc}); a usar Helvetica.")
    return "Helvetica", "Helvetica-Bold", "Courier", False


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def build_styles(font, font_bold, font_mono):
    base = getSampleStyleSheet()

    def s(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    ink = colors.HexColor("#111827")
    navy = colors.HexColor("#1F2A44")
    grey = colors.HexColor("#6B7280")
    teal = colors.HexColor("#0E7C6B")
    amber = colors.HexColor("#92600A")

    return {
        "med_title": s("MedTitle", fontName=font_bold, fontSize=21, leading=25,
                       textColor=navy, spaceAfter=4),
        "med_sub": s("MedSub", fontName=font, fontSize=9.5, leading=13,
                     textColor=grey, spaceAfter=2),
        "sec_title": s("SecTitle", fontName=font_bold, fontSize=14, leading=18,
                       textColor=navy, spaceBefore=16, spaceAfter=6),
        "content_head": s("ContentHead", fontName=font_bold, fontSize=10.5,
                          leading=14, textColor=colors.HexColor("#374151"),
                          spaceBefore=6, spaceAfter=2),
        "body": s("Body", fontName=font, fontSize=10, leading=14.5,
                  textColor=ink, spaceAfter=4, alignment=TA_LEFT),
        "mono": s("Mono", fontName=font_mono, fontSize=7.5, leading=10,
                  textColor=colors.HexColor("#374151"), spaceAfter=4,
                  backColor=colors.HexColor("#F8FAFC"), borderPadding=(4, 4, 4, 4)),
        "pgx_head": s("PgxHead", fontName=font_bold, fontSize=10.5, leading=14,
                      textColor=teal, spaceBefore=8, spaceAfter=3),
        "pgx_line": s("PgxLine", fontName=font, fontSize=9.5, leading=13.5,
                      textColor=ink, spaceAfter=2, leftIndent=8),
        "pgx_quote": s("PgxQuote", fontName=font, fontSize=9.5, leading=13.5,
                       textColor=colors.HexColor("#374151"), spaceAfter=3,
                       leftIndent=8, backColor=colors.HexColor("#F1F5F4"),
                       borderPadding=(5, 5, 5, 5)),
        "pgx_motivo": s("PgxMotivo", fontName=font, fontSize=9, leading=12.5,
                        textColor=amber, spaceAfter=6, leftIndent=8),
        "tbl_caption": s("TblCaption", fontName=font_bold, fontSize=9, leading=12,
                         textColor=grey, spaceBefore=6, spaceAfter=2),
        "cell": s("Cell", fontName=font, fontSize=8, leading=10.5, textColor=ink),
        "cell_head": s("CellHead", fontName=font_bold, fontSize=8, leading=10.5,
                       textColor=colors.white),
        "file_header": s("FileHeader", fontName=font_bold, fontSize=13, leading=16,
                         textColor=navy, spaceBefore=14, spaceAfter=6),
        "key": s("Key", fontName=font_bold, fontSize=9.5, leading=13,
                 textColor=colors.HexColor("#334155")),
        "value": s("Value", fontName=font, fontSize=9.5, leading=13, textColor=ink),
        "content": s("Content", fontName=font, fontSize=9, leading=13, textColor=ink),
    }


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def esc(text):
    s = "" if text is None else str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\r\n", "\n").replace("\r", "\n")


def esc_multiline(text):
    return esc(text).replace("\n", "<br/>")


def clean_source(text):
    """Des-escapa entidades HTML que o pipeline possa ter deixado no texto."""
    if text is None:
        return ""
    return html.unescape(str(text))


def sanitize_for_helvetica(text):
    repl = {
        "→": "->", "←": "<-", "↔": "<->", "⇒": "=>", "↑": "(+)", "↓": "(-)",
        "✓": "[v]", "✔": "[v]", "✗": "[x]", "✘": "[x]", "•": "-", "–": "-",
        "—": "-", "…": "...", "≥": ">=", "≤": "<=", "≠": "!=", "×": "x",
        "·": ".", "α": "alfa", "β": "beta", "µ": "u", "μ": "u",
        "“": '"', "”": '"', "‘": "'", "’": "'",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")



# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
class Renderer:
    LONG_TEXT_KEYS = {"content", "conteudo", "texto", "informacao_farmacogenomica",
                      "raw", "normalizado", "resumo", "summary", "notes", "nota"}

    def __init__(self, styles, unicode_ok, available_width):
        self.st = styles
        self.unicode_ok = unicode_ok
        self.avail = available_width

    def fix(self, text):
        return text if self.unicode_ok else sanitize_for_helvetica(text)

    def p(self, text, style="body"):
        return Paragraph(self.fix(text), self.st[style])

    # ---------- tabelas (lista de linhas de células) ----------
    def grid(self, rows, col_widths=None):
        if not rows:
            return None
        ncols = max(len(r) for r in rows) or 1
        norm = [list(r) + [""] * (ncols - len(r)) for r in rows]
        header = [Paragraph(self.fix(esc(c)), self.st["cell_head"]) for c in norm[0]]
        data = [header]
        for r in norm[1:]:
            data.append([Paragraph(self.fix(esc_multiline(c)), self.st["cell"]) for c in r])
        if not col_widths:
            col_widths = [self.avail / ncols] * ncols
        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2A44")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F3F4F6")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return tbl

    # ---------- content markdown -> flowables ----------
    def content_flowables(self, text):
        text = clean_source(text)
        flow, para = [], []

        def flush_para():
            if para:
                flow.append(self.p("<br/>".join(esc(x) for x in para), "body"))
                para.clear()

        for raw in text.split("\n"):
            stripped = raw.strip()
            if not stripped:
                flush_para()
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if m:
                flush_para()
                flow.append(self.p(esc(m.group(2)), "content_head"))
                continue
            para.append(stripped)

        flush_para()
        return flow

    # =======================================================================
    # MODO LEITURA
    # =======================================================================
    def render_reading(self, data, filename):
        if self._is_document_unique(data):
            return self._reading_summary(data)
        if self._is_extended(data):
            return self._reading_summary(data, extended=True)
        if self._is_section(data):
            return self._reading_section(data)
        return self._reading_generic(data, filename)

    @staticmethod
    def _is_section(d):
        return isinstance(d, dict) and ("content" in d or "avaliacao_farmacogenomica" in d)

    @staticmethod
    def _is_document_unique(d):
        return isinstance(d, dict) and "entidades" in d and "contagens" in d

    @staticmethod
    def _is_extended(d):
        return isinstance(d, dict) and "frequencias_entidades" in d

    def _reading_section(self, d):
        numero = d.get("numero")
        titulo = d.get("titulo") or "Secção"
        label = f"{numero}. {titulo}" if numero not in (None, "", "null") else str(titulo)
        flow = [self.p(esc(label), "sec_title")]

        content = (d.get("content") or "").strip()
        if content:
            flow.extend(self.content_flowables(content))

        flow.extend(self._reading_section_pgx(d.get("avaliacao_farmacogenomica")))
        flow.append(Spacer(1, 4))
        return flow

    def _reading_section_pgx(self, av):
        if not isinstance(av, dict) or av.get("contem_farmacogenomica") != "Sim":
            return []

        flow = [self.p("Informação farmacogenómica", "pgx_head")]

        excertos = av.get("excertos_farmacogenomicos") or []
        if excertos:
            multi = len(excertos) > 1
            for i, ex in enumerate(excertos, 1):
                if not isinstance(ex, dict):
                    continue
                texto = clean_source(ex.get("texto_original") or "").strip()
                motivo = clean_source(ex.get("motivo_extracao") or "").strip()
                if texto:
                    pref = f"<b>Excerto {i}:</b> " if multi else "<b>Excerto:</b> "
                    flow.append(self.p(pref + esc(texto), "pgx_quote"))
                if motivo:
                    flow.append(self.p("<b>Motivo da extração:</b> " + esc(motivo),
                                       "pgx_motivo"))
        else:
            trecho = clean_source(av.get("informacao_farmacogenomica") or "").strip()
            if trecho:
                flow.append(self.p("<b>Excerto:</b> " + esc(trecho), "pgx_quote"))

        ent = av.get("pgx_entidades") or {}
        for rot, key, idkey in [("Genes", "genes", "symbol"),
                                ("Alelos *", "star_alleles", "variant"),
                                ("Diplótipos", "diplotypes", "variant"),
                                ("rsIDs", "rsids", "variant")]:
            txt = self._join_counts(ent.get(key), idkey)
            if txt:
                flow.append(self.p(f"<b>{rot}:</b> {esc(txt)}", "pgx_line"))

        inc = ent.get("incomplete_star_alleles") or []
        inc_txt = ", ".join((it.get("raw_text") or "").strip()
                            for it in inc if isinstance(it, dict) and it.get("raw_text"))
        if inc_txt:
            flow.append(self.p(f"<b>Alelos * incompletos:</b> {esc(inc_txt)}", "pgx_line"))

        norm = (av.get("normalizacao") or {}).get("nome_extenso_para_simbolo") or []
        pares = [f"{(n.get('original_text') or '').strip()} → {(n.get('normalized_symbol') or '').strip()}"
                 for n in norm if n.get("original_text") and n.get("normalized_symbol")]
        if pares:
            flow.append(self.p("<b>Normalização:</b> " + esc("; ".join(pares)), "pgx_line"))

        return flow

    @staticmethod
    def _join_counts(items, key):
        parts = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            name = (it.get(key) or it.get("entity") or "").strip()
            if not name:
                continue
            m = it.get("total_mentions")
            parts.append(f"{name} ({m})" if m and m > 1 else name)
        return ", ".join(parts)

    def _reading_summary(self, d, extended=False):
        flow = [self.p("Resumo farmacogenómico do documento", "sec_title")]
        doc = d.get("documento") or {}
        for rot, k in [("Medicamento", "nome_medicamento"),
                       ("Substância ativa", "substancia_ativa"),
                       ("Grupo farmacoterapêutico", "grupo_farmacoterapeutico"),
                       ("Código ATC", "codigo_atc")]:
            if doc.get(k):
                flow.append(self.p(f"<b>{rot}:</b> {esc(clean_source(doc[k]))}", "pgx_line"))

        ent = (d.get("frequencias_entidades") if extended else d.get("entidades")) or {}
        any_ent = False
        for title, key in [("Genes", "genes"), ("Alelos *", "star_alleles"),
                           ("Diplótipos", "diplotypes"), ("rsIDs", "rsids")]:
            lines = self._summary_entity_lines(ent.get(key))
            if not lines:
                continue
            any_ent = True
            flow.append(self.p(f"{title} ({len(lines)})", "pgx_head"))
            for ln in lines:
                flow.append(self.p(ln, "pgx_line"))
        if not any_ent:
            flow.append(self.p("Sem entidades farmacogenómicas identificadas.", "pgx_line"))
        flow.append(Spacer(1, 4))
        return flow

    def _summary_entity_lines(self, items):
        out = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            entity = (it.get("entity") or it.get("symbol") or it.get("variant") or "").strip()
            if not entity:
                continue
            bits = [f"<b>{esc(entity)}</b>"]
            if it.get("name"):
                bits.append(f"— {esc(it['name'])}")
            if it.get("gene"):
                bits.append(f"[{esc(it['gene'])}]")
            elif it.get("genes"):
                bits.append(f"[{esc(', '.join(it['genes']))}]")
            m = it.get("total_mentions")
            if m:
                bits.append(f"· {m} menç.")
            if it.get("sections"):
                bits.append(f"(secções {esc(', '.join(str(x) for x in it['sections']))})")
            out.append(" ".join(bits))
        return out

    # ---------- fallback limpo ----------
    DENY_KEYS = {
        "numero", "figuras", "json_file", "section_number", "has_pgx",
        "has_entities", "contagens", "contagens_secao", "contagens_documento",
        "classificacao", "fontes_cruzamento", "evidence_flags", "ids",
        "source_matches", "guideline_ids", "guideline_matches",
        "active_substance_external_references", "active_substance_aliases",
        "seccoes", "entidades_com_guideline", "entidades_sem_guideline",
        "frequencias_entidades", "identificadores_substancia",
    }

    def _reading_generic(self, data, filename):
        flow = [self.p(esc(Path(filename).stem.replace("_", " ").title()), "sec_title")]
        flow.extend(self._clean(data, 0))
        flow.append(Spacer(1, 4))
        return flow

    def _clean(self, data, depth):
        flow = []
        if isinstance(data, dict):
            for k, v in data.items():
                if k in self.DENY_KEYS or v in (None, "", [], {}):
                    continue
                if isinstance(v, (str, int, float, bool)):
                    txt = esc_multiline(clean_source(v)) if isinstance(v, str) else esc(v)
                    flow.append(self.p(f"<b>{esc(k)}:</b> {txt}", "pgx_line"))
                else:
                    flow.append(self.p(f"<b>{esc(k)}</b>", "pgx_head"))
                    flow.extend(self._clean(v, depth + 1))
        elif isinstance(data, list):
            for it in data:
                if isinstance(it, (str, int, float, bool)):
                    flow.append(self.p("• " + esc(clean_source(it)), "pgx_line"))
                else:
                    flow.extend(self._clean(it, depth + 1))
        return flow

    # =======================================================================
    # MODO RAW
    # =======================================================================
    def render_raw(self, data, depth=0):
        if isinstance(data, dict):
            return self._raw_dict(data, depth)
        if isinstance(data, list):
            return self._raw_list(data, depth)
        return [self.p(esc(self._scalar(data)), "value")]

    @staticmethod
    def _scalar(v):
        if isinstance(v, bool):
            return "Sim" if v else "Não"
        return "—" if v is None else str(v)

    def _ind(self, base, depth):
        st = self.st[base].clone(f"{base}_{depth}")
        st.leftIndent = min(depth, 5) * 10
        return st

    def _raw_dict(self, d, depth):
        flow = []
        for key, value in d.items():
            kl = esc(key)
            if isinstance(value, str) and (key.lower() in self.LONG_TEXT_KEYS
                                           or "\n" in value or len(value) > 160):
                flow.append(Paragraph(self.fix(f"<b>{kl}</b>"), self._ind("key", depth)))
                flow.append(Paragraph(self.fix(esc_multiline(clean_source(value))),
                                      self._ind("content", depth)))
                flow.append(Spacer(1, 3))
            elif isinstance(value, (str, int, float, bool)) or value is None:
                flow.append(Paragraph(self.fix(f"<b>{kl}:</b> {esc(self._scalar(value))}"),
                                      self._ind("value", depth)))
            elif isinstance(value, list):
                flow.append(Paragraph(self.fix(f"<b>{kl}</b>"), self._ind("key", depth)))
                flow.extend(self._raw_list(value, depth + 1))
            elif isinstance(value, dict):
                if not value:
                    flow.append(Paragraph(self.fix(f"<b>{kl}:</b> —"), self._ind("value", depth)))
                else:
                    flow.append(Paragraph(self.fix(f"<b>{kl}</b>"), self._ind("key", depth)))
                    flow.extend(self._raw_dict(value, depth + 1))
        return flow

    def _raw_list(self, lst, depth):
        if not lst:
            return [Paragraph("—", self._ind("value", depth))]
        if all(isinstance(x, dict) for x in lst):
            cols = []
            for r in lst:
                for k in r.keys():
                    if k not in cols:
                        cols.append(k)
            if len(cols) <= 8:
                rows = [cols]
                for r in lst:
                    rows.append([
                        json.dumps(r.get(c, ""), ensure_ascii=False)
                        if isinstance(r.get(c), (dict, list)) else str(r.get(c, ""))
                        for c in cols])
                usable = self.avail - min(depth, 5) * 10
                return [self.grid(rows, [usable / len(cols)] * len(cols)), Spacer(1, 4)]
        if all(isinstance(x, (str, int, float, bool)) or x is None for x in lst):
            return [Paragraph("• " + esc(self._scalar(x)), self._ind("value", depth)) for x in lst]
        flow = []
        for i, item in enumerate(lst, 1):
            flow.append(Paragraph(self.fix(f"<b>[{i}]</b>"), self._ind("value", depth)))
            flow.extend(self.render_raw(item, depth + 1))
        return flow


# ---------------------------------------------------------------------------
# Recolha + ordenação (pelo campo "numero" de dentro do JSON)
# ---------------------------------------------------------------------------
def _numero_key(num):
    if num in (None, "", "null"):
        return None
    parts = re.split(r"[.\-_]", str(num).strip())
    key = []
    for p in parts:
        key.append(int(p) if p.isdigit() else 0)
    return tuple(key)


def load_and_sort(med_dir, reading_mode):
    items = []
    for p in med_dir.rglob("*.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = None
        items.append((p, data))

    if reading_mode:
        names = {p.name for p, _ in items}
        if "Document_Unique_PGx.json" in names:
            items = [(p, d) for p, d in items if p.name != "Extended_PGx_Analysis.json"]

    pgx_priority = {"Document_Unique_PGx.json": 900, "Extended_PGx_Analysis.json": 901}

    def sortkey(item):
        p, data = item
        if "pgx_outputs" in p.parts or p.name in pgx_priority:
            return (3, (pgx_priority.get(p.name, 950),), p.name.lower())
        nk = _numero_key(data.get("numero")) if isinstance(data, dict) else None
        if nk is not None:
            return (1, nk, "")
        titulo = (data.get("titulo") if isinstance(data, dict) else "") or p.stem
        return (2, (0,), str(titulo).lower())

    items.sort(key=sortkey)
    return items


# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
def make_footer(med_name, font):
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.HexColor("#9CA3AF"))
        w, _ = A4
        canvas.drawString(18 * mm, 10 * mm, med_name[:80])
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Pág. {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
        canvas.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
        canvas.restoreState()
    return _footer


# ---------------------------------------------------------------------------
# PDF de um medicamento
# ---------------------------------------------------------------------------
def build_medicine_pdf(med_dir, out_path, styles, font, unicode_ok, reading):
    items = load_and_sort(med_dir, reading)
    if not items:
        return 0

    # nome legível do medicamento (do Document_Unique/Extended, se existir)
    display_name = med_dir.name
    for _, data in items:
        if isinstance(data, dict):
            nm = (data.get("documento") or {}).get("nome_medicamento")
            if nm:
                display_name = nm
                break

    margin = 18 * mm
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            leftMargin=margin, rightMargin=margin,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=display_name)
    R = Renderer(styles, unicode_ok, doc.width)

    def fx(t):
        return t if unicode_ok else sanitize_for_helvetica(t)

    story = [Paragraph(fx(esc(display_name)), styles["med_title"])]
    modo = "leitura" if reading else "estruturado (raw)"
    story.append(Paragraph(fx(f"Conteúdo consolidado · modo {modo} · "
                              f"{len(items)} secção(ões)"), styles["med_sub"]))
    story.append(Paragraph(fx(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}"), styles["med_sub"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))

    for jf, data in items:
        rel = jf.relative_to(med_dir).as_posix()
        if data is None:
            story.append(Paragraph(fx(f"⚠️ Erro ao ler {esc(rel)}"), styles["body"]))
            continue
        if reading:
            block = R.render_reading(data, jf.name)
        else:
            block = [Paragraph(fx(f"{esc(rel)}"), styles["file_header"])] + R.render_raw(data)
        story.append(KeepTogether(block[:2]))
        story.extend(block[2:])

    doc.build(story, onFirstPage=make_footer(display_name, font),
              onLaterPages=make_footer(display_name, font))
    return len(items)


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
def run_batch(args):
    input_root = Path(args.input_root).resolve()
    if not input_root.exists():
        sys.exit(f"❌ Pasta de input não encontrada: {input_root}")

    reading = not args.raw
    font, font_bold, font_mono, unicode_ok = register_fonts(args.font)
    styles = build_styles(font, font_bold, font_mono)
    if not unicode_ok:
        print("⚠️  Fonte Unicode não encontrada — a usar Helvetica (símbolos → ASCII).")

    med_dirs = sorted(d for d in input_root.iterdir()
                      if d.is_dir() and any(d.rglob("*.json")))
    if not med_dirs:
        sys.exit(f"❌ Nenhuma subpasta com JSON encontrada em: {input_root}")

    default_out = None
    if not args.inside:
        default_out = (Path(args.output_dir).resolve() if args.output_dir
                       else input_root / "_pdfs")
        default_out.mkdir(parents=True, exist_ok=True)

    print(f"📂 Input : {input_root}")
    print(f"📦 Medicamentos: {len(med_dirs)}")
    print(f"📖 Modo  : {'leitura' if reading else 'raw (estruturado)'}")
    print(f"🖋  Fonte : {font}{'  (Unicode)' if unicode_ok else ''}")
    print(f"📄 Saída : {'dentro de cada pasta' if args.inside else default_out}\n")

    t0 = perf_counter()
    results = []
    for i, med_dir in enumerate(med_dirs, 1):
        out_path = (med_dir / f"{med_dir.name}.pdf") if args.inside \
            else default_out / f"{med_dir.name}.pdf"
        if out_path.exists() and not args.overwrite:
            print(f"[{i}/{len(med_dirs)}] ⏭  {med_dir.name} (já existe)")
            results.append((med_dir.name, "saltado", 0))
            continue
        try:
            n = build_medicine_pdf(med_dir, out_path, styles, font, unicode_ok, reading)
            state = "vazio" if n == 0 else "ok"
            icon = "⚠️" if n == 0 else "✅"
            print(f"[{i}/{len(med_dirs)}] {icon} {med_dir.name} ({n} JSON)")
            results.append((med_dir.name, state, n))
        except Exception:
            print(f"[{i}/{len(med_dirs)}] ❌ {med_dir.name}")
            traceback.print_exc()
            results.append((med_dir.name, "erro", 0))

    dur = perf_counter() - t0
    ok = sum(1 for _, s, _ in results if s == "ok")
    skip = sum(1 for _, s, _ in results if s == "saltado")
    err = sum(1 for _, s, _ in results if s == "erro")
    print("\n" + "=" * 48)
    print(f"Concluído em {dur:.1f}s  ·  ✅ {ok}  ⏭ {skip}  ❌ {err}")
    print("=" * 48)

    log_root = default_out if not args.inside else input_root
    log_path = log_root / f"Log_JSON_para_PDF_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = [f"Data: {datetime.now():%d/%m/%Y %H:%M}", f"Duração: {dur:.1f}s",
             f"Modo: {'leitura' if reading else 'raw'}", f"Input: {input_root}",
             "", "Medicamento - Estado - Nº JSON"]
    lines += [f"{n} - {s} - {c}" for n, s, c in results]
    lines += ["", f"Gerados: {ok} | Saltados: {skip} | Erros: {err}"]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"📝 Log: {log_path}")


def parse_args():
    p = argparse.ArgumentParser(
        description="Converte, em batch, os JSON de cada medicamento num PDF consolidado.")
    p.add_argument("input_root", help="Pasta raiz com uma subpasta por medicamento.")
    p.add_argument("-o", "--output-dir", default=None,
                   help="Pasta de saída (default: <input_root>/_pdfs).")
    p.add_argument("--inside", action="store_true",
                   help="Guardar o PDF dentro da pasta de cada medicamento.")
    p.add_argument("--overwrite", action="store_true",
                   help="Regenerar PDFs já existentes (default: saltar).")
    p.add_argument("--raw", action="store_true",
                   help="Dump estruturado completo do JSON.")
    p.add_argument("--font", default=None, help="Caminho para uma .ttf Unicode.")
    return p.parse_args()


if __name__ == "__main__":
    run_batch(parse_args())