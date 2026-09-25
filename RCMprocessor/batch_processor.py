from __future__ import annotations

import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

from .rcm_processor import RCMProcessor


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S %d/%m/%Y")


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    return str(timedelta(seconds=total_seconds))


def format_avg(seconds: float) -> str:
    total_seconds = int(round(seconds))
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes} min, {secs} seg"


def validar_resultado(result: dict) -> list[str]:
    """Verifica se o processamento produziu de facto um resultado utilizável.

    Uma execução sem exceção não garante nada: o RCM da cetamina tinha a
    numeração das secções trocada e o do tramadol oral não gerou secção
    nenhuma — ambos foram reportados como processados.

    Devolve a lista de problemas encontrados; vazia significa tudo bem.
    """
    problemas = []

    if result.get("status") in ("nao_utilizavel", "digitalizacao"):
        info = result.get("scan_info") or {}
        estado = info.get("status", "")
        if estado == "corrupt":
            return [f"camada de texto ilegível: {info.get('reason', '')}"]
        if estado == "sem_estrutura":
            return ["RCM sem secções normativas detetáveis — rever formatação"]
        return ["PDF sem camada de texto (digitalização)"]

    output_dir = Path(result.get("output_dir") or "")
    if not output_dir.is_dir():
        return ["pasta de output inexistente"]

    seccoes = [f for f in output_dir.glob("*.json")]
    if not seccoes:
        problemas.append("nenhuma secção extraída")

    if not (output_dir / "pgx_outputs" / "Document_Unique_PGx.json").exists():
        problemas.append("Document_Unique_PGx.json em falta")

    if not result.get("active_substance"):
        problemas.append("substância ativa não identificada")

    # As secções onde a farmacogenómica costuma estar. A ausência das três não
    # é fatal, mas quase sempre indica numeração fora do padrão.
    nucleares = {"Interacoes_medicamentosas_e_outras_formas_de_interacao",
                 "Propriedades_farmacocineticas", "Posologia_e_modo_de_administracao"}
    presentes = {f.stem for f in seccoes}
    if seccoes and not (nucleares & presentes):
        problemas.append("nenhuma das secções 4.2/4.5/5.2 foi encontrada")

    return problemas


def write_batch_log(
    log_path: Path,
    start_dt: datetime,
    end_dt: datetime,
    total_seconds: float,
    results: list[dict],
) -> None:
    total_files = len(results)
    avg_seconds = (total_seconds / total_files) if total_files else 0.0

    lines = []
    lines.append(f"Início {format_datetime(start_dt)}")
    lines.append(f"Final {format_datetime(end_dt)}")
    lines.append(f"Duração total - {format_duration(total_seconds)}")
    lines.append(f"Tempo médio por ficheiro - {format_avg(avg_seconds)}")
    lines.append("")
    lines.append("Nome do Ficheiro - Estado - Conteúdo Farmacogenómico")

    for item in results:
        linha = f"{item['file_name']} - {item['status']} - {item['pgx_status']}"
        if item.get("aviso"):
            linha += f" - {item['aviso']}"
        lines.append(linha)

    incompletos = [r for r in results if r["status"] == "Incompleto"]
    erros = [r for r in results if r["status"] == "Erro"]

    lines.append("")
    lines.append(f"Total de ficheiros - {total_files}")
    lines.append(f"Processados com sucesso - {sum(1 for r in results if r['status'] == 'Processado')}")
    lines.append(f"Incompletos - {len(incompletos)}")
    lines.append(f"Com erro - {len(erros)}")

    # Nomeados à parte: são os que precisam de revisão manual, e num lote de
    # milhares de documentos não se encontram a percorrer a lista toda.
    if incompletos or erros:
        lines.append("")
        lines.append("DOCUMENTOS A REVER")
        for item in erros:
            lines.append(f"  ERRO       {item['file_name']}")
        for item in incompletos:
            lines.append(f"  INCOMPLETO {item['file_name']} - {item.get('aviso', '')}")

    log_path.write_text("\n".join(lines), encoding="utf-8")


def ler_lista(caminho: Path) -> list[Path]:
    """Lê uma lista de ficheiros a processar, um por linha.

    Produzida pelo `preflight`, que exclui digitalizações e colapsa duplicados
    exactos. Linhas em branco e comentários com '#' são ignorados.
    """
    ficheiros = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            ficheiros.append(Path(linha))
    return ficheiros


def run_batch(
    input_dir: Path,
    output_root: Path,
    model: str,
    file_list: Path | None = None,
    retomar: bool = False,
    markdown_dir: Path | None = None,
) -> Path:
    input_dir = input_dir.resolve()
    output_root = output_root.resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Pasta de PDFs não encontrada: {input_dir}")

    output_root.mkdir(parents=True, exist_ok=True)

    # Ignora AppleDouble ("._Nome.pdf"): o macOS cria estes ficheiros de
    # metadados ao copiar para sistemas de ficheiros não-HFS. Não são PDFs
    # válidos, mas o glob apanha-os e cada um gera um documento-fantasma no
    # output e uma linha de erro no log. A pasta RCMs2 tinha 5.
    if file_list:
        pdf_files = [p if p.is_absolute() else (input_dir / p.name)
                     for p in ler_lista(file_list)]
        ausentes = [p for p in pdf_files if not p.exists()]
        if ausentes:
            print(f"⚠️ {len(ausentes)} ficheiros da lista não existem; ignorados")
            pdf_files = [p for p in pdf_files if p.exists()]
        print(f"📋 Lista fornecida: {len(pdf_files)} documentos")
    else:
        pdf_files = sorted(
            p for p in input_dir.glob("*.pdf")
            if not p.name.startswith("._")
        )

    if not pdf_files:
        raise FileNotFoundError(f"Não foram encontrados PDFs em: {input_dir}")

    # Retoma: salta o que já tem um Document_Unique_PGx.json válido.
    #
    # Sem isto, uma falha às 6 000 de 7 800 obriga a recomeçar do zero — dias de
    # processamento perdidos. A verificação é o ficheiro final existir, não a
    # pasta: uma pasta a meio de escrita não conta como feito.
    if retomar:
        antes = len(pdf_files)
        pdf_files = [
            p for p in pdf_files
            if not (output_root / p.stem / "pgx_outputs" / "Document_Unique_PGx.json").exists()
        ]
        saltados = antes - len(pdf_files)
        if saltados:
            print(f"↩️  Retoma: {saltados} já processados, {len(pdf_files)} em falta")
        if not pdf_files:
            print("✅ Nada a fazer — todos os documentos já estão processados.")

    start_dt = datetime.now()
    t0 = perf_counter()

    results = []

    for pdf_path in pdf_files:
        print(f"\n=== A processar: {pdf_path.name} ===")

        try:
            result = RCMProcessor(
                pdf_path=str(pdf_path),
                model=model,
                output_root=str(output_root),
                markdown_dir=str(markdown_dir) if markdown_dir else None,
            ).run()

            # "Sem exceção" não é o mesmo que "processado com sucesso".
            #
            # No lote de anestésicos, o tramadol_oral não gerou uma única
            # secção e foi na mesma reportado como processado. O log dizia
            # "53 de 54 com sucesso" e escondia a falha. Num corpus de milhares
            # de documentos, um total que não é de confiança é pior do que não
            # ter total nenhum.
            problemas = validar_resultado(result)

            if problemas:
                print(f"⚠️ {pdf_path.name}: {'; '.join(problemas)}")

            results.append({
                "file_name": pdf_path.stem,
                "status": "Incompleto" if problemas else "Processado",
                "pgx_status": "Sim" if result.get("has_pgx") else "Não",
                "aviso": "; ".join(problemas),
            })

        except Exception:
            print(f"❌ Erro ao processar {pdf_path.name}")
            traceback.print_exc()

            results.append({
                "file_name": pdf_path.stem,
                "status": "Erro",
                "pgx_status": "Não",
            })

    total_seconds = perf_counter() - t0
    end_dt = datetime.now()

    timestamp = start_dt.strftime("%Y%m%d_%H%M%S")
    log_path = output_root / f"Log_Batch_Processamento_{timestamp}.txt"

    write_batch_log(
        log_path=log_path,
        start_dt=start_dt,
        end_dt=end_dt,
        total_seconds=total_seconds,
        results=results,
    )

    print(f"\n✅ Log batch criado em: {log_path}")
    return log_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Processa em batch uma pasta de PDFs RCM e gera log final"
    )
    parser.add_argument("input_dir", help="Pasta com os PDFs")
    parser.add_argument("output_root", help="Pasta raiz dos outputs")
    parser.add_argument(
        "--model",
        dest="model",
        default="gpt-oss:120b",
        help="Modelo a usar"
    )
    parser.add_argument(
        "--file-list",
        dest="file_list",
        default=None,
        help="Ficheiro com a lista de PDFs a processar, um por linha. "
             "Produzido pelo preflight (processar.txt ou lote_NN.txt)."
    )
    parser.add_argument(
        "--retomar",
        action="store_true",
        help="Saltar documentos que já tenham Document_Unique_PGx.json. "
             "Permite continuar um lote interrompido sem recomeçar."
    )
    parser.add_argument(
        "--markdown-dir",
        dest="markdown_dir",
        default=None,
        help="Pasta com markdown já convertido (<nome-do-pdf>.md). Quando o "
             "ficheiro existe, é usado em vez de reconverter o PDF. Permite "
             "separar a conversão (CPU, sem rede) da extração (rede, sem "
             "docling em memória). Sem esta opção o PDF é convertido como "
             "sempre."
    )

    args = parser.parse_args()

    run_batch(
        input_dir=Path(args.input_dir),
        output_root=Path(args.output_root),
        model=args.model,
        file_list=Path(args.file_list) if args.file_list else None,
        retomar=args.retomar,
        markdown_dir=Path(args.markdown_dir) if args.markdown_dir else None,
    )