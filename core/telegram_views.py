import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.bot import process_telegram_update
from core.telegram_tasks import (
    claim_next_telegram_message,
    complete_telegram_message,
    fail_telegram_message,
    serialize_telegram_message,
)


logger = logging.getLogger(__name__)


def _authorized(request) -> bool:
    token = getattr(settings, "TELEGRAM_SERVICE_TOKEN", "") or ""
    header = request.headers.get("Authorization", "")
    return bool(token and header == f"Bearer {token}")


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _forbidden(request):
    logger.warning("Forbidden Telegram API request path=%s remote=%s", request.path, request.META.get("REMOTE_ADDR"))
    return JsonResponse({"error": "forbidden"}, status=403)


@csrf_exempt
@require_POST
def update(request):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    process_telegram_update(body)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def claim_message(request):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    worker_id = body.get("worker_id") or "telegram-worker"
    lease_seconds = int(body.get("lease_seconds") or 120)
    task = claim_next_telegram_message(worker_id=worker_id, lease_seconds=lease_seconds)
    if not task:
        return JsonResponse({"message": None}, status=204)
    logger.info("Telegram message claimed task_id=%s worker_id=%s", task.pk, worker_id)
    return JsonResponse({"message": serialize_telegram_message(task)})


@csrf_exempt
@require_POST
def complete_message(request, task_id):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    worker_id = body.get("worker_id") or "telegram-worker"
    try:
        task = complete_telegram_message(task_id, worker_id)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    logger.info("Telegram message completed task_id=%s worker_id=%s", task.pk, worker_id)
    return JsonResponse({"id": str(task.pk), "status": task.status})


@csrf_exempt
@require_POST
def fail_message(request, task_id):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    worker_id = body.get("worker_id") or "telegram-worker"
    try:
        task = fail_telegram_message(
            task_id,
            worker_id,
            body.get("error") or "",
            bool(body.get("retryable", True)),
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    logger.warning("Telegram message failed task_id=%s status=%s worker_id=%s", task.pk, task.status, worker_id)
    return JsonResponse({"id": str(task.pk), "status": task.status})
