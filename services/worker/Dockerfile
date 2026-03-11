FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/common:/app/services/worker

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu128 -r /tmp/requirements.txt

COPY services/common /app/services/common
COPY services/worker /app/services/worker

CMD ["python", "-m", "app.main"]
