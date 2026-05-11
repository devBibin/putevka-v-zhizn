import logging
import os
import tempfile
import threading
import time

import httpx

from ai_service.client import DjangoAiClient
from ai_service.logging_config import configure_logging
from ai_service.tasks.fill_form import ask_openai_fill
from ai_service.tasks.reviewer import review_letter
from ai_service.tasks.transcribe import transcribe_media_file


configure_logging()
logger = logging.getLogger(__name__)

POLLING_INTERVAL = int(os.getenv("AI_WORKER_POLLING_INTERVAL", "10"))
LEASE_SECONDS = int(os.getenv("AI_WORKER_LEASE_SECONDS", "900"))


def _with_downloaded_file(client: DjangoAiClient, file_url: str, suffix: str = ".media"):
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    started = time.monotonic()
    logger.info("Downloading AI task media target=%s", tmp.name)
    client.download(file_url, tmp.name)
    size = os.path.getsize(tmp.name)
    logger.info("Downloaded AI task media target=%s size_bytes=%s elapsed=%.2fs", tmp.name, size, time.monotonic() - started)
    return tmp.name


def execute_task(client: DjangoAiClient, task: dict) -> dict:
    task_type = task["type"]
    payload = task.get("payload") or {}

    if task_type == "motivation_letter_review":
        logger.info(
            "Reviewing motivation letter task_id=%s text_chars=%s",
            task.get("id"),
            len(payload.get("letter_text") or ""),
        )
        return review_letter(payload.get("letter_text") or "")

    if task_type in {"interview_transcription", "scholar_video_transcription"}:
        file_path = _with_downloaded_file(client, payload["file_url"])
        try:
            logger.info("Transcribing media task_id=%s task_type=%s file=%s", task.get("id"), task_type, file_path)
            transcript = transcribe_media_file(file_path, language=payload.get("language") or "ru")
            logger.info("Transcription finished task_id=%s transcript_chars=%s", task.get("id"), len(transcript))
            return {"transcript": transcript}
        finally:
            try:
                os.remove(file_path)
                logger.debug("Removed temporary media file task_id=%s file=%s", task.get("id"), file_path)
            except OSError:
                logger.warning("Failed to remove temporary media file task_id=%s file=%s", task.get("id"), file_path, exc_info=True)

    if task_type == "interview_result_fill":
        logger.info(
            "Filling interview result task_id=%s fields=%s transcript_chars=%s",
            task.get("id"),
            len(payload.get("fields_schema") or {}),
            len(payload.get("transcript") or ""),
        )
        answers = ask_openai_fill(payload.get("fields_schema") or {}, payload.get("transcript") or "")
        logger.info("Interview result fill finished task_id=%s answer_fields=%s", task.get("id"), len(answers))
        return {"answers": answers}

    raise ValueError(f"Unknown AI task type: {task_type}")


def run_once(client: DjangoAiClient) -> bool:
    try:
        task = client.claim(lease_seconds=LEASE_SECONDS)
    except httpx.HTTPError:
        logger.warning("Django AI API is unavailable, retrying in %ss", POLLING_INTERVAL, exc_info=True)
        time.sleep(POLLING_INTERVAL)
        return False
    if not task:
        logger.debug("No AI task claimed")
        return False
    task_id = task["id"]
    started = time.monotonic()
    logger.info(
        "Claimed AI task task_id=%s task_type=%s attempt=%s locked_until=%s",
        task_id,
        task["type"],
        task.get("attempts"),
        task.get("locked_until"),
    )
    stop_heartbeat = threading.Event()

    def heartbeat_loop():
        while not stop_heartbeat.wait(max(5, LEASE_SECONDS // 3)):
            try:
                client.heartbeat(task_id, lease_seconds=LEASE_SECONDS)
                logger.debug("Heartbeat sent for AI task task_id=%s", task_id)
            except Exception:
                logger.exception("Failed heartbeat for AI task %s", task_id)

    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    try:
        result = execute_task(client, task)
        client.complete(task_id, result)
        logger.info("Completed AI task task_id=%s elapsed=%.2fs", task_id, time.monotonic() - started)
    except Exception as exc:
        logger.exception("Failed AI task task_id=%s elapsed=%.2fs", task_id, time.monotonic() - started)
        client.fail(task_id, str(exc), retryable=True)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)
    return True


def main():
    client = DjangoAiClient()
    logger.info(
        "AI worker started worker_id=%s base_url=%s polling_interval=%ss lease=%ss",
        client.worker_id,
        client.base_url,
        POLLING_INTERVAL,
        LEASE_SECONDS,
    )
    while True:
        processed = run_once(client)
        if not processed:
            time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
