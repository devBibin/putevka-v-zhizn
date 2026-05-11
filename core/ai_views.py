import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.ai_tasks import (
    claim_next_task,
    complete_task,
    fail_task,
    file_response_from_token,
    heartbeat_task,
    serialize_task,
)


logger = logging.getLogger(__name__)


def _authorized(request) -> bool:
    token = getattr(settings, "AI_SERVICE_TOKEN", "") or ""
    header = request.headers.get("Authorization", "")
    return bool(token and header == f"Bearer {token}")


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _forbidden(request):
    logger.warning("Forbidden AI API request path=%s remote=%s", getattr(request, "path", "-"), request.META.get("REMOTE_ADDR"))
    return JsonResponse({"error": "forbidden"}, status=403)


@csrf_exempt
@require_POST
def claim_task(request):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    worker_id = body.get("worker_id") or "ai-worker"
    lease_seconds = int(body.get("lease_seconds") or 600)
    task = claim_next_task(worker_id=worker_id, lease_seconds=lease_seconds)
    if not task:
        logger.debug("AI task claim returned empty worker_id=%s lease=%s", worker_id, lease_seconds)
        return JsonResponse({"task": None}, status=204)
    logger.info("AI task claimed task_id=%s task_type=%s worker_id=%s lease=%s", task.pk, task.task_type, worker_id, lease_seconds)
    return JsonResponse({"task": serialize_task(task, request=request)})


@csrf_exempt
@require_POST
def heartbeat(request, task_id):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    ok = heartbeat_task(task_id, body.get("worker_id") or "ai-worker", int(body.get("lease_seconds") or 600))
    if not ok:
        logger.warning("AI task heartbeat rejected task_id=%s worker_id=%s", task_id, body.get("worker_id") or "ai-worker")
    return JsonResponse({"ok": ok}, status=200 if ok else 409)


@csrf_exempt
@require_POST
def complete(request, task_id):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    task = complete_task(task_id, body.get("worker_id") or "ai-worker", body.get("result") or {})
    logger.info("AI task completed task_id=%s task_type=%s worker_id=%s", task.pk, task.task_type, body.get("worker_id") or "ai-worker")
    return JsonResponse({"id": str(task.pk), "status": task.status})


@csrf_exempt
@require_POST
def fail(request, task_id):
    if not _authorized(request):
        return _forbidden(request)
    body = _json_body(request)
    task = fail_task(
        task_id,
        body.get("worker_id") or "ai-worker",
        body.get("error") or "",
        bool(body.get("retryable", True)),
    )
    logger.warning(
        "AI task failed task_id=%s task_type=%s status=%s worker_id=%s retryable=%s",
        task.pk,
        task.task_type,
        task.status,
        body.get("worker_id") or "ai-worker",
        bool(body.get("retryable", True)),
    )
    return JsonResponse({"id": str(task.pk), "status": task.status})


@require_GET
def download_file(request, token):
    if not _authorized(request):
        return _forbidden(request)
    logger.info("AI file download requested token_chars=%s", len(token or ""))
    return file_response_from_token(token)
