import logging
import mimetypes
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.decorators import ensure_registration_gate
from review_by_tutor.models import TestAssignment
from review_by_tutor.utils.selection_stages import require_selection_step
from scholar_form.forms import ScholarVideoForm, UserPersonalDataForm, UserProfileForm
from scholar_form.models import ScholarVideo, UserInfo, UserPersonalData, VideoInstruction
from scholar_form.services.yandex_disk import (
    YandexDiskError,
    build_schedule_disk_path,
    build_video_disk_path,
    delete_resource,
    get_download_url,
    upload_file_to_yandex_disk,
)

logger = logging.getLogger(__name__)

UPLOAD_STATUS_TTL_SECONDS = 60 * 60


def _upload_status_key(user_id, upload_id):
    return f"scholar-video-upload:{user_id}:{upload_id}"


def _set_upload_status(user_id, upload_id, *, state, message, percent=None, asset=None):
    if not upload_id:
        return

    payload = {
        "state": state,
        "message": message,
        "percent": percent,
        "asset": asset or "",
        "updated_at": timezone.now().isoformat(),
    }
    cache.set(_upload_status_key(user_id, upload_id), payload, UPLOAD_STATUS_TTL_SECONDS)


def _get_upload_status_payload(user_id, upload_id):
    if not upload_id:
        return None
    return cache.get(_upload_status_key(user_id, upload_id))


def _resolve_file_url(remote_path, local_field):
    if remote_path:
        try:
            return get_download_url(remote_path)
        except YandexDiskError as exc:
            logger.warning("Failed to get Yandex Disk download url for %s: %s", remote_path, exc)
            return None
        except Exception:
            logger.exception("Unexpected error while resolving Yandex Disk download url for %s", remote_path)
            return None

    local_name = getattr(local_field, "name", "") or ""
    if local_name:
        return local_field.url

    return None


def _guess_mime(name):
    if not name:
        return None
    mime, _ = mimetypes.guess_type(name)
    return mime


def build_video_asset_context(video):
    if not video:
        return {
            "video_download_url": None,
            "schedule_download_url": None,
            "video_name": "",
            "schedule_name": "",
            "video_mime": None,
        }

    try:
        video_name = video.video_storage_name
        schedule_name = video.schedule_storage_name

        video_download_url = _resolve_file_url(video.yandex_disk_path, video.file)
        schedule_download_url = _resolve_file_url(video.schedule_yandex_disk_path, video.schedule_file)
    except Exception:
        logger.exception("Failed to build video asset context for scholar_video_id=%s", getattr(video, "pk", None))
        return {
            "video_download_url": None,
            "schedule_download_url": None,
            "video_name": "",
            "schedule_name": "",
            "video_mime": None,
        }

    return {
        "video_download_url": video_download_url,
        "schedule_download_url": schedule_download_url,
        "video_name": video_name,
        "schedule_name": schedule_name,
        "video_mime": _guess_mime(video_name),
    }


def _form_error_payload(form):
    payload = {}

    for field_name, errors in form.errors.items():
        if field_name == "__all__":
            payload["non_field_errors"] = list(errors)
        else:
            payload[field_name] = list(errors)

    return payload


def _make_upload_retry_callback(*, user_id, upload_id, asset):
    return lambda next_attempt, total_attempts, message: _set_upload_status(
        user_id,
        upload_id,
        state="retrying",
        message=message,
        percent=None,
        asset=asset,
    )


def _rollback_uploaded_assets(uploaded_assets, *, user_id, upload_id):
    for item in reversed(uploaded_assets):
        new_path = item.get("new_path") or ""
        asset = item.get("asset") or ""
        if not new_path:
            continue

        _set_upload_status(
            user_id,
            upload_id,
            state="rollback",
            message="Откатываем загруженные файлы после ошибки",
            percent=None,
            asset=asset,
        )
        try:
            logger.warning(
                "Rolling back uploaded scholar asset user_id=%s upload_id=%s asset=%s disk_path=%s",
                user_id,
                upload_id,
                asset,
                new_path,
            )
            delete_resource(
                new_path,
                log_context={"user_id": user_id, "upload_id": upload_id, "asset": asset, "disk_path": new_path},
            )
        except YandexDiskError as exc:
            logger.warning(
                "Failed to roll back scholar asset user_id=%s upload_id=%s asset=%s disk_path=%s error=%s",
                user_id,
                upload_id,
                asset,
                new_path,
                exc,
            )
        else:
            logger.info(
                "Rolled back scholar asset user_id=%s upload_id=%s asset=%s disk_path=%s",
                user_id,
                upload_id,
                asset,
                new_path,
            )


def _delete_replaced_assets(uploaded_assets, *, user_id, upload_id):
    for item in uploaded_assets:
        previous_path = item.get("previous_path") or ""
        new_path = item.get("new_path") or ""
        asset = item.get("asset") or ""
        if not previous_path or previous_path == new_path:
            continue

        try:
            logger.info(
                "Deleting replaced scholar asset user_id=%s upload_id=%s asset=%s old_path=%s new_path=%s",
                user_id,
                upload_id,
                asset,
                previous_path,
                new_path,
            )
            delete_resource(
                previous_path,
                log_context={"user_id": user_id, "upload_id": upload_id, "asset": asset, "disk_path": previous_path},
            )
        except YandexDiskError as exc:
            logger.warning(
                "Failed to delete replaced scholar asset user_id=%s upload_id=%s asset=%s old_path=%s error=%s",
                user_id,
                upload_id,
                asset,
                previous_path,
                exc,
            )
        else:
            logger.info(
                "Deleted replaced scholar asset user_id=%s upload_id=%s asset=%s old_path=%s",
                user_id,
                upload_id,
                asset,
                previous_path,
            )


def _upload_scholar_video_assets(obj, form, *, upload_id=""):
    uploaded_video = form.cleaned_data.get("file")
    uploaded_schedule = form.cleaned_data.get("schedule_file")
    previous_video_path = obj.yandex_disk_path
    previous_schedule_path = obj.schedule_yandex_disk_path
    previous_video_uploaded_at = obj.yandex_disk_uploaded_at
    previous_schedule_uploaded_at = obj.schedule_yandex_disk_uploaded_at
    previous_video_error = obj.yandex_disk_error
    previous_schedule_error = obj.schedule_yandex_disk_error
    uploaded_assets = []

    try:
        if uploaded_video:
            disk_path = build_video_disk_path(obj.user, uploaded_video.name)
            logger.info(
                "Uploading scholar video asset user_id=%s upload_id=%s asset=video file_name=%s size=%s disk_path=%s",
                obj.user_id,
                upload_id,
                uploaded_video.name,
                getattr(uploaded_video, "size", None),
                disk_path,
            )
            _set_upload_status(
                obj.user_id,
                upload_id,
                state="uploading_to_yandex",
                message="Сервер загружает видео на Яндекс Диск",
                percent=0,
                asset="video",
            )
            upload_file_to_yandex_disk(
                uploaded_file=uploaded_video,
                disk_path=disk_path,
                progress_callback=lambda sent, total: _set_upload_status(
                    obj.user_id,
                    upload_id,
                    state="uploading_to_yandex",
                    message="Сервер загружает видео на Яндекс Диск",
                    percent=round((sent / total) * 100) if total else None,
                    asset="video",
                ),
                log_context={
                    "user_id": obj.user_id,
                    "upload_id": upload_id,
                    "asset": "video",
                },
                retry_callback=_make_upload_retry_callback(user_id=obj.user_id, upload_id=upload_id, asset="video"),
            )
            obj.file = None
            obj.yandex_disk_path = disk_path
            obj.yandex_disk_uploaded_at = timezone.now()
            obj.yandex_disk_error = ""
            uploaded_assets.append(
                {
                    "asset": "video",
                    "new_path": disk_path,
                    "previous_path": previous_video_path,
                }
            )
            logger.info(
                "Scholar video asset uploaded user_id=%s upload_id=%s asset=video disk_path=%s",
                obj.user_id,
                upload_id,
                disk_path,
            )

        if uploaded_schedule:
            disk_path = build_schedule_disk_path(obj.user, uploaded_schedule.name)
            logger.info(
                "Uploading scholar video asset user_id=%s upload_id=%s asset=schedule file_name=%s size=%s disk_path=%s",
                obj.user_id,
                upload_id,
                uploaded_schedule.name,
                getattr(uploaded_schedule, "size", None),
                disk_path,
            )
            _set_upload_status(
                obj.user_id,
                upload_id,
                state="uploading_to_yandex",
                message="Сервер загружает график на Яндекс Диск",
                percent=0,
                asset="schedule",
            )
            upload_file_to_yandex_disk(
                uploaded_file=uploaded_schedule,
                disk_path=disk_path,
                progress_callback=lambda sent, total: _set_upload_status(
                    obj.user_id,
                    upload_id,
                    state="uploading_to_yandex",
                    message="Сервер загружает график на Яндекс Диск",
                    percent=round((sent / total) * 100) if total else None,
                    asset="schedule",
                ),
                log_context={
                    "user_id": obj.user_id,
                    "upload_id": upload_id,
                    "asset": "schedule",
                },
                retry_callback=_make_upload_retry_callback(user_id=obj.user_id, upload_id=upload_id, asset="schedule"),
            )
            obj.schedule_file = None
            obj.schedule_yandex_disk_path = disk_path
            obj.schedule_yandex_disk_uploaded_at = timezone.now()
            obj.schedule_yandex_disk_error = ""
            uploaded_assets.append(
                {
                    "asset": "schedule",
                    "new_path": disk_path,
                    "previous_path": previous_schedule_path,
                }
            )
            logger.info(
                "Scholar video asset uploaded user_id=%s upload_id=%s asset=schedule disk_path=%s",
                obj.user_id,
                upload_id,
                disk_path,
            )
    except Exception:
        _rollback_uploaded_assets(uploaded_assets, user_id=obj.user_id, upload_id=upload_id)
        obj.yandex_disk_path = previous_video_path
        obj.schedule_yandex_disk_path = previous_schedule_path
        obj.yandex_disk_uploaded_at = previous_video_uploaded_at
        obj.schedule_yandex_disk_uploaded_at = previous_schedule_uploaded_at
        obj.yandex_disk_error = previous_video_error
        obj.schedule_yandex_disk_error = previous_schedule_error
        raise

    return uploaded_assets


@login_required
@ensure_registration_gate("protected")
def personal_info(request):
    profile, _ = UserInfo.objects.get_or_create(user=request.user)
    personal_data, _ = UserPersonalData.objects.get_or_create(user=request.user)

    planned_exams_qs = profile.planned_exams.all()
    planned_exams_labels = [str(x) for x in planned_exams_qs]

    if request.method == "POST":
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        personal_form = UserPersonalDataForm(request.POST, request.FILES, instance=personal_data)

        if profile_form.is_valid() and personal_form.is_valid():
            profile_form.save()
            personal_form.save()
            return redirect("personal_info")
    else:
        profile_form = UserProfileForm(instance=profile)
        personal_form = UserPersonalDataForm(instance=personal_data)

    return render(
        request,
        "personal_info.html",
        {
            "form": profile_form,
            "personal_form": personal_form,
            "active": "personal_info",
            "profile": profile,
            "planned_exams_labels": planned_exams_labels,
        },
    )


@login_required
@ensure_registration_gate("protected")
@require_selection_step(UserInfo.SelectionStep.VIDEO)
def my_video_page(request):
    instance, _ = ScholarVideo.objects.get_or_create(user=request.user)
    video_instruction = VideoInstruction.get_current()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    upload_id = (request.POST.get("upload_id", "") or "").strip()[:128]

    if request.method == "POST":
        form = ScholarVideoForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            uploaded_video = form.cleaned_data.get("file")
            uploaded_schedule = form.cleaned_data.get("schedule_file")
            previous_video_path = instance.yandex_disk_path
            previous_schedule_path = instance.schedule_yandex_disk_path
            previous_video_uploaded_at = instance.yandex_disk_uploaded_at
            previous_schedule_uploaded_at = instance.schedule_yandex_disk_uploaded_at
            previous_video_error = instance.yandex_disk_error
            previous_schedule_error = instance.schedule_yandex_disk_error
            uploaded_assets = []
            started_at = time.monotonic()

            logger.info(
                "Scholar video upload started for user_id=%s upload_id=%s video=%s schedule=%s",
                request.user.pk,
                upload_id,
                bool(uploaded_video),
                bool(uploaded_schedule),
            )
            _set_upload_status(
                request.user.pk,
                upload_id,
                state="preparing",
                message="Подготавливаем файлы к отправке",
                percent=0,
            )

            try:
                uploaded_assets = _upload_scholar_video_assets(obj, form, upload_id=upload_id)
                _set_upload_status(
                    request.user.pk,
                    upload_id,
                    state="saving",
                    message="Сохраняем запись о видеовизитке",
                    percent=100,
                )
                obj.save()
            except YandexDiskError as exc:
                if uploaded_video and not uploaded_schedule:
                    target_field = "file"
                elif uploaded_schedule and not uploaded_video:
                    target_field = "schedule_file"
                else:
                    target_field = None

                form.add_error(target_field, str(exc))
                if obj.pk:
                    update_kwargs = {"yandex_disk_error": "", "schedule_yandex_disk_error": ""}
                    if target_field == "schedule_file":
                        update_kwargs["schedule_yandex_disk_error"] = str(exc)
                    else:
                        update_kwargs["yandex_disk_error"] = str(exc)
                    ScholarVideo.objects.filter(pk=obj.pk).update(**update_kwargs)
                logger.exception(
                    "Scholar video upload to Yandex Disk failed for user_id=%s upload_id=%s video=%s schedule=%s elapsed=%.2fs",
                    request.user.pk,
                    upload_id,
                    bool(uploaded_video),
                    bool(uploaded_schedule),
                    time.monotonic() - started_at,
                )
                _set_upload_status(
                    request.user.pk,
                    upload_id,
                    state="error",
                    message=str(exc),
                )
                messages.error(request, str(exc))
                if is_ajax:
                    return JsonResponse(
                        {
                            "ok": False,
                            "errors": _form_error_payload(form),
                        },
                        status=502,
                    )
            except Exception:
                if uploaded_assets:
                    _rollback_uploaded_assets(uploaded_assets, user_id=request.user.pk, upload_id=upload_id)
                    obj.yandex_disk_path = previous_video_path
                    obj.schedule_yandex_disk_path = previous_schedule_path
                    obj.yandex_disk_uploaded_at = previous_video_uploaded_at
                    obj.schedule_yandex_disk_uploaded_at = previous_schedule_uploaded_at
                    obj.yandex_disk_error = previous_video_error
                    obj.schedule_yandex_disk_error = previous_schedule_error
                logger.exception(
                    "Unexpected scholar video upload failure for user_id=%s upload_id=%s video=%s schedule=%s elapsed=%.2fs",
                    request.user.pk,
                    upload_id,
                    bool(uploaded_video),
                    bool(uploaded_schedule),
                    time.monotonic() - started_at,
                )
                _set_upload_status(
                    request.user.pk,
                    upload_id,
                    state="error",
                    message="Не удалось завершить загрузку. Попробуйте еще раз.",
                )
                form.add_error(None, "Не удалось завершить загрузку. Попробуйте еще раз.")
                messages.error(request, "Не удалось завершить загрузку видеовизитки.")
                if is_ajax:
                    return JsonResponse(
                        {
                            "ok": False,
                            "errors": _form_error_payload(form),
                        },
                        status=500,
                    )
            else:
                _delete_replaced_assets(uploaded_assets, user_id=request.user.pk, upload_id=upload_id)
                logger.info(
                    "Scholar video saved for user_id=%s upload_id=%s video_path=%s schedule_path=%s elapsed=%.2fs",
                    request.user.pk,
                    upload_id,
                    obj.yandex_disk_path,
                    obj.schedule_yandex_disk_path,
                    time.monotonic() - started_at,
                )
                _set_upload_status(
                    request.user.pk,
                    upload_id,
                    state="done",
                    message="Загрузка завершена",
                    percent=100,
                )
                messages.success(request, "Данные по видеовизитке сохранены.")
                if is_ajax:
                    return JsonResponse({"ok": True})
                return redirect("my_video_page")
        else:
            logger.info(
                "ScholarVideoForm invalid for user_id=%s errors=%s",
                request.user.pk,
                form.errors.as_json(),
            )
            _set_upload_status(
                request.user.pk,
                upload_id,
                state="error",
                message="Проверьте форму. Видео должно быть MP4/WebM/MOV, а график — PDF/DOC/DOCX.",
            )
            messages.error(request, "Проверь форму. Видео должно быть MP4/WebM/MOV, а график — PDF/DOC/DOCX.")
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": _form_error_payload(form),
                    },
                    status=400,
                )
    else:
        form = ScholarVideoForm(instance=instance)

    return render(
        request,
        "video_task.html",
        {
            "form": form,
            "video": instance,
            "video_instruction": video_instruction,
            "active": "my_video_page",
            "now": timezone.now(),
            **build_video_asset_context(instance),
        },
    )


@login_required
@ensure_registration_gate("protected")
@require_GET
def my_video_upload_status(request):
    upload_id = (request.GET.get("upload_id", "") or "").strip()[:128]
    if not upload_id:
        return JsonResponse({"ok": False, "error": "upload_id is required"}, status=400)

    payload = _get_upload_status_payload(request.user.pk, upload_id)
    if not payload:
        return JsonResponse(
            {
                "ok": True,
                "state": "pending",
                "message": "Ожидаем запуск загрузки",
                "percent": None,
                "asset": "",
            }
        )

    return JsonResponse({"ok": True, **payload})


@login_required
def test_assignment_complete(request, pk):
    assignment = get_object_or_404(TestAssignment, pk=pk, user=request.user)

    if request.method == "POST":
        assignment.mark_completed()
        assignment.result_filled_by = None
        assignment.result_filled_at = None
        assignment.save()
        return redirect(reverse("candidate_testing_list"))

    return redirect(reverse("candidate_testing_list"))


@login_required
def form_step_entry(request):
    user_obj = request.user
    uinfo, _ = UserInfo.objects.get_or_create(user=user_obj)

    return render(
        request,
        "stage_locked.html",
        {
            "user_obj": user_obj,
            "uinfo": uinfo,
        },
    )
