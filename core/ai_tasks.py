import hashlib
import json
import logging
import os
import tempfile
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner
from django.db import models, transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import AiTask, MotivationLetter, MotivationLetterRubricReview


logger = logging.getLogger(__name__)

FILE_TOKEN_MAX_AGE = int(getattr(settings, "AI_FILE_TOKEN_MAX_AGE", 3600))


class DeletingFileResponse(FileResponse):
    def __init__(self, *args, delete_path: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_path = delete_path

    def close(self):
        super().close()
        if self.delete_path:
            try:
                os.remove(self.delete_path)
                logger.debug("Deleted proxied AI temp file path=%s", self.delete_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Failed to delete proxied AI temp file path=%s", self.delete_path, exc_info=True)


def _version_from_value(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _source_kwargs(obj: models.Model) -> dict[str, Any]:
    return {
        "source_app": obj._meta.app_label,
        "source_model": obj._meta.model_name,
        "source_object_id": obj.pk,
    }


def _pending_exists(task_type: str, obj: models.Model, source_version: str = "") -> bool:
    return AiTask.objects.filter(
        task_type=task_type,
        status__in=[AiTask.Status.PENDING, AiTask.Status.PROCESSING, AiTask.Status.RETRY],
        source_version=source_version,
        **_source_kwargs(obj),
    ).exists()


def create_ai_task(task_type: str, obj: models.Model, payload: dict[str, Any], source_version: str = "") -> AiTask:
    if _pending_exists(task_type, obj, source_version):
        task = AiTask.objects.filter(
            task_type=task_type,
            status__in=[AiTask.Status.PENDING, AiTask.Status.PROCESSING, AiTask.Status.RETRY],
            source_version=source_version,
            **_source_kwargs(obj),
        ).latest("created_at")
        logger.info(
            "AI task already pending task_id=%s task_type=%s source=%s.%s:%s status=%s",
            task.pk,
            task_type,
            obj._meta.app_label,
            obj._meta.model_name,
            obj.pk,
            task.status,
        )
        return task

    task = AiTask.objects.create(
        task_type=task_type,
        payload=payload,
        source_version=source_version,
        **_source_kwargs(obj),
    )
    logger.info(
        "AI task created task_id=%s task_type=%s source=%s.%s:%s payload_keys=%s",
        task.pk,
        task_type,
        obj._meta.app_label,
        obj._meta.model_name,
        obj.pk,
        ",".join(sorted(payload.keys())),
    )
    return task


def enqueue_motivation_letter_review(letter: MotivationLetter) -> AiTask | None:
    if letter.status != MotivationLetter.Status.SUBMITTED or not (letter.letter_text or "").strip():
        logger.debug("Skipped motivation letter AI enqueue letter_id=%s status=%s", letter.pk, letter.status)
        return None
    version = _version_from_value(letter.letter_text)
    return create_ai_task(
        AiTask.Type.MOTIVATION_LETTER_REVIEW,
        letter,
        {"letter_text": letter.letter_text},
        source_version=version,
    )


def enqueue_interview_transcription(interview) -> AiTask | None:
    if not getattr(interview, "video", None):
        logger.debug("Skipped interview transcription enqueue interview_id=%s reason=no_video", getattr(interview, "pk", None))
        return None
    if interview.transcript_status == "DONE":
        logger.debug("Skipped interview transcription enqueue interview_id=%s reason=already_done", interview.pk)
        return None
    token = make_file_token("review_by_tutor", "interview", interview.pk, "video")
    return create_ai_task(
        AiTask.Type.INTERVIEW_TRANSCRIPTION,
        interview,
        {"file_url": f"/internal/ai/files/{token}/", "language": "ru"},
        source_version=getattr(interview.video, "name", "") or str(interview.pk),
    )


def enqueue_scholar_video_transcription(video) -> AiTask | None:
    if not video.has_video_file or video.transcript_status == "DONE":
        logger.debug(
            "Skipped scholar video transcription enqueue video_id=%s has_file=%s status=%s",
            getattr(video, "pk", None),
            getattr(video, "has_video_file", None),
            getattr(video, "transcript_status", None),
        )
        return None
    token = make_file_token("scholar_form", "scholarvideo", video.pk, "file")
    return create_ai_task(
        AiTask.Type.SCHOLAR_VIDEO_TRANSCRIPTION,
        video,
        {"file_url": f"/internal/ai/files/{token}/", "language": "ru"},
        source_version=video.yandex_disk_path or getattr(video.file, "name", "") or str(video.pk),
    )


def enqueue_interview_result_fill(interview) -> AiTask | None:
    if interview.transcript_status != "DONE" or not (interview.transcript or "").strip():
        logger.debug("Skipped interview fill enqueue interview_id=%s transcript_status=%s", interview.pk, interview.transcript_status)
        return None
    if interview.ai_fill_status == "DONE":
        logger.debug("Skipped interview fill enqueue interview_id=%s reason=already_done", interview.pk)
        return None
    fields_schema = build_interview_result_schema()
    return create_ai_task(
        AiTask.Type.INTERVIEW_RESULT_FILL,
        interview,
        {"transcript": interview.transcript, "fields_schema": fields_schema},
        source_version=_version_from_value(interview.transcript),
    )


def claim_next_task(worker_id: str, lease_seconds: int = 600) -> AiTask | None:
    now = timezone.now()
    lease_until = now + timedelta(seconds=lease_seconds)
    with transaction.atomic():
        task = (
            AiTask.objects.select_for_update(skip_locked=True)
            .filter(
                models.Q(status__in=[AiTask.Status.PENDING, AiTask.Status.RETRY])
                | models.Q(status=AiTask.Status.PROCESSING, locked_until__lt=now)
            )
            .filter(attempts__lt=models.F("max_attempts"))
            .order_by("created_at")
            .first()
        )
        if not task:
            logger.debug("No claimable AI tasks worker_id=%s", worker_id)
            return None
        task.status = AiTask.Status.PROCESSING
        task.locked_by = worker_id
        task.locked_until = lease_until
        task.started_at = task.started_at or now
        task.attempts += 1
        task.error = ""
        task.save(update_fields=["status", "locked_by", "locked_until", "started_at", "attempts", "error", "updated_at"])
        mark_source_processing(task)
        logger.info(
            "AI task locked task_id=%s task_type=%s worker_id=%s attempt=%s lease_until=%s",
            task.pk,
            task.task_type,
            worker_id,
            task.attempts,
            lease_until.isoformat(),
        )
        return task


def serialize_task(task: AiTask, request=None) -> dict[str, Any]:
    payload = dict(task.payload or {})
    if request and "file_url" in payload and str(payload["file_url"]).startswith("/"):
        payload["file_url"] = request.build_absolute_uri(payload["file_url"])
    return {
        "id": str(task.pk),
        "type": task.task_type,
        "payload": payload,
        "attempts": task.attempts,
        "locked_until": task.locked_until.isoformat() if task.locked_until else None,
    }


def heartbeat_task(task_id, worker_id: str, lease_seconds: int = 600) -> bool:
    updated = AiTask.objects.filter(pk=task_id, status=AiTask.Status.PROCESSING, locked_by=worker_id).update(
        locked_until=timezone.now() + timedelta(seconds=lease_seconds),
        updated_at=timezone.now(),
    )
    if updated:
        logger.debug("AI task heartbeat task_id=%s worker_id=%s lease=%s", task_id, worker_id, lease_seconds)
    return bool(updated)


def complete_task(task_id, worker_id: str, result: dict[str, Any]) -> AiTask:
    with transaction.atomic():
        task = AiTask.objects.select_for_update().get(pk=task_id)
        if task.status == AiTask.Status.DONE:
            return task
        if task.locked_by and task.locked_by != worker_id:
            raise ValueError("Task is locked by another worker")
        apply_task_result(task, result)
        task.status = AiTask.Status.DONE
        task.result = result
        task.error = ""
        task.locked_until = None
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result", "error", "locked_until", "finished_at", "updated_at"])
        logger.info("AI task persisted done task_id=%s task_type=%s worker_id=%s", task.pk, task.task_type, worker_id)
        return task


def fail_task(task_id, worker_id: str, error: str, retryable: bool = True) -> AiTask:
    with transaction.atomic():
        task = AiTask.objects.select_for_update().get(pk=task_id)
        if task.locked_by and task.locked_by != worker_id:
            raise ValueError("Task is locked by another worker")
        final = not retryable or task.attempts >= task.max_attempts
        task.status = AiTask.Status.FAILED if final else AiTask.Status.RETRY
        task.error = (error or "")[:5000]
        task.locked_until = None
        task.finished_at = timezone.now() if final else None
        task.save(update_fields=["status", "error", "locked_until", "finished_at", "updated_at"])
        if final:
            mark_source_failed(task, task.error)
        logger.warning(
            "AI task persisted failure task_id=%s task_type=%s status=%s worker_id=%s final=%s error=%s",
            task.pk,
            task.task_type,
            task.status,
            worker_id,
            final,
            task.error[:300],
        )
        return task


def get_source_object(task: AiTask):
    model = apps.get_model(task.source_app, task.source_model)
    return model.objects.select_for_update().get(pk=task.source_object_id)


def mark_source_processing(task: AiTask) -> None:
    obj = get_source_object(task)
    if task.task_type == AiTask.Type.INTERVIEW_TRANSCRIPTION:
        obj.transcript_status = "PROCESSING"
        obj.transcript_error = ""
        obj.save(update_fields=["transcript_status", "transcript_error"])
    elif task.task_type == AiTask.Type.SCHOLAR_VIDEO_TRANSCRIPTION:
        obj.transcript_status = "PROCESSING"
        obj.transcript_error = ""
        obj.save(update_fields=["transcript_status", "transcript_error"])
    elif task.task_type == AiTask.Type.INTERVIEW_RESULT_FILL:
        obj.ai_fill_status = obj.AiFillStatus.PROCESSING
        obj.ai_fill_error = ""
        obj.save(update_fields=["ai_fill_status", "ai_fill_error"])
    logger.info("AI source marked processing task_id=%s source=%s.%s:%s", task.pk, task.source_app, task.source_model, task.source_object_id)


def mark_source_failed(task: AiTask, error: str) -> None:
    obj = get_source_object(task)
    if task.task_type == AiTask.Type.INTERVIEW_TRANSCRIPTION:
        obj.transcript_status = "FAILED"
        obj.transcript_error = error
        obj.save(update_fields=["transcript_status", "transcript_error"])
    elif task.task_type == AiTask.Type.SCHOLAR_VIDEO_TRANSCRIPTION:
        obj.transcript_status = "FAILED"
        obj.transcript_error = error
        obj.save(update_fields=["transcript_status", "transcript_error"])
    elif task.task_type == AiTask.Type.INTERVIEW_RESULT_FILL:
        obj.ai_fill_status = obj.AiFillStatus.FAILED
        obj.ai_fill_error = error
        obj.save(update_fields=["ai_fill_status", "ai_fill_error"])
    logger.warning("AI source marked failed task_id=%s source=%s.%s:%s", task.pk, task.source_app, task.source_model, task.source_object_id)


def apply_task_result(task: AiTask, result: dict[str, Any]) -> None:
    obj = get_source_object(task)
    if task.task_type == AiTask.Type.MOTIVATION_LETTER_REVIEW:
        review_kwargs = result["review"]
        MotivationLetterRubricReview.objects.update_or_create(letter=obj, defaults=review_kwargs)
        obj.is_done = True
        obj.save(update_fields=["is_done", "updated_at"])
        logger.info("Applied AI motivation review task_id=%s letter_id=%s score=%s", task.pk, obj.pk, review_kwargs.get("total_score"))
    elif task.task_type == AiTask.Type.INTERVIEW_TRANSCRIPTION:
        obj.transcript = result.get("transcript", "")
        obj.transcript_status = "DONE"
        obj.transcript_error = ""
        obj.transcript_updated_at = timezone.now()
        obj.save(update_fields=["transcript", "transcript_status", "transcript_error", "transcript_updated_at"])
        enqueue_interview_result_fill(obj)
        logger.info("Applied AI interview transcript task_id=%s interview_id=%s transcript_chars=%s", task.pk, obj.pk, len(obj.transcript or ""))
    elif task.task_type == AiTask.Type.SCHOLAR_VIDEO_TRANSCRIPTION:
        obj.transcript_text = result.get("transcript", "")
        obj.transcript_status = "DONE"
        obj.transcript_error = ""
        obj.transcript_updated_at = timezone.now()
        obj.save(update_fields=["transcript_text", "transcript_status", "transcript_error", "transcript_updated_at"])
        logger.info("Applied AI scholar video transcript task_id=%s video_id=%s transcript_chars=%s", task.pk, obj.pk, len(obj.transcript_text or ""))
    elif task.task_type == AiTask.Type.INTERVIEW_RESULT_FILL:
        apply_interview_result(obj, result.get("answers", {}))
        logger.info("Applied AI interview result fill task_id=%s interview_id=%s answer_fields=%s", task.pk, obj.pk, len(result.get("answers", {})))


def build_interview_result_schema() -> dict[str, str]:
    from review_by_tutor.models import InterviewResult

    skip = {"id", "pk", "interview", "created_at", "updated_at", "started_at", "finished_at", "status"}
    schema = {}
    for field in InterviewResult._meta.get_fields():
        if not getattr(field, "concrete", False) or getattr(field, "many_to_many", False):
            continue
        if getattr(field, "is_relation", False) and field.name != "interview":
            continue
        if field.name in skip:
            continue
        schema[field.name] = f"{field.verbose_name} (field: {field.name}, type: {field.__class__.__name__})"
    return schema


def apply_interview_result(interview, answers: dict[str, Any]) -> None:
    from review_by_tutor.models import InterviewResult

    result_obj, _ = InterviewResult.objects.get_or_create(interview=interview)
    fields = [f for f in InterviewResult._meta.get_fields() if getattr(f, "concrete", False) and f.name in answers]
    update_fields = apply_answers_to_result(result_obj, fields, answers)
    if not update_fields:
        logger.warning("AI returned no applicable InterviewResult updates interview_id=%s answer_fields=%s", interview.pk, len(answers))
        raise ValueError("AI returned no applicable InterviewResult updates")
    result_obj.updated_at = timezone.now()
    update_fields.append("updated_at")
    result_obj.save(update_fields=update_fields)
    interview.ai_fill_status = interview.AiFillStatus.DONE
    interview.ai_filled_at = timezone.now()
    interview.ai_fill_error = ""
    interview.save(update_fields=["ai_fill_status", "ai_filled_at", "ai_fill_error"])
    logger.info("InterviewResult updated from AI interview_id=%s fields=%s", interview.pk, ",".join(update_fields))


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _normalize_for_field(field: models.Field, raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return ""
    if isinstance(field, models.BooleanField):
        text = str(raw).strip().lower()
        if text in {"да", "true", "истина", "1", "yes", "y"}:
            return True
        if text in {"нет", "false", "ложь", "0", "no", "n"}:
            return False
        return raw if isinstance(raw, bool) else None
    if isinstance(field, (models.IntegerField, models.PositiveIntegerField, models.BigIntegerField, models.SmallIntegerField)):
        if isinstance(raw, int):
            return raw
        text = str(raw).strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return None
        return (-1 if text.startswith("-") else 1) * int(digits)
    if isinstance(field, models.DecimalField):
        if isinstance(raw, Decimal):
            return raw
        cleaned = "".join(ch for ch in str(raw).strip().replace(",", ".") if ch in set("0123456789.-"))
        if cleaned in {"", "-", ".", "-."}:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    if isinstance(field, models.DateField) and not isinstance(field, models.DateTimeField):
        return parse_date(str(raw).strip())
    if isinstance(field, models.DateTimeField):
        return parse_datetime(str(raw).strip())
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw).strip()


def apply_answers_to_result(result_obj, fields: list[models.Field], answers: dict[str, Any]) -> list[str]:
    update_fields: list[str] = []
    for field in fields:
        old_value = getattr(result_obj, field.name, None)
        new_value = _normalize_for_field(field, answers.get(field.name))
        if new_value is None or (isinstance(new_value, str) and not new_value.strip()):
            continue
        if isinstance(field, (models.CharField, models.TextField)):
            if _empty(old_value):
                setattr(result_obj, field.name, new_value)
            else:
                setattr(result_obj, field.name, f"Заметка куратора: {old_value.rstrip()}\n\nВариант нейронки:\n{new_value.strip()}")
            update_fields.append(field.name)
        elif _empty(old_value):
            setattr(result_obj, field.name, new_value)
            update_fields.append(field.name)
    return update_fields


def make_file_token(app_label: str, model_name: str, object_id: int, field_name: str) -> str:
    return TimestampSigner(salt="ai-file").sign(json.dumps([app_label, model_name, object_id, field_name]))


def _scholar_video_yandex_source(obj, field_name: str) -> tuple[str, str]:
    if field_name == "file" and getattr(obj, "yandex_disk_path", ""):
        return obj.yandex_disk_path, obj.video_storage_name or "video.mp4"
    if field_name == "schedule_file" and getattr(obj, "schedule_yandex_disk_path", ""):
        return obj.schedule_yandex_disk_path, obj.schedule_storage_name or "schedule.pdf"
    return "", ""


def open_file_from_token(token: str):
    try:
        raw = TimestampSigner(salt="ai-file").unsign(token, max_age=FILE_TOKEN_MAX_AGE)
        app_label, model_name, object_id, field_name = json.loads(raw)
    except (BadSignature, ValueError, TypeError):
        raise Http404("File token is invalid")
    model = apps.get_model(app_label, model_name)
    obj = model.objects.get(pk=object_id)

    if app_label == "scholar_form" and model_name == "scholarvideo":
        from scholar_form.services.yandex_disk import download_file_from_yandex_disk

        disk_path, filename = _scholar_video_yandex_source(obj, field_name)
        if disk_path:
            suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".media"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.close()
            download_file_from_yandex_disk(disk_path, tmp.name, log_context={"user_id": obj.user_id})
            logger.info("Opened AI file from Yandex Disk source=%s.%s:%s field=%s filename=%s", app_label, model_name, object_id, field_name, filename)
            return open(tmp.name, "rb"), filename, tmp.name

    file_field = getattr(obj, field_name)
    if not file_field:
        raise Http404("File is missing")
    logger.info("Opened AI file source=%s.%s:%s field=%s filename=%s", app_label, model_name, object_id, field_name, file_field.name)
    return file_field.open("rb"), file_field.name.rsplit("/", 1)[-1], None


def file_response_from_token(token: str) -> FileResponse:
    fh, filename, delete_path = open_file_from_token(token)
    return DeletingFileResponse(fh, as_attachment=True, filename=filename, delete_path=delete_path)
