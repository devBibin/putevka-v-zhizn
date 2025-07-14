FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y netcat-openbsd postgresql-client && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --timeout 30 \
    --retries 10 \
    --default-timeout=30 \
    -r requirements.txt

COPY .env .
COPY telegram_bot_polling.py .

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
