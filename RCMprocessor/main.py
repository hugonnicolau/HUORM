import argparse
from .rcm_processor import RCMProcessor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Processador de RCMs (Docling + modelo + TSV)"
    )
    parser.add_argument("pdf", help="Caminho para o ficheiro PDF a processar")
    parser.add_argument(
        "--output-root",
        dest="output_root",
        default=None,
        help="Pasta raiz para guardar os outputs do documento"
    )
    parser.add_argument(
        "--model",
        dest="model",
        default="gpt-oss:120b",
        help="Modelo a usar"
    )

    args = parser.parse_args()

    RCMProcessor(
        pdf_path=args.pdf,
        model=args.model,
        output_root=args.output_root,
    ).run()