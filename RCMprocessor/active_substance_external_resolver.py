from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

import requests

from .substance_utils import build_queries as _shared_build_queries
from .substance_utils import matches_any as _shared_matches_any
from .substance_utils import normalize as _shared_normalize
from .substance_utils import split_substances as _shared_split_substances


class ActiveSubstanceExternalResolver:
    """Resolve external references for an active substance.

    Strategy:
    - try the English aliases first;
    - split combination products into individual substances;
    - fall back to the original substance name;
    - cache results locally.

    Sources:
    - ClinPGx: local folder data/clinpgx/guidelineAnnotations/*.json
    - MeSH: NCBI E-utilities, keeping only the MeSH Unique ID
    - MRCONSO.RRF: data/umls/MRCONSO.RRF, for the UMLS CUI and DrugBank ID

    Note: the DrugBank ID is read locally from MRCONSO; DrugBank itself is
    never queried.
    """

    NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    NCBI_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    # Minimum length for an MRCONSO string to qualify as a partial match.
    # See _resolve_mrconso_one: without this floor, single letters ("L", "M",
    # "Or") matched substance names.
    MIN_PARTIAL_LENGTH = 5

    def __init__(
        self,
        data_dir: Path,
        cache_path: Optional[Path] = None,
        clinpgx_guideline_annotations_dir: Optional[Path] = None,
        timeout: int = 20,
        sleep_seconds: float = 0.4,
    ):
        self.data_dir = Path(data_dir)

        self.cache_path = (
            Path(cache_path)
            if cache_path
            else self.data_dir / "cache" / "active_substance_external_cache.json"
        )

        self.clinpgx_guideline_annotations_dir = (
            Path(clinpgx_guideline_annotations_dir)
            if clinpgx_guideline_annotations_dir
            else self.data_dir / "clinpgx" / "guidelineAnnotations"
        )

        self.mrconso_path = self.data_dir / "umls" / "MRCONSO.RRF"
        if not self.mrconso_path.exists():
            # fallback for layouts used by earlier versions of the project
            self.mrconso_path = self.data_dir / "MRCONSO.RRF"

        self.timeout = timeout
        self.sleep_seconds = sleep_seconds

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()

        # Chaves que ESTE processo escreveu. Só estas são aplicadas sobre o
        # disco no _save_cache. Sem isto, um processo grava a sua cópia
        # completa e reverte, nas chaves que não são suas, o trabalho que os
        # outros já tinham gravado — a cópia dele é a do arranque.
        self._sujas: set[str] = set()

    # =====================================================
    # CACHE
    # =====================================================
    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}

        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self) -> None:
        """Grava a cache de forma atómica e sem apagar o trabalho dos outros.

        A fase 2 corre em vários processos em paralelo — um por lote — e todos
        partilham este ficheiro. Com um write_text directo acontecia o
        seguinte: cada processo lê a cache no arranque, guarda-a em memória, e
        ao gravar escreve a SUA versão por cima. O último a gravar apagava as
        entradas que os outros tinham resolvido. Pior: uma escrita interrompida
        a meio deixa JSON truncado, e o _load_cache engole a excepção e devolve
        {} — a cache fica vazia sem um único aviso.

        O custo não é teórico. Cada substância por resolver são dois
        varrimentos completos do MRCONSO, 2,3 GB cada, cerca de um minuto. Com
        949 substâncias por resolver no corpus nacional, perder a cache
        significa repetir 16 horas de varrimento.

        A correcção tem três partes, e as três são precisas:

        1. um lock de ficheiro, para que ler-fundir-gravar seja indivisível.
           Sem ele, dois processos lêem o mesmo estado e o segundo grava por
           cima do que o primeiro acabou de acrescentar. Medido: 8 processos
           com 30 escritas cada deixavam 93 das 240 entradas;
        2. reler o disco dentro do lock, para não perder o que os outros
           gravaram desde o arranque deste processo;
        3. gravar num temporário e fazer rename, porque o os.replace é
           atómico e nunca deixa JSON truncado.

        O flock existe no macOS e no Linux. Se faltar (Windows), degrada para
        o comportamento sem lock, que continua a ser melhor do que o original.
        """
        bloqueio = self.cache_path.with_name(f"{self.cache_path.name}.lock")

        # O flock é do Unix; no Windows o equivalente é o msvcrt.locking. Sem
        # um dos dois, vários processos podem ler o mesmo estado e o segundo
        # gravar por cima do primeiro. A corrida nacional corre em 3 ou mais
        # processos, portanto isto não é hipotético.
        try:
            import fcntl
        except ImportError:
            fcntl = None
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

        handle = None
        try:
            if fcntl is not None:
                handle = open(bloqueio, "a+")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                handle = open(bloqueio, "a+")
                handle.seek(0)
                # O msvcrt.locking falha em vez de esperar; repete-se até obter.
                for _ in range(600):
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        time.sleep(0.1)

            try:
                em_disco = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(em_disco, dict):
                    # Aplicam-se APENAS as chaves que este processo escreveu.
                    # As outras ficam como estão no disco, que é onde está a
                    # versão mais recente de quem as mexeu.
                    em_disco.update({k: self.cache[k]
                                     for k in self._sujas if k in self.cache})
                    self.cache = em_disco
            except Exception:
                # Ficheiro ausente, vazio ou corrompido: grava-se o que se tem.
                pass

            temporario = self.cache_path.with_name(
                f"{self.cache_path.name}.{os.getpid()}.tmp"
            )
            temporario.write_text(
                json.dumps(self.cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporario, self.cache_path)
        finally:
            if handle is not None:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    elif msvcrt is not None:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    handle.close()

    # =====================================================
    # NORMALISATION / QUERIES
    # =====================================================
    # The implementation now lives in substance_utils, shared with
    # ClinicalVariantsLookup, which previously never split combinations.
    def _normalize(self, text: str) -> str:
        return _shared_normalize(text)

    def _split_substances(self, text: str) -> list[str]:
        return _shared_split_substances(text)

    def _build_queries(
        self,
        active_substance: Optional[str],
        aliases: Optional[list[str]],
    ) -> list[str]:
        return _shared_build_queries(active_substance, aliases)

    def _cache_key(
        self,
        active_substance: Optional[str],
        aliases: Optional[list[str]],
    ) -> str:
        queries = self._build_queries(active_substance, aliases)
        return self._normalize(" | ".join(queries))

    def _matches_query(self, value: str, queries: list[str]) -> bool:
        # Was: a plain bidirectional substring test, which made "iron" match
        # "spironolactone". Now it requires word boundaries.
        return _shared_matches_any(value, queries)

    # =====================================================
    # HELPERS
    # =====================================================
    def _read_json_file(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _strip_html(self, value: str) -> str:
        if not value:
            return ""

        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"&nbsp;|&amp;|&quot;|&#39;", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def _extract_strings_recursive(self, obj: Any) -> list[str]:
        values = []

        if isinstance(obj, dict):
            for value in obj.values():
                values.extend(self._extract_strings_recursive(value))
        elif isinstance(obj, list):
            for item in obj:
                values.extend(self._extract_strings_recursive(item))
        elif isinstance(obj, str):
            values.append(obj)

        return values

    # =====================================================
    # ClinPGx LOCAL
    # =====================================================
    def _load_clinpgx_annotation_files(self) -> list[dict]:
        if not self.clinpgx_guideline_annotations_dir.exists():
            return []

        records = []

        for path in sorted(self.clinpgx_guideline_annotations_dir.glob("*.json")):
            try:
                data = self._read_json_file(path)
            except Exception:
                continue

            if isinstance(data, dict):
                data["_source_file"] = path.name
                records.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        item["_source_file"] = path.name
                        records.append(item)

        return records

    def _get_guideline_block(self, record: dict) -> dict:
        guideline = record.get("guideline")
        return guideline if isinstance(guideline, dict) else record

    def _get_related_chemicals(self, guideline: dict) -> list[dict]:
        chemicals = guideline.get("relatedChemicals")
        return [c for c in chemicals if isinstance(c, dict)] if isinstance(chemicals, list) else []

    def _get_related_genes(self, guideline: dict) -> list[dict]:
        genes = guideline.get("relatedGenes")
        return [g for g in genes if isinstance(g, dict)] if isinstance(genes, list) else []

    def _clinpgx_matches_related_chemicals(
        self,
        guideline: dict,
        queries: list[str],
    ) -> bool:
        for chem in self._get_related_chemicals(guideline):
            name = str(chem.get("name") or "").strip()
            if name and self._matches_query(name, queries):
                return True
        return False

    def _clinpgx_fallback_text_match(
        self,
        guideline: dict,
        queries: list[str],
    ) -> bool:
        for s in self._extract_strings_recursive(guideline):
            if self._matches_query(s, queries):
                return True
        return False

    def _compact_clinpgx_match(self, record: dict) -> dict:
        source_file = record.get("_source_file")
        guideline = self._get_guideline_block(record)

        related_chemicals = [
            {"id": chem.get("id"), "name": chem.get("name")}
            for chem in self._get_related_chemicals(guideline)
        ]

        related_genes = [
            {
                "id": gene.get("id"),
                "symbol": gene.get("symbol"),
                "name": gene.get("name"),
            }
            for gene in self._get_related_genes(guideline)
        ]

        summary_html = ""
        summary_markdown = guideline.get("summaryMarkdown")
        if isinstance(summary_markdown, dict):
            summary_html = summary_markdown.get("html") or ""

        return {
            "source_file": source_file,
            "guideline_id": guideline.get("id"),
            "guideline_name": guideline.get("name"),
            "source": guideline.get("source"),
            "has_testing_info": guideline.get("hasTestingInfo"),
            "dosing_information": guideline.get("dosingInformation"),
            "recommendation": guideline.get("recommendation"),
            "alternate_drug_available": guideline.get("alternateDrugAvailable"),
            "pediatric": guideline.get("pediatric"),
            "related_chemicals": related_chemicals,
            "related_genes": related_genes,
            "summary": self._strip_html(summary_html),
        }

    def _resolve_clinpgx(self, queries: list[str]) -> dict:
        records = self._load_clinpgx_annotation_files()

        if not records:
            return {
                "found": False,
                "status": "not_available",
                "matches_count": 0,
                "matches": [],
            }

        matches = []

        for record in records:
            guideline = self._get_guideline_block(record)
            related_chemicals = self._get_related_chemicals(guideline)

            if related_chemicals:
                matched = self._clinpgx_matches_related_chemicals(guideline, queries)
            else:
                matched = self._clinpgx_fallback_text_match(guideline, queries)

            if matched:
                matches.append(self._compact_clinpgx_match(record))

        return {
            "found": bool(matches),
            "status": "ok",
            "matches_count": len(matches),
            "matches": matches,
        }

    # =====================================================
    # MeSH / NCBI
    # =====================================================
    def _extract_mesh_unique_id_from_summary_item(self, item: dict) -> str:
        if not isinstance(item, dict):
            return ""

        value = item.get("ds_meshui")
        if isinstance(value, str) and re.match(r"^D\d{6}$", value.strip()):
            return value.strip()

        possible_keys = [
            "mesh_ui",
            "meshui",
            "mesh_unique_id",
            "unique_id",
            "uniqueid",
            "uid",
        ]

        for key in possible_keys:
            value = item.get(key)

            if isinstance(value, str):
                match = re.search(r"\bD\d{6}\b", value)
                if match:
                    return match.group(0)

            if isinstance(value, list):
                for sub_value in value:
                    if isinstance(sub_value, str):
                        match = re.search(r"\bD\d{6}\b", sub_value)
                        if match:
                            return match.group(0)

        text = json.dumps(item, ensure_ascii=False)
        match = re.search(r"\bD\d{6}\b", text)
        return match.group(0) if match else ""

    def _extract_mesh_preferred_term(self, item: dict) -> str:
        if not isinstance(item, dict):
            return ""

        terms = item.get("ds_meshterms")
        if isinstance(terms, list) and terms:
            return str(terms[0]).strip()
        if isinstance(terms, str) and terms.strip():
            return terms.strip()

        title = item.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()

        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

        return ""

    def _resolve_mesh_one(self, query: str) -> dict:
        try:
            search_response = requests.get(
                self.NCBI_ESEARCH_URL,
                params={"db": "mesh", "term": query, "retmode": "json"},
                timeout=self.timeout,
            )
            time.sleep(self.sleep_seconds)

            if search_response.status_code != 200:
                return {
                    "found": False,
                    "query": query,
                    "status": "http_error",
                    "http_status": search_response.status_code,
                    "mesh_unique_id": "",
                    "preferred_term": "",
                }

            search_payload = search_response.json()
            ids = search_payload.get("esearchresult", {}).get("idlist", [])

            if not ids:
                return {
                    "found": False,
                    "query": query,
                    "status": "not_found",
                    "mesh_unique_id": "",
                    "preferred_term": "",
                }

            entrez_uid = ids[0]

            summary_response = requests.get(
                self.NCBI_ESUMMARY_URL,
                params={"db": "mesh", "id": entrez_uid, "retmode": "json"},
                timeout=self.timeout,
            )
            time.sleep(self.sleep_seconds)

            if summary_response.status_code != 200:
                return {
                    "found": False,
                    "query": query,
                    "status": "summary_http_error",
                    "http_status": summary_response.status_code,
                    "mesh_unique_id": "",
                    "preferred_term": "",
                }

            summary_payload = summary_response.json()
            result = summary_payload.get("result", {})
            item = result.get(entrez_uid, {})

            mesh_unique_id = self._extract_mesh_unique_id_from_summary_item(item)
            preferred_term = self._extract_mesh_preferred_term(item)

            return {
                "found": bool(mesh_unique_id),
                "query": query,
                "status": "ok" if mesh_unique_id else "mesh_unique_id_not_found",
                "mesh_unique_id": mesh_unique_id,
                "preferred_term": preferred_term,
            }

        except Exception as e:
            return {
                "found": False,
                "query": query,
                "status": "error",
                "error": str(e),
                "mesh_unique_id": "",
                "preferred_term": "",
            }

    def _resolve_mesh(self, queries: list[str]) -> dict:
        results_by_substance = {query: self._resolve_mesh_one(query) for query in queries}
        return {
            "found": any(r.get("found") for r in results_by_substance.values()),
            "results_by_substance": results_by_substance,
        }

    # =====================================================
    # MRCONSO / UMLS LOCAL
    # =====================================================
    def _is_drugbank_sab(self, sab: str) -> bool:
        return (sab or "").strip().upper() == "DRUGBANK"

    def _format_drugbank_code(self, code: str) -> str:
        """Normalise DrugBank identifiers read from MRCONSO.

        In MRCONSO the DrugBank ID usually sits in CODE and/or SCUI, e.g.
        DB00682. The DrugBank API and website are never queried.
        """
        code = (code or "").strip()
        if not code:
            return ""
        return code.upper() if code.upper().startswith("DB") else code

    def _resolve_mrconso_one(self, query: str) -> dict:
        """Resolve the active substance against MRCONSO.

        Strategy:
        1) find the CUI by text match in any source vocabulary;
        2) for those CUIs, collect DrugBank IDs from SAB=DRUGBANK rows and
           the English synonyms from LAT=ENG rows.

        The local MRCONSO path is deliberately kept out of the output.
        """
        if not self.mrconso_path.exists():
            return {
                "found": False,
                "query": query,
                "status": "mrconso_not_available",
                "matches": [],
                "best_match": {},
            }

        query_norm = self._normalize(query)
        if not query_norm:
            return {
                "found": False,
                "query": query,
                "status": "empty_query",
                "matches": [],
                "best_match": {},
            }

        exact_candidates: dict[str, dict] = {}
        partial_candidates: dict[str, dict] = {}
        max_candidates = 25

        try:
            # 1) Primeiro obtém CUI(s) por match textual em qualquer fonte do MRCONSO.
            with self.mrconso_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    fields = line.rstrip("\n").split("|")
                    if len(fields) < 15:
                        continue
                    cui = fields[0]
                    string_value = fields[14]
                    string_norm = self._normalize(string_value)
                    if not cui or not string_norm:
                        continue

                    if string_norm == query_norm:
                        exact_candidates.setdefault(cui, {
                            "cui": cui,
                            "matched_term": string_value,
                            "match_type": "exact",
                        })
                        if len(exact_candidates) >= max_candidates:
                            break
                    # Partial match with a minimum length.
                    #
                    # Sem o limite, `string_norm in query_norm` aceitava
                    # QUALQUER string do MRCONSO contida na consulta —
                    # incluindo letras isoladas. O "metoxifluorane" casou com
                    # "L" (leucina), "Or" e "M", e como a leucina tem DrugBank
                    # ID, won the ordering and was recorded as the
                    # substance's CUI. A wrong CUI is worse than none: it
                    # drags in another drug's synonyms and identifiers.
                    #
                    # 5 characters is the least a substance name needs to be
                    # distinctive; below that come acronyms and code letters.
                    elif (
                        len(string_norm) >= self.MIN_PARTIAL_LENGTH
                        and (query_norm in string_norm or string_norm in query_norm)
                    ):
                        partial_candidates.setdefault(cui, {
                            "cui": cui,
                            "matched_term": string_value,
                            "match_type": "partial",
                        })

            candidates = exact_candidates or dict(list(partial_candidates.items())[:max_candidates])
            if not candidates:
                return {
                    "found": False,
                    "query": query,
                    "status": "not_found",
                    "matches": [],
                    "best_match": {},
                }

            # 2) For the CUI(s) found, recover the DrugBank ID and the
            #    English synonyms.
            #
            # The CUI is the bridge between the Portuguese name and the name
            # international databases use: "alopurinol" and "allopurinol" are
            # the same C0002144, "voriconazol" and "voriconazole" the same
            # C0393080.
            #
            # Without this step the resolver reached the CUI and stopped, and
            # the ClinPGx query went out with the Portuguese name — which
            # ClinPGx does not know. It cost 5 guidelines in 64 documents
            # (alopurinol/HLA-B,
            # voriconazol/CYP2C19, brexpiprazol/CYP2D6, metoxiflurano/RYR1,
            # abacavir/HLA-B), 8% do corpus.
            #
            # Collected in the pass that already existed, so it is free.
            cui_set = set(candidates)
            with self.mrconso_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    fields = line.rstrip("\n").split("|")
                    if len(fields) < 15:
                        continue
                    cui = fields[0]
                    if cui not in cui_set:
                        continue

                    # LAT = field 1. Only English terms matter: they are the
                    # ones ClinPGx, PharmGKB and CPIC use.
                    if fields[1] == "ENG":
                        termo = fields[14].strip()
                        if termo:
                            candidates[cui].setdefault("english_terms", set()).add(termo)

                    sab = fields[11]
                    if not self._is_drugbank_sab(sab):
                        continue

                    # MRCONSO: SCUI=campo 9, SDUI=campo 10, CODE=campo 13, STR=campo 14.
                    # For DRUGBANK the identifier is usually in CODE and/or SCUI.
                    drugbank_id = (
                        self._format_drugbank_code(fields[13])
                        or self._format_drugbank_code(fields[9])
                        or self._format_drugbank_code(fields[10])
                    )
                    if not drugbank_id:
                        continue
                    candidates[cui]["drugbank_id"] = drugbank_id
                    candidates[cui]["drugbank_term"] = fields[14]

            matches = []
            for item in candidates.values():
                # Sorted by length: short names are the INNs
                # ("allopurinol"); long ones are formulations and salts
                # ("allopurinol 100 MG Oral Tablet"), useless for querying
                # ClinPGx and nothing but noise.
                ingleses = sorted(item.get("english_terms", set()), key=len)
                matches.append({
                    "query": query,
                    "match_type": item.get("match_type", ""),
                    "cui": item.get("cui", ""),
                    "drugbank_id": item.get("drugbank_id", ""),
                    "preferred_term": item.get("drugbank_term") or item.get("matched_term", ""),
                    "matched_term": item.get("matched_term", ""),
                    "english_terms": ingleses[:12],
                })

            # Prefer candidates with a DrugBank ID, then exact matches.
            matches.sort(key=lambda x: (not bool(x.get("drugbank_id")), x.get("match_type") != "exact", x.get("preferred_term", "")))

            return {
                "found": bool(matches),
                "query": query,
                "status": "ok" if matches else "not_found",
                "matches": matches,
                "best_match": matches[0] if matches else {},
            }

        except Exception as e:
            return {
                "found": False,
                "query": query,
                "status": "error",
                "error": str(e),
                "matches": [],
                "best_match": {},
            }

    def _resolve_mrconso(self, queries: list[str]) -> dict:
        """Resolve every query and arbitrate the best CUI among them.

        Queries run aliases first, original name second. Without arbitration
        between them, an alias producing only partial matches beat an original
        name with an exact match: the alias "metoxifluorane" returned leucine
        by partial match, while "metoxiflurano" had the correct CUI by exact
        match.

        An exact match from any query always outranks a partial one from any
        other.
        """
        results_by_substance = {query: self._resolve_mrconso_one(query) for query in queries}

        melhor_exato = None
        for resultado in results_by_substance.values():
            for match in resultado.get("matches") or []:
                if match.get("match_type") == "exact":
                    melhor_exato = match
                    break
            if melhor_exato:
                break

        return {
            "found": any(r.get("found") for r in results_by_substance.values()),
            "available": self.mrconso_path.exists(),
            # Explicit, so a reader of the output knows arbitration happened.
            "best_match_global": melhor_exato or {},
            "best_match_type": "exact" if melhor_exato else "partial",
            "results_by_substance": results_by_substance,
        }

    # =====================================================
    # MÉTODO PÚBLICO
    # =====================================================
    @staticmethod
    def _expandir_com_sinonimos(queries: list[str], mrconso: dict) -> list[str]:
        """Add the English names of the resolved CUI to the query list.

        Only one- or two-token terms are added: for the same CUI, MRCONSO
        holds both "allopurinol" and "allopurinol 100 MG Oral Tablet". The
        second never matches ClinPGx and, worse, could match something else
        by accident in a partial search.
        """
        extra: list[str] = []
        vistos = {q.strip().lower() for q in queries}

        for bloco in (mrconso or {}).get("results_by_substance", {}).values():
            for match in (bloco or {}).get("matches", []):
                for termo in match.get("english_terms", []):
                    t = str(termo).strip()
                    # A substance name, not a formulation: at most two tokens
                    # and no digits (doses always carry a number).
                    if not t or len(t.split()) > 2 or any(c.isdigit() for c in t):
                        continue
                    if t.lower() in vistos:
                        continue
                    vistos.add(t.lower())
                    extra.append(t)

        return queries + extra

    def resolve(
        self,
        active_substance: Optional[str],
        aliases: Optional[list[str]] = None,
    ) -> dict:
        queries = self._build_queries(active_substance, aliases)
        key = self._cache_key(active_substance, aliases)

        if key and key in self.cache:
            cached = self.cache[key]
            refs = cached.get("references") or {}
            # Recalcula caches antigas que ainda tinham ChEBI, não tinham DrugBank ID via MRCONSO,
            # não tinham MRCONSO, ou continham detalhes técnicos como mrconso_path.
            mrconso_cache_text = json.dumps(refs.get("mrconso", {}), ensure_ascii=False).lower()
            if (
                "mrconso" in refs
                and "mrconso_path" not in mrconso_cache_text
                and "chebi_id" not in mrconso_cache_text
                and "drugbank_id" in mrconso_cache_text
                # Caches anteriores à expansão de sinónimos não têm o campo e
                # foram construídas a consultar o ClinPGx só com o nome
                # português. Recalculam-se, senão o bug fica preso na cache.
                and "english_terms" in mrconso_cache_text
            ):
                return cached

        # O MRCONSO corre PRIMEIRO, ao contrário do que era.
        #
        # É ele que dá o CUI e, a partir do CUI, os nomes ingleses. O ClinPGx
        # só conhece nomes ingleses. Com a ordem anterior — ClinPGx, MeSH,
        # MRCONSO — a consulta ao ClinPGx era feita antes de existir tradução,
        # e ia com "voriconazol" a uma base que só tem "voriconazole".
        mrconso = self._resolve_mrconso(queries)
        queries_expandidas = self._expandir_com_sinonimos(queries, mrconso)

        result = {
            "queries": queries,
            "queries_expandidas": queries_expandidas,
            "references": {
                "clinpgx": self._resolve_clinpgx(queries_expandidas),
                "mesh": self._resolve_mesh(queries),
                "mrconso": mrconso,
            },
        }

        if key:
            self.cache[key] = result
            self._sujas.add(key)
            self._save_cache()

        return result
