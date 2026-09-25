import json
from pathlib import Path

from .scanned_pdf_detector import inspect as inspect_pdf
from .pdf_converter import PDFConverter
from .markdown_processor import MarkdownProcessor
from .pharmacogenomics_evaluator import PharmacogenomicsEvaluator
from .json_exporter import JSONExporter
from .active_substance_external_resolver import ActiveSubstanceExternalResolver


class RCMProcessor:
    """
    Orquestra o processamento de um RCM.
    """

    def __init__(
        self,
        pdf_path: str,
        model: str = "gpt-oss:120b",
        output_root: str | None = None,
        markdown_dir: str | None = None,
    ):
        self.pdf_path = Path(pdf_path).resolve()

        if not self.pdf_path.exists():
            raise FileNotFoundError(f"Ficheiro PDF não encontrado: {pdf_path}")

        self.model = model
        self.output_root = Path(output_root).resolve() if output_root else None
        self.markdown_dir = Path(markdown_dir).resolve() if markdown_dir else None

    def _obter_markdown(self) -> str:
        """Markdown do documento, convertido agora ou lido de uma conversão anterior.

        A conversão pelo docling e a extração pelo modelo têm naturezas
        opostas: a primeira é CPU e não escala com processos (o docling já
        satura os núcleos sozinho, e cada processo carrega ~1,5 GB de modelos);
        a segunda é espera de rede e escala bem, desde que não tenha o docling
        em memória a limitar quantos processos cabem.

        Separá-las em duas fases — converter tudo primeiro, extrair depois —
        permite correr a segunda com muito mais paralelismo, distribuir a
        primeira por várias máquinas sem coordenação nenhuma (não precisa de
        rede nem de chave), e não perder a conversão quando a extração falha
        num documento.

        Sem ``markdown_dir``, o comportamento é exactamente o de sempre.
        """
        if self.markdown_dir:
            convertido = self.markdown_dir / f"{self.pdf_path.stem}.md"
            if convertido.exists():
                # newline="" desliga a tradução de fins de linha.
                #
                # Sem isto, `read_text` abre em modo universal newlines e
                # converte todo o \r do ficheiro em \n. O docling emite \r
                # dentro das células de tabelas multi-linha — 521 num único
                # RCM da rifampicina — e o texto lido de volta deixava de ser
                # o texto que o docling produziu. A execução em duas fases
                # passaria ao modelo um input diferente do da execução numa
                # fase, que é precisamente a garantia que ela tem de dar.
                with convertido.open(encoding="utf-8", newline="") as fh:
                    return fh.read()

        return PDFConverter(self.pdf_path).convert()

    def _build_output_dir(self) -> Path:
        pdf_name = self.pdf_path.stem

        if self.output_root:
            output_dir = (self.output_root / pdf_name).resolve()
        else:
            output_dir = (self.pdf_path.parent / f"chunks_json_{pdf_name}").resolve()

        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def run(self) -> dict:
        md_text = self._obter_markdown()

        output_dir = self._build_output_dir()

        # Unusable PDFs are flagged rather than OCR'd. OCR was evaluated and
        # discarded: unreliable text produces entities that do not exist, which
        # is worse than no text. Without this flag an unusable RCM is
        # indistinguishable from one that genuinely has no PGx content, and
        # every percentage in the analysis gets a quietly wrong denominator.
        #
        # Two distinct failures are caught here. A scan has no text layer at
        # all. A corrupt document has one, but the font lacks a usable
        # character map, so extraction returns glyph codes: tramadol_oral gave
        # 41 705 characters of which none were readable Portuguese, produced
        # zero sections, and was still reported as processed.
        scan_info = inspect_pdf(self.pdf_path, markdown=md_text)
        if not scan_info["is_usable"]:
            rotulo = ("digitalização" if scan_info["status"] == "scanned"
                      else "texto corrompido")
            print(f"⚠️ PDF não utilizável ({scan_info['reason']}) — "
                  f"marcado como {rotulo}, não analisado.")

            # Both write the same marker file: downstream, the only question
            # is whether the document can enter the denominators.
            (output_dir / "NAO_UTILIZAVEL.json").write_text(
                json.dumps({"pdf": str(self.pdf_path), **scan_info},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "pdf": str(self.pdf_path),
                "output_dir": str(output_dir),
                "status": "nao_utilizavel",
                "scan_info": scan_info,
                "has_pgx": False,
                "has_entities": False,
            }

        md_output_dir = output_dir / "md"
        md_output_dir.mkdir(exist_ok=True)

        (md_output_dir / "raw.md").write_text(md_text, encoding="utf-8")

        mp = MarkdownProcessor(md_text)
        normalized_md = mp.get_markdown_normalizado()

        (md_output_dir / "normalizado.md").write_text(
            normalized_md,
            encoding="utf-8",
        )

        seccoes_numericas = mp.extrair_seccoes_numericas()
        campos_especiais = mp.extrair_campos_especiais()

        # RCM sem estrutura de secções reconhecível.
        #
        # É um terceiro modo de falha, ao lado da digitalização e do texto
        # corrompido, e tem de ser tratado da mesma maneira: excluído dos
        # denominadores em vez de contado como "sem farmacogenómica".
        #
        # O caso que o revelou foi o abacavir. O RCM está lá e é legível — o
        # HLA-B*5701 aparece sete vezes, com indicação de teste antes de
        # iniciar a terapêutica. Mas os títulos não têm numeração e estão na
        # mesma fonte do corpo, pelo que o docling não os marca como
        # cabeçalhos e não há por onde segmentar. Zero secções, zero entidades,
        # e o documento entrava nas contagens como se o rótulo nada dissesse.
        #
        # Não se tenta adivinhar: um título inferido por heurística num RCM mal
        # formado produziria secções erradas, que é pior do que nenhuma. O
        # documento é sinalizado para revisão manual e a lista destes casos é,
        # em si, um resultado sobre a qualidade editorial dos RCMs.
        if not seccoes_numericas:
            print("⚠️ Nenhuma secção normativa detetada — RCM sem estrutura "
                  "reconhecível, marcado para revisão.")
            (output_dir / "NAO_UTILIZAVEL.json").write_text(
                json.dumps({
                    "pdf": str(self.pdf_path),
                    "status": "sem_estrutura",
                    "is_usable": False,
                    "reason": "nenhuma secção normativa detetada; títulos sem "
                              "numeração e sem distinção tipográfica",
                    "chars": len(md_text),
                    "campos_especiais_encontrados": len(campos_especiais),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "pdf": str(self.pdf_path),
                "output_dir": str(output_dir),
                "status": "nao_utilizavel",
                "scan_info": {"status": "sem_estrutura", "is_usable": False},
                "has_pgx": False,
                "has_entities": False,
            }

        avaliador = PharmacogenomicsEvaluator(model=self.model)

        active_substance = None
        active_substance_aliases = []
        active_substance_queries = []
        active_substance_external_references = {}

        secao_2 = mp.extrair_secao_2()

        if secao_2:
            resultado_substancia = avaliador.extrair_substancia_ativa(secao_2)
            substancia = (resultado_substancia.get("substancia_ativa") or "").strip()

            if resultado_substancia.get("encontrada") == "Sim" and substancia:
                active_substance = substancia

                active_substance_aliases = avaliador.gerar_aliases_substancia_ativa(
                    substancia
                )

                campos_especiais.append({
                    "numero": "2",
                    "titulo": "Substância ativa",
                    "content": substancia,
                    "tabelas": [],
                    "figuras": [],
                })

                print(f"✅ Substância ativa identificada: {substancia}")

                try:
                    base_dir = Path(__file__).resolve().parent
                    data_dir = base_dir / "data"

                    resolver = ActiveSubstanceExternalResolver(data_dir=data_dir)

                    resolver_result = resolver.resolve(
                        active_substance=active_substance,
                        aliases=active_substance_aliases,
                    )

                    active_substance_queries = resolver_result.get("queries") or []
                    active_substance_external_references = resolver_result.get("references") or {}

                except Exception as e:
                    print(f"⚠️ Erro no cruzamento externo da substância ativa: {e}")
                    active_substance_queries = []
                    active_substance_external_references = {
                        "status": "error",
                        "error": str(e),
                    }

            else:
                print("⚠️ Não foi possível identificar a substância ativa.")
        else:
            print("⚠️ Secção 2 não encontrada no documento.")

        todas_seccoes = campos_especiais + seccoes_numericas

        JSONExporter(output_dir).exportar(todas_seccoes)

        summary = avaliador.avaliar_documento(
            todas_seccoes,
            output_dir,
            active_substance=active_substance,
            active_substance_aliases=active_substance_aliases,
            active_substance_queries=active_substance_queries,
            active_substance_external_references=active_substance_external_references,
        )

        return {
            "pdf": str(self.pdf_path),
            "output_dir": str(output_dir),
            "active_substance": active_substance,
            "active_substance_aliases": active_substance_aliases,
            "active_substance_queries": active_substance_queries,
            "active_substance_external_references": active_substance_external_references,
            "has_pgx": bool(summary.get("has_pgx", False)),
            "has_entities": bool(summary.get("has_entities", False)),
        }