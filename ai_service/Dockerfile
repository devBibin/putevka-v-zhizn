FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libmagic1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --timeout 30 --retries 10 -r requirements.txt

COPY ai_service ./ai_service
RUN mkdir -p core
COPY core/llm_safe.py ./core/llm_safe.py
COPY core/__init__.py ./core/__init__.py

ENV PYTHONPATH=/app

CMD ["python", "-m", "ai_service.worker"]
