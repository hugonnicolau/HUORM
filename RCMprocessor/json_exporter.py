import json
from pathlib import Path
from .markdown_processor import MarkdownProcessor


class JSONExporter:
    """
    Classe responsável por exportar secções processadas para ficheiros JSON.

    - Cria automaticamente a diretória de saída, caso não exista.
    - Cada secção é guardada num ficheiro JSON separado.
    - O nome do ficheiro é baseado no título da secção, devidamente normalizado.
    """

    def __init__(self, output_dir: Path):
        """
        Inicializa o exportador de JSON.

        Args:
            output_dir (Path): Diretório onde os ficheiros JSON serão guardados.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # =====================================================
    # EXPORTAÇÃO DAS SECÇÕES
    # =====================================================
    def exportar(self, seccoes: list):
        """
        Exporta cada secção para um ficheiro JSON individual.

        Cada elemento da lista 'seccoes' deve ser um dicionário contendo:
          - 'titulo'  (str): Título ou nome da secção.
          - 'content' (str): Conteúdo textual da secção.
          - 'tabelas' (list): Tabelas associadas à secção.
          - 'figuras' (list): Figuras associadas à secção.

        O nome do ficheiro é gerado a partir do título da secção,
        utilizando MarkdownProcessor.normalizar_nome_ficheiro().

        Args:
            seccoes (list): Lista de secções já processadas.

        Efeito:
            Cria um ficheiro JSON por cada secção no diretório especificado.
        """
        print(f"💾 A guardar secções em: {self.output_dir}")

        for sec in seccoes:
            titulo = sec.get("titulo", "secção_sem_titulo")
            nome_ficheiro = MarkdownProcessor.normalizar_nome_ficheiro(titulo) + ".json"
            caminho = self.output_dir / nome_ficheiro

            try:
                caminho.write_text(
                    json.dumps(sec, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"✅ {nome_ficheiro}")
            except Exception as e:
                print(f"⚠️ Erro ao guardar {nome_ficheiro}: {e}")

        print(f"\n📄 {len(seccoes)} ficheiros JSON criados com sucesso.")






