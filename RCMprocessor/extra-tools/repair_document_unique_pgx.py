from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class DocumentUniquePGxRepair:
    """
    Repara Document_Unique_PGx.json sem voltar a correr o batch.

    Faz duas coisas principais:
    1. Recalcula as menções reais a partir dos JSONs individuais das secções.
    2. Renomeia identificadores_substancia.mrconso_cui para identificadores_substancia.umls_cui.

    Fonte oficial para menções:
    - JSONs individuais das secções na pasta principal do documento.

    Fonte para preservar enriquecimento:
    - Document_Unique_PGx.json antigo.
    """

    PGX_OUTPUTS_DIRNAME = "pgx_outputs"
    UNIQUE_FILENAME = "Document_Unique_PGx.json"
    BACKUP_SUFFIX = ".bak"

    SPECIAL_FILES = {
        "Document_Unique_PGx.json",
        "Extended_PGx_Analysis.json",
        "Resumo_PGx_Extended.json",
        "Resumo_Entidades_PGx.json",
        "Analise_Global_PGx.json",
        "Nome_do_Medicamento.json",
        "Grupo_farmacoterapeutico.json",
        "ATC.json",
        "Substancia_ativa.json",
        "Substância_ativa.json",
    }

    def __init__(self, outputs_root: str | Path, dry_run: bool = False):
        self.outputs_root = Path(outputs_root).resolve()
        self.dry_run = dry_run

        if not self.outputs_root.exists():
            raise FileNotFoundError(f"Pasta não encontrada: {self.outputs_root}")

    # =====================================================
    # IO
    # =====================================================
    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _safe_dict(self, value: Any) -> dict:
        return value if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list:
        return value if isinstance(value, list) else []

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    # =====================================================
    # PATHS
    # =====================================================
    def _doc_dirs(self) -> list[Path]:
        return sorted([p for p in self.outputs_root.iterdir() if p.is_dir()])

    def _unique_path(self, doc_dir: Path) -> Path | None:
        candidates = [
            doc_dir / self.PGX_OUTPUTS_DIRNAME / self.UNIQUE_FILENAME,
            doc_dir / self.UNIQUE_FILENAME,
        ]

        for path in candidates:
            if path.exists():
                return path

        return None

    def _section_jsons(self, doc_dir: Path) -> list[Path]:
        """
        Fonte oficial das contagens: JSONs individuais na pasta principal do documento.
        """

        out = []

        for path in sorted(doc_dir.glob("*.json")):
            if path.name in self.SPECIAL_FILES:
                continue

            try:
                data = self._read_json(path)
            except Exception:
                continue

            avaliacao = self._safe_dict(data.get("avaliacao_farmacogenomica"))
            entidades = self._safe_dict(avaliacao.get("pgx_entidades"))

            if entidades:
                out.append(path)

        return out

    # =====================================================
    # IDENTIFICADORES
    # =====================================================
    def _repair_identifiers(self, unique_data: dict) -> tuple[dict, bool]:
        """
        Converte:
        identificadores_substancia.mrconso_cui -> identificadores_substancia.umls_cui

        Mantém compatibilidade:
        - se umls_cui já existir, preserva;
        - se só existir mrconso_cui, copia o valor para umls_cui e remove mrconso_cui.
        """

        data = dict(unique_data)
        ids = self._safe_dict(data.get("identificadores_substancia"))

        changed = False

        if "mrconso_cui" in ids:
            if not ids.get("umls_cui"):
                ids["umls_cui"] = ids.get("mrconso_cui", "")
            ids.pop("mrconso_cui", None)
            changed = True

        data["identificadores_substancia"] = ids

        return data, changed

    # =====================================================
    # ENTIDADES
    # =====================================================
    def _entity_value(self, item: dict, category: str) -> str:
        if category == "genes":
            return str(
                item.get("symbol")
                or item.get("entity")
                or item.get("gene")
                or ""
            ).strip()

        return str(
            item.get("entity")
            or item.get("variant")
            or item.get("symbol")
            or item.get("rsid")
            or ""
        ).strip()

    def _section_label(self, section_data: dict, fallback_stem: str) -> str:
        number = str(
            section_data.get("numero")
            or section_data.get("section_number")
            or ""
        ).strip()

        if number:
            return number

        title = str(
            section_data.get("titulo")
            or section_data.get("section_title")
            or fallback_stem
        ).strip()

        return title

    def _section_display(self, section_data: dict, fallback_stem: str) -> str:
        number = str(
            section_data.get("numero")
            or section_data.get("section_number")
            or ""
        ).strip()

        title = str(
            section_data.get("titulo")
            or section_data.get("section_title")
            or fallback_stem
        ).strip()

        return f"{number} {title}".strip()

    def _entity_mentions(self, item: dict) -> int:
        for key in ["total_mentions", "mentions", "count", "occurrences"]:
            n = self._to_int(item.get(key), 0)
            if n > 0:
                return n
        return 1

    def _old_entities_by_key(self, unique_data: dict) -> dict[str, dict[str, dict]]:
        """
        Indexa entidades antigas para preservar IDs, nomes, guidelines e enrichment.
        """

        result = {
            "genes": {},
            "star_alleles": {},
            "diplotypes": {},
            "rsids": {},
        }

        entidades = self._safe_dict(unique_data.get("entidades"))

        for category in result.keys():
            for item in self._safe_list(entidades.get(category)):
                if not isinstance(item, dict):
                    continue

                value = self._entity_value(item, category)

                if value:
                    result[category][value] = dict(item)

        return result

    def _aggregate_from_sections(self, doc_dir: Path) -> tuple[dict, dict]:
        """
        Agrega entidades a partir dos JSONs de secção.

        Retorna:
        - aggregate[category][entity] = {
            total_mentions,
            sections,
            section_displays
          }
        - section_totals para auditoria.
        """

        aggregate = {
            "genes": defaultdict(lambda: {
                "total_mentions": 0,
                "sections": set(),
                "section_displays": set(),
            }),
            "star_alleles": defaultdict(lambda: {
                "total_mentions": 0,
                "sections": set(),
                "section_displays": set(),
            }),
            "diplotypes": defaultdict(lambda: {
                "total_mentions": 0,
                "sections": set(),
                "section_displays": set(),
            }),
            "rsids": defaultdict(lambda: {
                "total_mentions": 0,
                "sections": set(),
                "section_displays": set(),
            }),
        }

        section_totals = {}

        for section_path in self._section_jsons(doc_dir):
            section_data = self._read_json(section_path)

            avaliacao = self._safe_dict(section_data.get("avaliacao_farmacogenomica"))
            entidades = self._safe_dict(avaliacao.get("pgx_entidades"))

            section_label = self._section_label(section_data, section_path.stem)
            section_display = self._section_display(section_data, section_path.stem)

            section_counter = Counter()

            for category in ["genes", "star_alleles", "diplotypes", "rsids"]:
                for item in self._safe_list(entidades.get(category)):
                    if not isinstance(item, dict):
                        continue

                    value = self._entity_value(item, category)
                    if not value:
                        continue

                    n = self._entity_mentions(item)

                    aggregate[category][value]["total_mentions"] += n
                    aggregate[category][value]["sections"].add(section_label)
                    aggregate[category][value]["section_displays"].add(section_display)

                    section_counter[category] += n

            section_totals[section_display] = {
                "genes": section_counter["genes"],
                "star_alleles": section_counter["star_alleles"],
                "diplotypes": section_counter["diplotypes"],
                "rsids": section_counter["rsids"],
                "total": sum(section_counter.values()),
            }

        return aggregate, section_totals

    def _has_guideline(self, item: dict) -> bool:
        ids = self._safe_dict(item.get("ids"))

        guideline_ids = ids.get("guideline_ids")
        if isinstance(guideline_ids, list) and len(guideline_ids) > 0:
            return True

        guideline_ids = item.get("guideline_ids")
        if isinstance(guideline_ids, list) and len(guideline_ids) > 0:
            return True

        guideline_matches = item.get("guideline_matches")
        if isinstance(guideline_matches, list) and len(guideline_matches) > 0:
            return True

        evidence_flags = self._safe_dict(item.get("evidence_flags"))
        if evidence_flags.get("has_guideline"):
            return True

        return False

    def _rebuild_entity(
        self,
        category: str,
        entity: str,
        agg_item: dict,
        old_entities: dict[str, dict[str, dict]],
    ) -> dict:
        """
        Preserva dados antigos da entidade e substitui apenas:
        - entity/symbol
        - total_mentions
        - sections
        """

        old_item = dict(old_entities.get(category, {}).get(entity, {}))

        old_item["entity"] = entity

        if category == "genes" and "symbol" in old_item:
            old_item["symbol"] = entity

        old_item["total_mentions"] = int(agg_item["total_mentions"])
        old_item["sections"] = sorted(agg_item["sections"])
        old_item["section_labels"] = sorted(agg_item["section_displays"])

        return old_item

    def _rebuild_entities(self, unique_data: dict, aggregate: dict) -> dict:
        old_entities = self._old_entities_by_key(unique_data)

        rebuilt = {
            "genes": [],
            "star_alleles": [],
            "diplotypes": [],
            "rsids": [],
        }

        for category in ["genes", "star_alleles", "diplotypes", "rsids"]:
            for entity in sorted(aggregate[category].keys()):
                rebuilt[category].append(
                    self._rebuild_entity(
                        category=category,
                        entity=entity,
                        agg_item=aggregate[category][entity],
                        old_entities=old_entities,
                    )
                )

        return rebuilt

    def _count_guideline_entities(self, entities: list[dict]) -> int:
        return sum(1 for item in entities if self._has_guideline(item))

    def _rebuild_counts(self, rebuilt_entities: dict, old_counts: dict) -> dict:
        genes = rebuilt_entities["genes"]
        star_alleles = rebuilt_entities["star_alleles"]
        diplotypes = rebuilt_entities["diplotypes"]
        rsids = rebuilt_entities["rsids"]

        genes_mentions = sum(self._to_int(x.get("total_mentions")) for x in genes)
        star_mentions = sum(self._to_int(x.get("total_mentions")) for x in star_alleles)
        diplotype_mentions = sum(self._to_int(x.get("total_mentions")) for x in diplotypes)
        rsid_mentions = sum(self._to_int(x.get("total_mentions")) for x in rsids)

        counts = dict(old_counts)

        counts["genes_unicos_total"] = len(genes)
        counts["genes_mencoes_total"] = genes_mentions

        counts["star_alleles_unicos_total"] = len(star_alleles)
        counts["star_alleles_mencoes_total"] = star_mentions

        counts["diplotipos_unicos_total"] = len(diplotypes)
        counts["diplotipos_mencoes_total"] = diplotype_mentions

        counts["rsids_unicos_total"] = len(rsids)
        counts["rsids_mencoes_total"] = rsid_mentions

        counts["entidades_unicas_total"] = (
            len(genes) + len(star_alleles) + len(diplotypes) + len(rsids)
        )

        counts["entidades_mencoes_total"] = (
            genes_mentions + star_mentions + diplotype_mentions + rsid_mentions
        )

        counts["genes_com_guideline_total"] = self._count_guideline_entities(genes)
        counts["star_alleles_com_guideline_total"] = self._count_guideline_entities(star_alleles)
        counts["diplotipos_com_guideline_total"] = self._count_guideline_entities(diplotypes)
        counts["rsids_com_guideline_total"] = self._count_guideline_entities(rsids)

        counts.setdefault("genes_normalizados_nome_extenso_para_simbolo_total", 0)
        counts.setdefault("normalizacoes_tecnicas_total", 0)
        counts.setdefault("star_alleles_incompletos_total", 0)

        return counts

    # =====================================================
    # REPAIR
    # =====================================================
    def repair_one(self, doc_dir: Path) -> dict:
        unique_path = self._unique_path(doc_dir)

        if unique_path is None:
            return {
                "document": doc_dir.name,
                "status": "missing_document_unique",
            }

        unique_data_original = self._read_json(unique_path)
        unique_data, identifiers_changed = self._repair_identifiers(unique_data_original)

        old_counts = self._safe_dict(unique_data.get("contagens"))

        aggregate, section_totals = self._aggregate_from_sections(doc_dir)

        rebuilt_entities = self._rebuild_entities(unique_data, aggregate)
        rebuilt_counts = self._rebuild_counts(rebuilt_entities, old_counts)

        old_total = self._to_int(old_counts.get("entidades_mencoes_total"))
        new_total = self._to_int(rebuilt_counts.get("entidades_mencoes_total"))

        repaired = dict(unique_data)
        repaired["entidades"] = rebuilt_entities
        repaired["contagens"] = rebuilt_counts

        repaired["reparacao_document_unique"] = {
            "aplicada": True,
            "fonte_mencoes": "jsons_individuais_das_seccoes",
            "mencoes_entidades_total_antes": old_total,
            "mencoes_entidades_total_depois": new_total,
            "identificador_mrconso_cui_renomeado_para_umls_cui": identifiers_changed,
            "section_totals": section_totals,
        }

        changed = (
            identifiers_changed
            or old_total != new_total
            or repaired.get("entidades") != unique_data_original.get("entidades")
            or repaired.get("contagens") != unique_data_original.get("contagens")
        )

        if not self.dry_run:
            backup_path = unique_path.with_name(unique_path.name + self.BACKUP_SUFFIX)

            if not backup_path.exists():
                shutil.copy2(unique_path, backup_path)

            self._write_json(unique_path, repaired)

        return {
            "document": doc_dir.name,
            "status": "repaired",
            "unique_path": str(unique_path),
            "changed": changed,
            "identifiers_changed": identifiers_changed,
            "old_entity_mentions_total": old_total,
            "new_entity_mentions_total": new_total,
            "delta": new_total - old_total,
            "genes_mentions_before": self._to_int(old_counts.get("genes_mencoes_total")),
            "genes_mentions_after": self._to_int(rebuilt_counts.get("genes_mencoes_total")),
            "star_alleles_mentions_before": self._to_int(old_counts.get("star_alleles_mencoes_total")),
            "star_alleles_mentions_after": self._to_int(rebuilt_counts.get("star_alleles_mencoes_total")),
            "diplotypes_mentions_before": self._to_int(old_counts.get("diplotipos_mencoes_total")),
            "diplotypes_mentions_after": self._to_int(rebuilt_counts.get("diplotipos_mencoes_total")),
            "rsids_mentions_before": self._to_int(old_counts.get("rsids_mencoes_total")),
            "rsids_mentions_after": self._to_int(rebuilt_counts.get("rsids_mencoes_total")),
        }

    def repair_all(self) -> dict:
        rows = []

        for doc_dir in self._doc_dirs():
            rows.append(self.repair_one(doc_dir))

        summary = {
            "dry_run": self.dry_run,
            "total_document_dirs": len(self._doc_dirs()),
            "documents_repaired": sum(1 for r in rows if r.get("status") == "repaired"),
            "documents_missing_document_unique": sum(
                1 for r in rows if r.get("status") == "missing_document_unique"
            ),
            "documents_changed": sum(
                1
                for r in rows
                if r.get("status") == "repaired" and r.get("changed") is True
            ),
            "documents_with_mentions_changed": sum(
                1
                for r in rows
                if r.get("status") == "repaired"
                and r.get("old_entity_mentions_total") != r.get("new_entity_mentions_total")
            ),
            "documents_with_identifiers_changed": sum(
                1
                for r in rows
                if r.get("status") == "repaired" and r.get("identifiers_changed") is True
            ),
            "rows": rows,
        }

        report_path = self.outputs_root / "Repair_Document_Unique_PGx_Report.json"

        if not self.dry_run:
            self._write_json(report_path, summary)

        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Repara Document_Unique_PGx.json usando os JSONs individuais das secções e renomeia mrconso_cui para umls_cui."
    )

    parser.add_argument(
        "outputs_root",
        help="Pasta raiz do batch. Exemplo: $HOME/Desktop/outputs_batch",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a reparação sem escrever ficheiros.",
    )

    args = parser.parse_args()

    repairer = DocumentUniquePGxRepair(
        outputs_root=args.outputs_root,
        dry_run=args.dry_run,
    )

    summary = repairer.repair_all()

    print("✅ Reparação Document_Unique concluída." if not args.dry_run else "✅ Dry-run concluído.")
    print(f"Total de pastas: {summary['total_document_dirs']}")
    print(f"Documentos reparados: {summary['documents_repaired']}")
    print(f"Documentos sem Document_Unique: {summary['documents_missing_document_unique']}")
    print(f"Documentos alterados: {summary['documents_changed']}")
    print(f"Documentos com alteração nas menções: {summary['documents_with_mentions_changed']}")
    print(f"Documentos com mrconso_cui renomeado para umls_cui: {summary['documents_with_identifiers_changed']}")