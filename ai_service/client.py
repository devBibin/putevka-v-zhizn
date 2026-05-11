import os
import logging
import time
from urllib.parse import urljoin

import httpx


logger = logging.getLogger(__name__)


class DjangoAiClient:
    def __init__(self):
        self.base_url = os.getenv("AI_DJANGO_BASE_URL", "http://web:8000").rstrip("/") + "/"
        self.worker_id = os.getenv("AI_WORKER_ID", "ai-worker")
        token = os.getenv("AI_SERVICE_TOKEN", "")
        self.client = httpx.Client(
            timeout=httpx.Timeout(300.0, connect=30.0, read=300.0, write=300.0),
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def claim(self, lease_seconds: int):
        started = time.monotonic()
        response = self.client.post(
            self._url("/internal/ai/tasks/claim/"),
            json={"worker_id": self.worker_id, "lease_seconds": lease_seconds},
        )
        self._log_response("claim", response, started)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json().get("task")

    def heartbeat(self, task_id: str, lease_seconds: int):
        started = time.monotonic()
        response = self.client.post(
            self._url(f"/internal/ai/tasks/{task_id}/heartbeat/"),
            json={"worker_id": self.worker_id, "lease_seconds": lease_seconds},
        )
        self._log_response("heartbeat", response, started, task_id=task_id)
        response.raise_for_status()

    def complete(self, task_id: str, result: dict):
        started = time.monotonic()
        response = self.client.post(
            self._url(f"/internal/ai/tasks/{task_id}/complete/"),
            json={"worker_id": self.worker_id, "result": result},
        )
        self._log_response("complete", response, started, task_id=task_id)
        response.raise_for_status()

    def fail(self, task_id: str, error: str, retryable: bool = True):
        started = time.monotonic()
        response = self.client.post(
            self._url(f"/internal/ai/tasks/{task_id}/fail/"),
            json={"worker_id": self.worker_id, "error": error, "retryable": retryable},
        )
        self._log_response("fail", response, started, task_id=task_id)
        response.raise_for_status()

    def download(self, url: str, target_path: str):
        started = time.monotonic()
        response = self.client.get(url)
        self._log_response("download", response, started)
        response.raise_for_status()
        with open(target_path, "wb") as fh:
            fh.write(response.content)

    def _log_response(self, operation: str, response: httpx.Response, started: float, task_id: str | None = None) -> None:
        elapsed = time.monotonic() - started
        log = logger.warning if response.is_error else logger.debug
        log(
            "Django AI API %s status=%s elapsed=%.2fs task_id=%s",
            operation,
            response.status_code,
            elapsed,
            task_id or "-",
        )
