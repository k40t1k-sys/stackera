FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY examples ./examples

RUN useradd -m -u 10001 appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    APP_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT \
    APP_LOG_LEVEL=INFO \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", ${PORT}]
