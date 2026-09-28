#!/usr/bin/env python3
"""Refaz, nas saídas já gravadas, a associação de cada RCM às guidelines do ClinPGx.

Porque existe
-------------
A corrida nacional associou alguns RCM a guidelines de outros fármacos. Uma
palavra de sal ou genérica bastava para a ligação: "cloridrato" separado de
"beta-histina, cloridrato" chegava às guidelines da imipramina e do
irinotecano; "sodium" ligava o soro fisiológico ao nitrato de sódio da lista
do G6PD; "acid" ligava qualquer ácido ao ácido fólico; o "K" do potássio ligava
os sais de potássio a "Vitamin K and analogues". Outras ligações vinham de
sinónimos do UMLS obtidos por correspondência parcial (paracetamol + cafeína
chegava à aspirina através de uma marca que junta os três) ou de
estereoisómeros (o escitalopram herdava a guideline do citalopram).

As regras corrigidas estão em RCMprocessor/substance_utils.py e em
RCMprocessor/active_substance_external_resolver.py (REGRAS_CLINPGX). Este
script aplica-as às saídas que já existem, sem chamar o modelo e sem rede: usa
o resultado do MRCONSO gravado em cada Extended_PGx_Analysis.json.

O que muda em cada documento
----------------------------
* active_substance_external_references.clinpgx: refeito com as regras novas.
* Em cada entidade (gene, alelo, diplótipo, rsID): guideline_ids e
  guideline_matches ficam só com as guidelines que continuam associadas à
  substância; has_guideline e as contagens *_com_guideline_total acompanham.
* A extracção em si (entidades, menções, secções, passagens) não é tocada.

Uso, a partir de FINALV2:
    python extra-tools/preparacao/recalcular_guidelines.py out_nacional \\
        --copia correcao_guidelines/antes

Os ficheiros alterados são copiados para --copia antes de serem reescritos, e
cada alteração fica registada em <copia>/../ALTERACOES.csv. Correr duas vezes
não muda nada da segunda: o resultado depende só das regras e do que está
gravado.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from RCMprocessor.active_substance_external_resolver import (  # noqa: E402
    ActiveSubstanceExternalResolver as Resolver,
    REGRAS_CLINPGX,
)

CATEGORIAS = ("genes", "star_alleles", "diplotypes", "rsids")
CONTAGENS = {
    "genes": "genes_com_guideline_total",
    "star_alleles": "star_alleles_com_guideline_total",
    "diplotypes": "diplotipos_com_guideline_total",
    "rsids": "rsids_com_guideline_total",
}


def _filtrar_entidade(item: dict, validas: set[str]) -> None:
    """Deixa na entidade só as guidelines que continuam associadas."""
    if not isinstance(item, dict):
        return
    if isinstance(item.get("guideline_ids"), list):
        item["guideline_ids"] = [g for g in item["guideline_ids"] if g in validas]
    if isinstance(item.get("guideline_matches"), list):
        item["guideline_matches"] = [
            m for m in item["guideline_matches"]
            if isinstance(m, dict) and m.get("guideline_id") in validas
        ]
    tem = bool(item.get("guideline_ids") or item.get("guideline_matches"))
    if isinstance(item.get("evidence_flags"), dict):
        item["evidence_flags"]["has_guideline"] = tem
    if isinstance(item.get("source_matches"), dict):
        item["source_matches"]["clinpgx_guideline_json"] = tem
    ids = item.get("ids")
    if isinstance(ids, dict) and isinstance(ids.get("guideline_ids"), list):
        ids["guideline_ids"] = [g for g in ids["guideline_ids"] if g in validas]


def recalcular(resolver: Resolver, extended: dict, unico: dict | None) -> tuple[list[str], list[str]]:
    """Reescreve os dois JSON em memória. Devolve (guidelines antes, depois)."""
    refs = extended.setdefault("active_substance_external_references", {})
    antes = [m.get("guideline_id") for m in (refs.get("clinpgx") or {}).get("matches") or []]

    consultas = resolver._build_queries(
        extended.get("active_substance"), extended.get("active_substance_aliases"))
    # Só os blocos do MRCONSO das consultas que as regras actuais produzem: é o
    # que resolve() teria à frente numa corrida nova.
    mrconso = dict(refs.get("mrconso") or {})
    blocos = mrconso.get("results_by_substance") or {}
    mrconso["results_by_substance"] = {q: b for q, b in blocos.items() if q in consultas}
    expandidas = resolver._expandir_com_sinonimos(consultas, mrconso)
    refs["clinpgx"] = resolver._resolve_clinpgx(expandidas)
    refs["clinpgx"]["regras_clinpgx"] = REGRAS_CLINPGX
    depois = [m.get("guideline_id") for m in refs["clinpgx"].get("matches") or []]
    validas = set(depois)

    freq = extended.get("frequencias_entidades") or {}
    for cat in CATEGORIAS:
        for item in freq.get(cat) or []:
            _filtrar_entidade(item, validas)
    extended["entidades_com_guideline"] = {
        cat: [x for x in freq.get(cat) or [] if (x.get("evidence_flags") or {}).get("has_guideline")]
        for cat in CATEGORIAS}
    extended["entidades_sem_guideline"] = {
        cat: [x for x in freq.get(cat) or [] if not (x.get("evidence_flags") or {}).get("has_guideline")]
        for cat in CATEGORIAS}
    contagens = extended.get("contagens_documento")
    if isinstance(contagens, dict):
        for cat, chave in CONTAGENS.items():
            contagens[chave] = len(extended["entidades_com_guideline"][cat])
    fontes = extended.get("fontes_cruzamento")
    if isinstance(fontes, dict):
        fontes["clinpgx_guideline_json"] = bool(depois)

    if unico is not None:
        for cat in CATEGORIAS:
            for item in (unico.get("entidades") or {}).get(cat) or []:
                _filtrar_entidade(item, validas)
        if isinstance(unico.get("contagens"), dict):
            for cat, chave in CONTAGENS.items():
                unico["contagens"][chave] = sum(
                    1 for x in (unico.get("entidades") or {}).get(cat) or []
                    if (x.get("ids") or {}).get("guideline_ids"))

    return antes, depois


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raiz", type=Path, help="pasta das saídas, p. ex. out_nacional")
    ap.add_argument("--copia", type=Path, required=True,
                    help="onde guardar os ficheiros originais que forem alterados")
    ap.add_argument("--data", type=Path, default=RAIZ / "RCMprocessor" / "data")
    args = ap.parse_args()

    # Cache própria e vazia: este script não consulta a rede nem deve tocar
    # na cache da corrida.
    resolver = Resolver(
        data_dir=args.data,
        cache_path=Path(tempfile.gettempdir()) / "recalcular_guidelines_cache.json",
    )
    # As 217 anotações do ClinPGx lêem-se uma vez, não uma vez por documento.
    registos = resolver._load_clinpgx_annotation_files()
    resolver._load_clinpgx_annotation_files = lambda: registos
    registo = []
    n_doc = n_alt = 0
    for pasta in sorted(p for p in args.raiz.iterdir() if p.is_dir()):
        ext_p = pasta / "pgx_outputs" / "Extended_PGx_Analysis.json"
        uni_p = pasta / "pgx_outputs" / "Document_Unique_PGx.json"
        if not ext_p.exists():
            continue
        n_doc += 1
        original_ext = ext_p.read_text(encoding="utf-8")
        original_uni = uni_p.read_text(encoding="utf-8") if uni_p.exists() else None
        extended = json.loads(original_ext)
        unico = json.loads(original_uni) if original_uni else None

        antes, depois = recalcular(resolver, extended, unico)
        novo_ext = json.dumps(extended, ensure_ascii=False, indent=2)
        novo_uni = json.dumps(unico, ensure_ascii=False, indent=2) if unico is not None else None
        if sorted(antes) == sorted(depois) and set(antes) == set(depois):
            # Sem mudança de associações; nada a reescrever.
            continue

        n_alt += 1
        destino = args.copia / pasta.name / "pgx_outputs"
        destino.mkdir(parents=True, exist_ok=True)
        if not (destino / ext_p.name).exists():
            shutil.copy2(ext_p, destino / ext_p.name)
        if uni_p.exists() and not (destino / uni_p.name).exists():
            shutil.copy2(uni_p, destino / uni_p.name)
        ext_p.write_text(novo_ext, encoding="utf-8")
        if novo_uni is not None:
            uni_p.write_text(novo_uni, encoding="utf-8")
        registo.append({
            "documento": pasta.name,
            "substancia": extended.get("active_substance") or "",
            "removidas": " ".join(sorted(set(antes) - set(depois))),
            "acrescentadas": " ".join(sorted(set(depois) - set(antes))),
            "antes": len(set(antes)),
            "depois": len(set(depois)),
        })

    if registo:
        csv_p = args.copia.parent / "ALTERACOES.csv"
        novo = not csv_p.exists()
        with csv_p.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(registo[0].keys()))
            if novo:
                w.writeheader()
            w.writerows(registo)

    print(f"{n_doc} documentos lidos; {n_alt} com associações alteradas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
