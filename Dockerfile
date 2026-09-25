# Imagem de execucao do pipeline de extraccao.
#
# Fixa o ambiente local: Python, bibliotecas e modelos do docling. NAO fixa o
# servico remoto do modelo, que e a fonte de variabilidade discutida no
# capitulo 4 — por isso a imagem torna o ambiente reinstanciavel, nao torna a
# saida determinista.
#
# Construir:
#     docker build -t rcmprocessor:2.0.0 .
#
# Correr, montando os PDFs e a pasta de saida:
#     docker run --rm \
#       -e OLLAMA_API_KEY \
#       -v "$PWD/RCMs_a_processar:/dados/entrada:ro" \
#       -v "$PWD/out_nacional:/dados/saida" \
#       rcmprocessor:2.0.0 /dados/entrada /dados/saida --model glm-5.3-flash
#
# A chave do servico entra por variavel de ambiente e nunca fica na imagem.

FROM python:3.12.10-slim

# O docling precisa destas para abrir PDFs e para os modelos de layout.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalado antes do codigo para a camada das dependencias ser reaproveitada
# entre construcoes quando so o codigo muda.
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# Modelos de layout e de estrutura de tabelas do docling, descarregados na
# construcao. Sem este passo a primeira execucao iria busca-los a rede, e uma
# imagem que precisa de rede para arrancar nao fixa o ambiente.
RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

COPY RCMprocessor/ ./RCMprocessor/

# Sem escrita como root no material montado.
RUN useradd -m -u 1000 pipeline && chown -R pipeline:pipeline /app
USER pipeline

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

ENTRYPOINT ["python", "-m", "RCMprocessor.batch_processor"]
