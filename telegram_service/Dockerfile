FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py .
COPY core/__init__.py ./core/__init__.py
COPY core/telegram_proxy.py ./core/telegram_proxy.py
COPY telegram_service ./telegram_service

CMD ["python", "-m", "telegram_service.worker"]
