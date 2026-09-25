from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set
import merpy


@dataclass(frozen=True)
class PGxEntities:
    genes: List[str]
    star_alleles: List[str]
    rsids: List[str]


class MinimalPGxNER:
    """
    NER com merpy em 2 lexicons:
      - genes: termos do genes.tsv
      - variants: termos do clinicalVariants.tsv

    O matching é feito em minúsculas para ser consistente com o merpy.
    """

    def __init__(
        self,
        genes_lookup,
        clinical_variants_lookup,
        genes_lexicon_name: str = "clinpgxgenes",
        variants_lexicon_name: str = "clinpgxvariants",
    ):
        self.genes_lookup = genes_lookup
        self.clinvars = clinical_variants_lookup
        self.genes_lexicon_name = genes_lexicon_name
        self.variants_lexicon_name = variants_lexicon_name

        genes_terms = sorted(
            t.lower() for t in self.genes_lookup.all_terms(include_aliases=False) if t
        )
        vars_terms = sorted(
            t.lower() for t in self.clinvars.all_terms() if t
        )

        self._ensure_lexicon(self.genes_lexicon_name, genes_terms)
        self._ensure_lexicon(self.variants_lexicon_name, vars_terms)

    def _ensure_lexicon(self, name: str, terms: List[str]) -> None:
        if name in merpy.get_lexicons():
            return
        merpy.create_lexicon(terms, name)
        merpy.process_lexicon(name)

    def _terms_from_merpy(self, text: str, lexicon_name: str) -> Set[str]:
        if not text or not text.strip():
            return set()

        try:
            ents = merpy.get_entities(text, lexicon_name)
        except Exception:
            return set()

        found: Set[str] = set()

        for e in ents or []:
            if isinstance(e, (list, tuple)) and len(e) >= 3:
                term = str(e[2]).strip()
                if term:
                    found.add(term)
            elif isinstance(e, str):
                term = e.strip()
                if term:
                    found.add(term)

        return found

    def extract(self, text: str) -> PGxEntities:
        txt = (text or "").lower()

        # -------- GENES --------
        gene_terms = self._terms_from_merpy(txt, self.genes_lexicon_name)
        genes: Set[str] = set()

        for t in gene_terms:
            raw = (t or "").strip()
            if not raw:
                continue

            has_digit = any(ch.isdigit() for ch in raw)
            if not has_digit:
                continue

            sym = raw.upper()
            rec = self.genes_lookup.get(sym)
            if rec:
                genes.add(rec.symbol)

        # -------- VARIANTS --------
        var_terms = self._terms_from_merpy(txt, self.variants_lexicon_name)

        star_alleles = sorted({v.upper() for v in var_terms if "*" in v})
        rsids = sorted({v.lower() for v in var_terms if v.lower().startswith("rs")})

        return PGxEntities(
            genes=sorted(genes),
            star_alleles=star_alleles,
            rsids=rsids,
        )