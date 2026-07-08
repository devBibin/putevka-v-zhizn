import logging
import os
import time
from urllib.parse import urljoin

import requests


logger = logging.getLogger(__name__)


class DjangoTelegramClient:
    def __init__(self):
        self.base_url = os.getenv("TELEGRAM_DJANGO_BASE_URL", "http://web:8000").rstrip("/") + "/"
        self.worker_id = os.getenv("TELEGRAM_WORKER_ID", "telegram-worker")
        token = os.getenv("TELEGRAM_SERVICE_TOKEN", "")
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def submit_update(self, update: dict) -> None:
        started = time.monotonic()
        response = self.session.post(self._url("/internal/telegram/updates/"), json=update, timeout=30)
        self._log_response("update", response, started)
        response.raise_for_status()

    def claim(self, lease_seconds: int) -> dict | None:
        started = time.monotonic()
        response = self.session.post(
            self._url("/internal/telegram/messages/claim/"),
            json={"worker_id": self.worker_id, "lease_seconds": lease_seconds},
            timeout=30,
        )
        self._log_response("claim", response, started)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json().get("message")

    def complete(self, task_id: str) -> None:
        started = time.monotonic()
        response = self.session.post(
            self._url(f"/internal/telegram/messages/{task_id}/complete/"),
            json={"worker_id": self.worker_id},
            timeout=30,
        )
        self._log_response("complete", response, started, task_id=task_id)
        response.raise_for_status()

    def fail(self, task_id: str, error: str, retryable: bool = True) -> None:
        started = time.monotonic()
        response = self.session.post(
            self._url(f"/internal/telegram/messages/{task_id}/fail/"),
            json={"worker_id": self.worker_id, "error": error, "retryable": retryable},
            timeout=30,
        )
        self._log_response("fail", response, started, task_id=task_id)
        response.raise_for_status()

    def _log_response(self, operation: str, response: requests.Response, started: float, task_id: str | None = None) -> None:
        elapsed = time.monotonic() - started
        log = logger.warning if response.status_code >= 400 else logger.debug
        log(
            "Django Telegram API %s status=%s elapsed=%.2fs task_id=%s",
            operation,
            response.status_code,
            elapsed,
            task_id or "-",
        )
