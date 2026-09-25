import sys
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend


class PDFConverter:
    """
    Classe responsável por converter um ficheiro PDF de um RCM para Markdown,
    utilizando o Docling com o backend PyPdfium.

    Esta classe:
      - Configura o pipeline de extração do Docling;
      - Ativa a deteção de tabelas;
      - Converte o documento para um modelo interno estruturado;
      - Exporta o resultado final em formato Markdown.
    """

    def __init__(self, pdf_path: Path):
        """
        Inicializa o conversor com o caminho para o ficheiro PDF.

        Args:
            pdf_path (Path): Caminho para o ficheiro PDF a converter.
        """
        self.pdf_path = pdf_path

    def convert(self) -> str:
        """
        Converte o PDF para Markdown usando o Docling.

        Passos:
            1. Configura opções do pipeline:
               - Sem OCR (do_ocr=False);
               - Com deteção de tabelas (do_table_structure=True);
               - Sem matching avançado de células.
            2. Cria um DocumentConverter com PyPdfium como backend.
            3. Converte o PDF para o modelo interno.
            4. Exporta o documento resultante para Markdown.

        Returns:
            str: O texto completo do PDF convertido para Markdown.
        """

        # Configuração do pipeline Docling
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = False

        # Conversor Docling com backend PyPdfium
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options, backend=PyPdfiumDocumentBackend
                )
            }
        )

        # Conversão do PDF e exportação para Markdown
        result = converter.convert(str(self.pdf_path))
        markdown = result.document.export_to_markdown()

        return markdown
