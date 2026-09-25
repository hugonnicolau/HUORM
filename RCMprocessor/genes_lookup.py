from __future__ import annotations
import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Iterable


@dataclass(frozen=True)
class GeneRecord:
    pharmgkb_id: str
    ncbi_gene_id: str
    hgnc_id: str
    ensembl_id: str
    name: str
    symbol: str


class GenesLookup:
    """
    Lê genes.tsv (ClinPGx/PharmGKB) e permite:
      - get(symbol): record por símbolo oficial
      - resolve_symbol(term): resolve símbolo, alias ou nome extenso -> símbolo oficial (UPPER)
      - all_terms(): termos para lexicon
    """

    def __init__(self, genes_tsv_path: Path):
        self.genes_tsv_path = Path(genes_tsv_path)
        if not self.genes_tsv_path.exists():
            raise FileNotFoundError(f"genes.tsv não encontrado: {self.genes_tsv_path}")

        self._by_symbol: Dict[str, GeneRecord] = {}
        self._alias_to_symbol: Dict[str, str] = {}
        self._load()

    def _normalize_key(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.upper().strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _split_aliases(self, raw: str) -> Iterable[str]:
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p and len(p) <= 120]

    def _add_mapping(self, term: str, symbol: str) -> None:
        key = self._normalize_key(term)
        if key:
            self._alias_to_symbol.setdefault(key, symbol)

    def _load(self) -> None:
        with self.genes_tsv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                symbol = (row.get("Symbol") or "").strip()
                if not symbol:
                    continue

                rec = GeneRecord(
                    pharmgkb_id=(row.get("PharmGKB Accession Id") or "").strip(),
                    ncbi_gene_id=(row.get("NCBI Gene ID") or "").strip(),
                    hgnc_id=(row.get("HGNC ID") or "").strip(),
                    ensembl_id=(row.get("Ensembl Id") or "").strip(),
                    name=(row.get("Name") or "").strip(),
                    symbol=symbol.strip(),
                )

                sym_u = symbol.upper()
                self._by_symbol[sym_u] = rec

                # símbolo oficial
                self._add_mapping(symbol, sym_u)

                # aliases
                alt = (row.get("Alternate Symbols") or "").strip()
                for a in self._split_aliases(alt):
                    self._add_mapping(a, sym_u)

                # nome extenso do gene
                if rec.name:
                    self._add_mapping(rec.name, sym_u)

    def get(self, symbol: str) -> Optional[GeneRecord]:
        if not symbol:
            return None
        return self._by_symbol.get(symbol.upper())

    def resolve_symbol(self, term: str) -> Optional[str]:
        if not term:
            return None
        return self._alias_to_symbol.get(self._normalize_key(term))

    def all_terms(self, include_aliases: bool = True) -> Set[str]:
        if not include_aliases:
            return set(self._by_symbol.keys())
        return set(self._alias_to_symbol.keys())