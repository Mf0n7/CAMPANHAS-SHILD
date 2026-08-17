# Imagem unica: FastAPI serve a API e as telas. Nao ha frontend separado.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8010 \
    OUTPUT_DIR=/tmp/campanhas

WORKDIR /app

# Pillow precisa das libs de imagem; o resto vem em wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g libfreetype6 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

# Sem volume: poster, texto da campanha e status vivem no Postgres.
# OUTPUT_DIR e so cache descartavel (imagens montadas do WhatsApp).
RUN useradd -m -u 10001 shild && mkdir -p /tmp/campanhas && chown -R shild /app /tmp/campanhas
USER shild

EXPOSE 8010
# /saude e LIVENESS: responde 200 se o processo esta vivo, mesmo com o banco fora.
# Nao troque por /saude/pronto aqui — esse devolve 503 quando o banco cai, e o
# orquestrador passaria a reiniciar o container em loop justamente quando voce
# precisa abrir a tela para descobrir o que ha de errado.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8010/saude || exit 1

CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8010"]
