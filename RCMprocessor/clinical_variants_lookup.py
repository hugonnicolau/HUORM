from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from .substance_utils import build_queries, matches_any


@dataclass(frozen=True)
class ClinicalVariantRecord:
    variant: str
    gene: str
    type: str
    level_of_evidence: str
    chemicals: str
    phenotypes: str


class ClinicalVariantsLookup:
    """
    Lê clinicalVariants.tsv e permite:
      - all_terms(): obter todas as variantes individuais para construir o lexicon
      - get_all(variant): obter todos os registos completos de uma variante específica
      - get_best_match(variant, active_substance, aliases): obter um match único
      - get_all_matches(variant, active_substance, aliases): obter todos os matches
        compatíveis com a substância ativa
      - has_term(variant): verificar se a variante existe
    """

    def __init__(self, tsv_path: Path):
        self.tsv_path = Path(tsv_path)
        if not self.tsv_path.exists():
            raise FileNotFoundError(f"clinicalVariants.tsv não encontrado: {self.tsv_path}")

        self._by_variant: Dict[str, List[ClinicalVariantRecord]] = {}
        self._terms: Set[str] = set()
        self._load()

    def _split_variants_field(self, raw: str) -> List[str]:
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]

    def _normalize(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.lower().strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _split_chemicals(self, raw: str) -> List[str]:
        if not raw:
            return []
        parts = re.split(r"[;,|]", raw)
        return [p.strip() for p in parts if p.strip()]

    def _build_normalized_candidates(
        self,
        active_substance: Optional[str],
        aliases: Optional[List[str]],
    ) -> List[str]:
        # Combinações ("paracetamol + tiocolquicosido") têm de ser partidas nos
        # seus componentes: o campo `chemicals` do ClinPGx lista os fármacos
        # individualmente, pelo que a string combinada nunca corresponde a nada.
        # 122 dos 643 RCMs do corpus (19%) são combinações e falhavam aqui em
        # silêncio. build_queries() é o mesmo splitter usado pelo
        # ActiveSubstanceExternalResolver, e mantém também a string completa
        # para o único registo ClinPGx que é ele próprio uma combinação
        # ("sulfamethoxazole / trimethoprim", PA166279741).
        candidates: List[str] = build_queries(active_substance, aliases)

        seen = set()
        normalized_candidates = []
        for c in candidates:
            norm = self._normalize(c)
            if norm and norm not in seen:
                seen.add(norm)
                normalized_candidates.append(norm)

        return normalized_candidates

    def _record_matches_candidates(
        self,
        rec: ClinicalVariantRecord,
        normalized_candidates: List[str],
    ) -> bool:
        if not normalized_candidates:
            return False

        chemicals = self._split_chemicals(rec.chemicals)

        # match exato
        for chem in chemicals:
            chem_norm = self._normalize(chem)
            if chem_norm in normalized_candidates:
                return True

        # match parcial, agora com fronteiras de palavra: o substring nu fazia
        # "iron" corresponder a "sp[iron]olactone".
        for chem in chemicals:
            if matches_any(chem, normalized_candidates):
                return True

        return False

    def _load(self) -> None:
        with self.tsv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")

            for row in reader:
                raw_variant = (row.get("variant") or "").strip()
                if not raw_variant:
                    continue

                gene = (row.get("gene") or "").strip()
                type_ = (row.get("type") or "").strip()
                level = (row.get("level of evidence") or "").strip()
                chemicals = (row.get("chemicals") or "").strip()
                phenotypes = (row.get("phenotypes") or "").strip()

                for variant in self._split_variants_field(raw_variant):
                    rec = ClinicalVariantRecord(
                        variant=variant,
                        gene=gene,
                        type=type_,
                        level_of_evidence=level,
                        chemicals=chemicals,
                        phenotypes=phenotypes,
                    )

                    key = variant.upper()
                    self._terms.add(key)
                    self._by_variant.setdefault(key, []).append(rec)

    def all_terms(self) -> Set[str]:
        return set(self._terms)

    def get_all(self, variant: str) -> List[ClinicalVariantRecord]:
        if not variant:
            return []
        return list(self._by_variant.get(variant.upper(), []))

    def get(self, variant: str) -> Optional[ClinicalVariantRecord]:
        """
        Compatibilidade retroativa.
        Se existirem várias entradas, devolve a primeira.
        """
        records = self.get_all(variant)
        return records[0] if records else None

    def get_best_match(
        self,
        variant: str,
        active_substance: Optional[str] = None,
        aliases: Optional[List[str]] = None,
    ) -> Optional[ClinicalVariantRecord]:
        """
        Devolve um único match.

        - Se houver contexto de substância ativa, tenta match real com chemicals
        - Se não encontrar, devolve None
        - Se não houver contexto nenhum, devolve o primeiro registo
        """
        records = self.get_all(variant)
        if not records:
            return None

        normalized_candidates = self._build_normalized_candidates(
            active_substance=active_substance,
            aliases=aliases,
        )

        if not normalized_candidates:
            return records[0]

        for rec in records:
            if self._record_matches_candidates(rec, normalized_candidates):
                return rec

        return None

    def get_all_matches(
        self,
        variant: str,
        active_substance: Optional[str] = None,
        aliases: Optional[List[str]] = None,
    ) -> List[ClinicalVariantRecord]:
        """
        Devolve todos os registos da variante compatíveis com a substância ativa.

        - Se houver substância ativa/aliases, devolve só os matches reais
        - Se não houver contexto, devolve todos os registos da variante
        """
        records = self.get_all(variant)
        if not records:
            return []

        normalized_candidates = self._build_normalized_candidates(
            active_substance=active_substance,
            aliases=aliases,
        )

        if not normalized_candidates:
            return records

        matches = []
        for rec in records:
            if self._record_matches_candidates(rec, normalized_candidates):
                matches.append(rec)

        return matches


    def get_all_matches_for_gene(
        self,
        gene: str,
        active_substance: Optional[str] = None,
        aliases: Optional[List[str]] = None,
    ) -> List[ClinicalVariantRecord]:
        """
        Devolve todos os registos de clinicalVariants.tsv associados a um gene,
        opcionalmente filtrados pela substância ativa/aliases.

        Útil para distinguir:
        - gene reconhecido em genes.tsv;
        - gene com evidência de variante clínica em clinicalVariants.tsv.
        """
        if not gene:
            return []

        gene_norm = self._normalize(gene)
        normalized_candidates = self._build_normalized_candidates(
            active_substance=active_substance,
            aliases=aliases,
        )

        out: List[ClinicalVariantRecord] = []
        seen = set()

        for records in self._by_variant.values():
            for rec in records:
                if self._normalize(rec.gene) != gene_norm:
                    continue

                if normalized_candidates and not self._record_matches_candidates(rec, normalized_candidates):
                    continue

                key = (rec.variant, rec.gene, rec.type, rec.level_of_evidence, rec.chemicals, rec.phenotypes)
                if key in seen:
                    continue
                seen.add(key)
                out.append(rec)

        return out

    def has_term(self, variant: str) -> bool:
        if not variant:
            return False
        return variant.upper() in self._terms