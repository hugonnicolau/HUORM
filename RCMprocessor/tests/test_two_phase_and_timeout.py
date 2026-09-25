"""
Testes das duas alterações de 15-09-2026.

**1. Execução em duas fases** (`RCMProcessor.markdown_dir`)

A conversão pelo docling e a extração pelo modelo têm naturezas opostas: a
primeira é CPU e não escala com processos, a segunda é espera de rede e escala
bem desde que não tenha o docling em memória. Separá-las exige que o pipeline
saiba ler markdown já convertido. O que estes testes garantem é que a opção é
**retrocompatível**: sem ela, o comportamento tem de ser exactamente o de antes.

**2. Timeout e classificação de erros** (`classificar_erro_llm`)

A 15-09-2026 um documento ficou mais de uma hora parado com o socket para o
ollama.com estabelecido e inactivo. Não havia timeout, portanto não havia
excepção, portanto o backoff nunca foi accionado e o processo simplesmente não
avançou. Com timeout, isso passa a ser um erro que o backoff trata — mas só se
os erros forem distinguidos: um 429 não se resolve a insistir depressa, e um
401 não se resolve de todo.

    python RCMprocessor/tests/test_two_phase_and_timeout.py
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


# ==========================================================================
#  Carregamento sem importar o pacote
#
#  O rcm_processor importa o pharmacogenomics_evaluator, que importa ollama e
#  dotenv. Nenhum teste da suite pode depender disso — a suite tem de correr
#  sem rede e sem as dependências pesadas instaladas. Extraem-se as funções do
#  código-fonte por AST, como as outras suites já fazem.
# ==========================================================================

def _extrair_funcao(ficheiro: str, nome: str, classe: str | None = None):
    """Compila uma única função/método a partir do ficheiro, isolada."""
    fonte = (RAIZ / ficheiro).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    alvo_pai = arvore
    if classe:
        alvo_pai = next(n for n in arvore.body
                        if isinstance(n, ast.ClassDef) and n.name == classe)

    no = next(n for n in alvo_pai.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == nome)

    # Descartar decoradores (@staticmethod) para poder chamar directamente.
    no.decorator_list = []
    modulo = ast.Module(body=[no], type_ignores=[])
    ast.fix_missing_locations(modulo)
    espaco: dict = {}
    exec(compile(modulo, f"<{ficheiro}:{nome}>", "exec"), espaco)  # noqa: S102
    return espaco[nome]


classificar_erro_llm = _extrair_funcao(
    "pharmacogenomics_evaluator.py", "classificar_erro_llm",
    classe="PharmacogenomicsEvaluator")

_obter_markdown = _extrair_funcao(
    "rcm_processor.py", "_obter_markdown", classe="RCMProcessor")


class _FakeProcessor:
    """O mínimo que o `_obter_markdown` toca."""

    def __init__(self, pdf_path: Path, markdown_dir: Path | None):
        self.pdf_path = pdf_path
        self.markdown_dir = markdown_dir
        self.converteu = False


def _chamar_obter_markdown(proc: _FakeProcessor, resultado_conversao: str) -> str:
    """Executa `_obter_markdown` com o PDFConverter substituído.

    A função foi extraída isolada, portanto o `PDFConverter` que ela invoca
    resolve-se nos globals que lhe dermos. É isso que permite testá-la sem
    docling instalado.
    """
    class _FakeConverter:
        def __init__(self, caminho):
            proc.converteu = True

        def convert(self):
            return resultado_conversao

    _obter_markdown.__globals__["PDFConverter"] = _FakeConverter
    return _obter_markdown(proc)


# ==========================================================================
#  1. Execução em duas fases
# ==========================================================================

def test_sem_markdown_dir_converte_como_sempre():
    """Retrocompatibilidade: sem a opção, nada muda."""
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "RCM_varfarina.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        proc = _FakeProcessor(pdf, markdown_dir=None)

        assert _chamar_obter_markdown(proc, "convertido agora") == "convertido agora"
        assert proc.converteu is True, "devia ter convertido o PDF"


def test_markdown_existente_e_usado_sem_converter():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdf = base / "RCM_varfarina.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md_dir = base / "markdown"
        md_dir.mkdir()
        # newline="" pela mesma razão do teste dos acentos: grava-se como o
        # converter_lote grava, senão no Windows o \n vira \r\n e o teste mede
        # a plataforma em vez de medir o pipeline.
        with (md_dir / "RCM_varfarina.md").open(
                "w", encoding="utf-8", newline="") as fh:
            fh.write("# 4.2 Posologia\nCYP2C9")

        proc = _FakeProcessor(pdf, markdown_dir=md_dir)
        obtido = _chamar_obter_markdown(proc, "NÃO DEVIA CONVERTER")

        assert obtido == "# 4.2 Posologia\nCYP2C9"
        assert proc.converteu is False, "não devia ter chamado o docling"


def test_markdown_dir_sem_o_ficheiro_converte():
    """Um documento que a fase 1 não converteu não pode ser perdido em
    silêncio: converte-se na hora."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdf = base / "RCM_novo.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md_dir = base / "markdown"
        md_dir.mkdir()
        (md_dir / "RCM_outro.md").write_text("outro documento", encoding="utf-8")

        proc = _FakeProcessor(pdf, markdown_dir=md_dir)

        assert _chamar_obter_markdown(proc, "convertido agora") == "convertido agora"
        assert proc.converteu is True


def test_carriage_returns_sobrevivem_a_leitura():
    """O \\r do docling não pode virar \\n ao ser lido de disco.

    O docling emite \\r dentro das células de tabelas multi-linha — 521 num
    único RCM da rifampicina. Uma leitura em modo texto normal traduz todos
    esses \\r em \\n, e a fase 2 passaria ao modelo um texto diferente do que
    a execução numa fase só produziria. Foi assim que o teste de equivalência
    deu 1/11 a 16-09-2026: o único documento que passou não tinha \\r nenhum.
    """
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdf = base / "RCM_Rifampicina.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md_dir = base / "markdown"
        md_dir.mkdir()

        original = "| Fármaco ou classe de \r fármaco    | Efeito |\n\nlinha normal\n"
        with (md_dir / "RCM_Rifampicina.md").open(
                "w", encoding="utf-8", newline="") as fh:
            fh.write(original)

        proc = _FakeProcessor(pdf, markdown_dir=md_dir)
        obtido = _chamar_obter_markdown(proc, "")

        assert obtido == original, "o markdown lido não é byte a byte o gravado"
        assert "\r" in obtido, "os carriage returns foram traduzidos na leitura"
        assert obtido.count("\r") == original.count("\r")


def test_acentos_no_markdown_sobrevivem():
    """Os RCM são em português e o markdown é lido de disco. Uma leitura sem
    encoding explícito partiria em Windows, onde o default é cp1252."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdf = base / "RCM_indapamida.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md_dir = base / "markdown"
        md_dir.mkdir()
        texto = "## 2. COMPOSIÇÃO QUALITATIVA E QUANTITATIVA\nIndapamida — 1,5 mg"
        # newline="" para o teste gravar os mesmos bytes que o converter_lote
        # grava. Sem isto, no Windows o write_text traduz \n para \r\n, o
        # pipeline devolve fielmente o \r\n que está no ficheiro — que é o
        # comportamento certo — e o teste falhava por comparar com a string
        # original. O teste estava a assumir Unix sem querer.
        with (md_dir / "RCM_indapamida.md").open(
                "w", encoding="utf-8", newline="") as fh:
            fh.write(texto)

        proc = _FakeProcessor(pdf, markdown_dir=md_dir)
        assert _chamar_obter_markdown(proc, "") == texto


# ==========================================================================
#  2. Classificação dos erros do modelo
# ==========================================================================

class _ErroHttp(Exception):
    def __init__(self, status: int, mensagem: str = ""):
        super().__init__(mensagem or f"status {status}")
        self.status_code = status


def test_429_e_identificado_como_limite_de_pedidos():
    rotulo, status = classificar_erro_llm(_ErroHttp(429))
    assert status == 429
    assert "limite" in rotulo


def test_502_e_indisponibilidade_e_nao_limite():
    """Distinção que importa: 502 repete-se com o backoff normal, 429 não."""
    rotulo, status = classificar_erro_llm(_ErroHttp(502))
    assert status == 502
    assert "indispon" in rotulo
    assert "limite" not in rotulo


def test_timeout_sem_status_e_reconhecido():
    rotulo, status = classificar_erro_llm(
        TimeoutError("Request timed out after 300s"))
    assert rotulo == "timeout"
    assert status is None


def test_429_no_texto_e_apanhado_sem_status_code():
    """Nem todos os clientes expõem status_code — o ollama embrulha alguns
    erros em excepções genéricas."""
    _, status = classificar_erro_llm(Exception("server returned 429 Too Many Requests"))
    assert status == 429


def test_falha_de_ligacao():
    rotulo, status = classificar_erro_llm(Exception("Connection refused"))
    assert rotulo == "falha de ligação"
    assert status is None


def test_erro_desconhecido_devolve_o_tipo():
    rotulo, status = classificar_erro_llm(ValueError("qualquer coisa"))
    assert rotulo == "ValueError"
    assert status is None


# ==========================================================================
#  3. Constantes: o timeout tem de existir e ser usado
# ==========================================================================

def _constante(nome: str):
    fonte = (RAIZ / "pharmacogenomics_evaluator.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    classe = next(n for n in arvore.body
                  if isinstance(n, ast.ClassDef)
                  and n.name == "PharmacogenomicsEvaluator")
    for no in classe.body:
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name) and alvo.id == nome:
                    valor = no.value
                    # `frozenset({...})` não é um literal: o literal_eval
                    # rejeita a chamada. Desembrulha-se o argumento.
                    if (isinstance(valor, ast.Call)
                            and isinstance(valor.func, ast.Name)
                            and valor.func.id in ("frozenset", "set")):
                        return frozenset(ast.literal_eval(valor.args[0]))
                    return ast.literal_eval(valor)
    raise AssertionError(f"constante {nome} não encontrada")


def test_timeout_definido_e_plausivel():
    t = _constante("LLM_TIMEOUT")
    assert 60 <= t <= 900, (
        f"LLM_TIMEOUT={t}: curto demais aborta trabalho legítimo, "
        f"longo demais não protege de um pedido pendurado")


def test_backoff_do_429_e_maior_que_o_normal():
    assert _constante("LLM_BACKOFF_RATE_LIMIT") > _constante("LLM_BACKOFF_BASE")


def test_estados_sem_retentativa_nao_incluem_transitorios():
    sem_retry = set(_constante("LLM_STATUS_SEM_RETENTATIVA"))
    assert 401 in sem_retry and 404 in sem_retry
    for transitorio in (429, 500, 502, 503, 504):
        assert transitorio not in sem_retry, (
            f"{transitorio} é transitório e tem de ser repetido")


def test_cliente_construido_com_timeout():
    """Ter a constante não chega — ela tem de chegar ao cliente."""
    fonte = (RAIZ / "pharmacogenomics_evaluator.py").read_text(encoding="utf-8")
    inicio = fonte.index("self.client = Client(")
    trecho = fonte[inicio:inicio + 400]
    assert "timeout=" in trecho, "o Client é construído sem timeout"
    assert "LLM_TIMEOUT" in trecho


# ==========================================================================
if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passaram")
    sys.exit(1 if failures else 0)
