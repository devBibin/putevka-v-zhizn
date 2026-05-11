import json

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


def _authorized(request) -> bool:
    token = getattr(settings, "AI_SERVICE_TOKEN", "") or ""
    header = request.headers.get("Authorization", "")
    return bool(token and header == f"Bearer {token}")


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _forbidden():
    return JsonResponse({"error": "forbidden"}, status=403)


@csrf_exempt
@require_POST
def claim_task(request):
    if not _authorized(request):
        return _forbidden()
    body = _json_body(request)
    worker_id = body.get("worker_id") or "ai-worker"
    lease_seconds = int(body.get("lease_seconds") or 600)
    task = claim_next_task(worker_id=worker_id, lease_seconds=lease_seconds)
    if not task:
        return JsonResponse({"task": None}, status=204)
    return JsonResponse({"task": serialize_task(task, request=request)})


@csrf_exempt
@require_POST
def heartbeat(request, task_id):
    if not _authorized(request):
        return _forbidden()
    body = _json_body(request)
    ok = heartbeat_task(task_id, body.get("worker_id") or "ai-worker", int(body.get("lease_seconds") or 600))
    return JsonResponse({"ok": ok}, status=200 if ok else 409)


@csrf_exempt
@require_POST
def complete(request, task_id):
    if not _authorized(request):
        return _forbidden()
    body = _json_body(request)
    task = complete_task(task_id, body.get("worker_id") or "ai-worker", body.get("result") or {})
    return JsonResponse({"id": str(task.pk), "status": task.status})


@csrf_exempt
@require_POST
def fail(request, task_id):
    if not _authorized(request):
        return _forbidden()
    body = _json_body(request)
    task = fail_task(
        task_id,
        body.get("worker_id") or "ai-worker",
        body.get("error") or "",
        bool(body.get("retryable", True)),
    )
    return JsonResponse({"id": str(task.pk), "status": task.status})


@require_GET
def download_file(request, token):
    if not _authorized(request):
        return _forbidden()
    return file_response_from_token(token)
