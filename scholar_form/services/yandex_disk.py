import logging
import mimetypes
import re
import time
from pathlib import Path, PurePosixPath

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

logger = logging.getLogger(__name__)

YANDEX_DISK_API_BASE = "https://cloud-api.yandex.net/v1/disk"
DEFAULT_VIDEO_FOLDER = "Путевка/Видеовизитки"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_UPLOAD_TIMEOUT_SECONDS = 900
DEFAULT_API_RETRIES = 3
DEFAULT_UPLOAD_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_VERIFY_RETRIES = 5
DEFAULT_VERIFY_DELAY_SECONDS = 1.0
RETRYABLE_API_STATUS_CODES = {408, 423, 429, 500, 502, 503, 504}
RETRYABLE_UPLOAD_STATUS_CODES = RETRYABLE_API_STATUS_CODES | {409}
INVALID_DISK_NAME_RE = re.compile(r'[\\/:*?"<>|]+')
SPACE_RE = re.compile(r"\s+")


class YandexDiskError(RuntimeError):
    pass


class _ProgressReader:
    def __init__(self, stream, total_size: int, callback, chunk_size: int = 1024 * 1024):
        self._stream = stream
        self._total_size = max(int(total_size or 0), 0)
        self._callback = callback
        self._chunk_size = chunk_size
        self._sent = 0

        if self._callback:
            self._callback(0, self._total_size)

    def read(self, amt=None):
        if amt is None or amt < 0:
            amt = self._chunk_size

        chunk = self._stream.read(amt)
        if chunk:
            self._sent += len(chunk)
            if self._callback:
                self._callback(self._sent, self._total_size)
        return chunk

    def __getattr__(self, item):
        return getattr(self._stream, item)

    def __len__(self):
        return self._total_size


def _setting(name: str, default=None):
    value = getattr(settings, name, default)
    if isinstance(value, str):
        return value.strip()
    return value


def _auth_headers():
    token = _setting("YANDEX_DISK_OAUTH_TOKEN", "")
    if not token:
        raise YandexDiskError("Не настроен OAuth-токен Яндекс Диска.")
    return {"Authorization": f"OAuth {token}"}


def _normalize_disk_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return "disk:/"

    if raw.startswith("disk:/"):
        normalized = raw
    else:
        normalized = f"disk:/{raw.lstrip('/')}"

    if normalized != "disk:/":
        normalized = normalized.rstrip("/")

    return normalized


def _join_disk_path(*parts: str) -> str:
    chunks = []
    for part in parts:
        if not part:
            continue
        normalized = str(part).replace("\\", "/").strip("/")
        if normalized:
            chunks.append(normalized)
    return _normalize_disk_path("/".join(chunks))


def _log_context(log_context=None, **extra):
    payload = {}
    if log_context:
        payload.update(log_context)
    for key, value in extra.items():
        if value not in (None, ""):
            payload[key] = value
    return payload


def _log_context_suffix(log_context=None) -> str:
    payload = _log_context(log_context)
    if not payload:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in payload.items())


def _response_excerpt(response, limit: int = 300) -> str:
    body = (getattr(response, "text", "") or "").replace("\n", " ").strip()
    if len(body) <= limit:
        return body
    return body[:limit] + "..."


def _retry_delay(attempt: int) -> float:
    base = float(_setting("YANDEX_DISK_RETRY_BACKOFF_SECONDS", DEFAULT_RETRY_BACKOFF_SECONDS) or 0)
    if base <= 0:
        return 0
    return base * attempt


def _notify_retry(retry_callback, next_attempt: int, max_attempts: int, message: str):
    if retry_callback:
        retry_callback(next_attempt, max_attempts, message)


def _request(method: str, resource: str, *, timeout=None, operation="request", request_error_message="Не удалось связаться с API Яндекс Диска.", retry_statuses=None, max_attempts=None, log_context=None, retry_callback=None, **kwargs):
    allowed_retry_statuses = set(retry_statuses or RETRYABLE_API_STATUS_CODES)
    total_attempts = max(int(max_attempts or _setting("YANDEX_DISK_API_RETRIES", DEFAULT_API_RETRIES) or 1), 1)
    request_timeout = timeout or _setting("YANDEX_DISK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    extra_headers = kwargs.pop("headers", {})

    for attempt in range(1, total_attempts + 1):
        started_at = time.monotonic()
        try:
            response = requests.request(
                method=method,
                url=f"{YANDEX_DISK_API_BASE}{resource}",
                headers={**_auth_headers(), **extra_headers},
                timeout=request_timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            elapsed = time.monotonic() - started_at
            if attempt >= total_attempts:
                logger.error(
                    "Yandex Disk %s failed after %s/%s attempts elapsed=%.2fs%s error=%s",
                    operation,
                    attempt,
                    total_attempts,
                    elapsed,
                    _log_context_suffix(log_context),
                    exc,
                )
                raise YandexDiskError(request_error_message) from exc

            next_attempt = attempt + 1
            logger.warning(
                "Yandex Disk %s network error on attempt %s/%s elapsed=%.2fs%s error=%s",
                operation,
                attempt,
                total_attempts,
                elapsed,
                _log_context_suffix(log_context),
                exc,
            )
            _notify_retry(
                retry_callback,
                next_attempt,
                total_attempts,
                f"Временный сбой связи с Яндекс Диском, повторяем попытку {next_attempt}/{total_attempts}",
            )
            delay = _retry_delay(attempt)
            if delay:
                time.sleep(delay)
            continue

        elapsed = time.monotonic() - started_at
        if response.status_code in allowed_retry_statuses and attempt < total_attempts:
            next_attempt = attempt + 1
            logger.warning(
                "Yandex Disk %s returned transient status=%s on attempt %s/%s elapsed=%.2fs%s body=%s",
                operation,
                response.status_code,
                attempt,
                total_attempts,
                elapsed,
                _log_context_suffix(log_context),
                _response_excerpt(response),
            )
            _notify_retry(
                retry_callback,
                next_attempt,
                total_attempts,
                f"Яндекс Диск временно недоступен, повторяем попытку {next_attempt}/{total_attempts}",
            )
            delay = _retry_delay(attempt)
            if delay:
                time.sleep(delay)
            continue

        if attempt > 1:
            logger.info(
                "Yandex Disk %s succeeded on attempt %s/%s status=%s elapsed=%.2fs%s",
                operation,
                attempt,
                total_attempts,
                response.status_code,
                elapsed,
                _log_context_suffix(log_context),
            )
        return response

    raise YandexDiskError(request_error_message)


def _raise_api_error(response, default_message: str):
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    message = payload.get("message") or payload.get("description") or response.text or default_message
    raise YandexDiskError(message)


def ensure_folder(path: str, *, log_context=None, retry_callback=None):
    normalized = _normalize_disk_path(path)
    tail = normalized.replace("disk:/", "", 1).strip("/")
    if not tail:
        return

    current = "disk:/"
    for part in tail.split("/"):
        current = _join_disk_path(current, part)
        response = _request(
            "PUT",
            "/resources",
            params={"path": current},
            operation="ensure folder",
            request_error_message="Не удалось создать папку на Яндекс Диске.",
            log_context=_log_context(log_context, current_path=current),
            retry_callback=retry_callback,
        )
        if response.status_code in {201, 409}:
            continue
        _raise_api_error(response, f"Не удалось создать папку {current} на Яндекс Диске.")


def delete_resource(path: str, *, log_context=None, retry_callback=None):
    normalized = _normalize_disk_path(path)
    if normalized == "disk:/":
        return

    response = _request(
        "DELETE",
        "/resources",
        params={"path": normalized, "permanently": "true"},
        operation="delete resource",
        request_error_message="Не удалось удалить файл с Яндекс Диска.",
        log_context=_log_context(log_context, disk_path=normalized),
        retry_callback=retry_callback,
    )
    if response.status_code in {202, 204, 404}:
        return
    _raise_api_error(response, f"Не удалось удалить {normalized} с Яндекс Диска.")


def _get_upload_link(path: str, *, log_context=None, retry_callback=None) -> str:
    response = _request(
        "GET",
        "/resources/upload",
        params={"path": _normalize_disk_path(path), "overwrite": "true"},
        operation="get upload link",
        request_error_message="Не удалось получить ссылку для загрузки на Яндекс Диск.",
        log_context=_log_context(log_context, disk_path=_normalize_disk_path(path)),
        retry_callback=retry_callback,
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось получить ссылку для загрузки на Яндекс Диск.")

    href = response.json().get("href")
    if not href:
        raise YandexDiskError("Яндекс Диск не вернул ссылку для загрузки файла.")
    return href


def get_upload_url(path: str, *, log_context=None, retry_callback=None) -> str:
    normalized_path = _normalize_disk_path(path)
    parent = str(PurePosixPath(normalized_path.replace("disk:/", "", 1)).parent)
    ensure_folder(parent, log_context=log_context, retry_callback=retry_callback)
    return _get_upload_link(normalized_path, log_context=log_context, retry_callback=retry_callback)


def get_download_url(path: str, *, log_context=None) -> str:
    response = _request(
        "GET",
        "/resources/download",
        params={"path": _normalize_disk_path(path)},
        operation="get download link",
        request_error_message="Не удалось получить ссылку для скачивания с Яндекс Диска.",
        log_context=_log_context(log_context, disk_path=_normalize_disk_path(path)),
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось получить ссылку для скачивания с Яндекс Диска.")

    href = response.json().get("href")
    if not href:
        raise YandexDiskError("Яндекс Диск не вернул ссылку для скачивания файла.")
    return href


def get_public_download_url(public_key: str, *, public_path: str = "", log_context=None) -> str:
    params = {"public_key": public_key, "limit": 1000}
    if public_path:
        params["path"] = public_path
    response = _request(
        "GET",
        "/public/resources/download",
        params=params,
        operation="get public download link",
        request_error_message="Не удалось получить ссылку для скачивания публичного файла с Яндекс Диска.",
        log_context=_log_context(log_context),
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось получить ссылку для скачивания публичного файла с Яндекс Диска.")

    href = response.json().get("href")
    if not href:
        raise YandexDiskError("Яндекс Диск не вернул ссылку для скачивания публичного файла.")
    return href


def get_public_resource_metadata(public_key: str, *, public_path: str = "", log_context=None) -> dict:
    params = {"public_key": public_key}
    if public_path:
        params["path"] = public_path
    response = _request(
        "GET",
        "/public/resources",
        params=params,
        operation="get public resource metadata",
        request_error_message="Не удалось проверить публичный файл на Яндекс Диске.",
        log_context=_log_context(log_context),
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось проверить публичный файл на Яндекс Диске.")
    return response.json()


def get_resource_metadata(path: str, *, log_context=None) -> dict:
    normalized_path = _normalize_disk_path(path)
    response = _request(
        "GET",
        "/resources",
        params={"path": normalized_path, "limit": 1000},
        operation="get resource metadata",
        request_error_message="Не удалось проверить файл на Яндекс Диске.",
        log_context=_log_context(log_context, disk_path=normalized_path),
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось проверить файл на Яндекс Диске.")
    return response.json()


def resource_exists(path: str, *, log_context=None) -> bool:
    normalized_path = _normalize_disk_path(path)
    response = _request(
        "GET",
        "/resources",
        params={"path": normalized_path},
        operation="check resource exists",
        request_error_message="Не удалось проверить наличие файла на Яндекс Диске.",
        max_attempts=1,
        log_context=_log_context(log_context, disk_path=normalized_path),
    )
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    _raise_api_error(response, "Не удалось проверить наличие файла на Яндекс Диске.")


def _content_type(uploaded_file) -> str:
    explicit = getattr(uploaded_file, "content_type", "") or ""
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(getattr(uploaded_file, "name", "") or "")
    return guessed or "application/octet-stream"


def _rewind_stream(stream, *, attempt: int, total_attempts: int, log_context=None):
    if not hasattr(stream, "seek"):
        if attempt > 1:
            raise YandexDiskError("Не удалось повторить загрузку: поток файла не поддерживает перемотку.")
        return
    try:
        stream.seek(0)
    except (OSError, ValueError) as exc:
        logger.error(
            "Failed to rewind upload stream before attempt %s/%s%s error=%s",
            attempt,
            total_attempts,
            _log_context_suffix(log_context),
            exc,
        )
        raise YandexDiskError("Не удалось подготовить файл к повторной отправке на Яндекс Диск.") from exc


def _verify_uploaded_resource(path: str, *, log_context=None, retry_callback=None):
    normalized_path = _normalize_disk_path(path)
    total_attempts = max(int(_setting("YANDEX_DISK_VERIFY_RETRIES", DEFAULT_VERIFY_RETRIES) or 1), 1)
    delay = max(float(_setting("YANDEX_DISK_VERIFY_DELAY_SECONDS", DEFAULT_VERIFY_DELAY_SECONDS) or 0), 0)

    for attempt in range(1, total_attempts + 1):
        response = _request(
            "GET",
            "/resources",
            params={"path": normalized_path},
            operation="verify uploaded resource",
            request_error_message="Не удалось проверить загруженный файл на Яндекс Диске.",
            max_attempts=1,
            log_context=_log_context(log_context, disk_path=normalized_path),
        )
        if response.status_code == 200:
            return
        if response.status_code == 404 and attempt < total_attempts:
            next_attempt = attempt + 1
            logger.warning(
                "Uploaded resource not visible yet on attempt %s/%s%s",
                attempt,
                total_attempts,
                _log_context_suffix(_log_context(log_context, disk_path=normalized_path)),
            )
            _notify_retry(
                retry_callback,
                next_attempt,
                total_attempts,
                f"Проверяем появление файла на Яндекс Диске, попытка {next_attempt}/{total_attempts}",
            )
            if delay:
                time.sleep(delay)
            continue
        if response.status_code == 404:
            raise YandexDiskError("Файл отправлен, но не появился на Яндекс Диске. Попробуйте повторить загрузку.")
        _raise_api_error(response, "Не удалось проверить загруженный файл на Яндекс Диске.")


def upload_file_to_yandex_disk(*, uploaded_file, disk_path: str, progress_callback=None, log_context=None, retry_callback=None):
    normalized_path = _normalize_disk_path(disk_path)
    parent = str(PurePosixPath(normalized_path.replace("disk:/", "", 1)).parent)
    file_name = getattr(uploaded_file, "name", "") or ""
    stream = getattr(uploaded_file, "file", uploaded_file)
    total_size = int(getattr(uploaded_file, "size", 0) or 0)
    content_type = _content_type(uploaded_file)
    context = _log_context(
        log_context,
        disk_path=normalized_path,
        file_name=file_name,
        file_size=total_size,
        content_type=content_type,
    )

    logger.info("Yandex Disk upload started%s", _log_context_suffix(context))
    ensure_folder(parent, log_context=context, retry_callback=retry_callback)
    logger.info("Yandex Disk folder ensured%s", _log_context_suffix(context))
    upload_href = _get_upload_link(normalized_path, log_context=context, retry_callback=retry_callback)
    logger.info("Yandex Disk upload link received%s", _log_context_suffix(context))

    total_attempts = max(int(_setting("YANDEX_DISK_UPLOAD_RETRIES", DEFAULT_UPLOAD_RETRIES) or 1), 1)
    response = None
    for attempt in range(1, total_attempts + 1):
        _rewind_stream(stream, attempt=attempt, total_attempts=total_attempts, log_context=context)
        payload = _ProgressReader(stream, total_size, progress_callback) if progress_callback else stream
        started_at = time.monotonic()

        logger.info(
            "Yandex Disk binary upload attempt %s/%s started%s",
            attempt,
            total_attempts,
            _log_context_suffix(context),
        )
        try:
            response = requests.put(
                upload_href,
                data=payload,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(total_size),
                },
                timeout=_setting("YANDEX_DISK_UPLOAD_TIMEOUT_SECONDS", DEFAULT_UPLOAD_TIMEOUT_SECONDS),
            )
        except requests.RequestException as exc:
            elapsed = time.monotonic() - started_at
            if attempt >= total_attempts:
                logger.error(
                    "Yandex Disk binary upload failed after %s/%s attempts elapsed=%.2fs%s error=%s",
                    attempt,
                    total_attempts,
                    elapsed,
                    _log_context_suffix(context),
                    exc,
                )
                raise YandexDiskError("Не удалось загрузить файл на Яндекс Диск.") from exc

            next_attempt = attempt + 1
            logger.warning(
                "Yandex Disk binary upload network error on attempt %s/%s elapsed=%.2fs%s error=%s",
                attempt,
                total_attempts,
                elapsed,
                _log_context_suffix(context),
                exc,
            )
            _notify_retry(
                retry_callback,
                next_attempt,
                total_attempts,
                f"Сбой при отправке файла на Яндекс Диск, повторяем попытку {next_attempt}/{total_attempts}",
            )
            delay = _retry_delay(attempt)
            if delay:
                time.sleep(delay)
            continue

        elapsed = time.monotonic() - started_at
        if response.status_code in {201, 202}:
            logger.info(
                "Yandex Disk binary upload attempt %s/%s finished status=%s elapsed=%.2fs%s",
                attempt,
                total_attempts,
                response.status_code,
                elapsed,
                _log_context_suffix(context),
            )
            break

        if response.status_code in RETRYABLE_UPLOAD_STATUS_CODES and attempt < total_attempts:
            next_attempt = attempt + 1
            logger.warning(
                "Yandex Disk binary upload got transient status=%s on attempt %s/%s elapsed=%.2fs%s body=%s",
                response.status_code,
                attempt,
                total_attempts,
                elapsed,
                _log_context_suffix(context),
                _response_excerpt(response),
            )
            _notify_retry(
                retry_callback,
                next_attempt,
                total_attempts,
                f"Яндекс Диск временно отклонил файл, повторяем попытку {next_attempt}/{total_attempts}",
            )
            delay = _retry_delay(attempt)
            if delay:
                time.sleep(delay)
            continue

        logger.error(
            "Yandex Disk binary upload failed with status=%s on attempt %s/%s elapsed=%.2fs%s body=%s",
            response.status_code,
            attempt,
            total_attempts,
            elapsed,
            _log_context_suffix(context),
            _response_excerpt(response),
        )
        _raise_api_error(response, "Не удалось загрузить файл на Яндекс Диск.")

    _verify_uploaded_resource(normalized_path, log_context=context, retry_callback=retry_callback)
    logger.info("Yandex Disk upload verified%s", _log_context_suffix(context))


def _clean_extension(file_name: str, fallback: str) -> str:
    ext = Path(file_name or "").suffix.lower()
    return ext or fallback


def _clean_name_part(value: str, fallback: str = "") -> str:
    cleaned = INVALID_DISK_NAME_RE.sub(" ", (value or "").strip())
    cleaned = SPACE_RE.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


def _user_label_parts(user_or_id):
    if hasattr(user_or_id, "pk"):
        user_id = user_or_id.pk
        try:
            user_info = user_or_id.user_info
        except ObjectDoesNotExist:
            user_info = None
        last_name = _clean_name_part(getattr(user_info, "last_name", "") or getattr(user_or_id, "last_name", ""))
        first_name = _clean_name_part(getattr(user_info, "first_name", "") or getattr(user_or_id, "first_name", ""))
        middle_name = _clean_name_part(getattr(user_info, "middle_name", ""))
        username = _clean_name_part(getattr(user_or_id, "username", ""))
    else:
        user_id = int(user_or_id)
        last_name = ""
        first_name = ""
        middle_name = ""
        username = ""

    fallback_slug = username or f"user_{user_id}"
    return {
        "user_id": user_id,
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "fallback_slug": fallback_slug,
    }


def _candidate_folder_name(user_or_id) -> str:
    parts = _user_label_parts(user_or_id)
    full_name = " ".join(part for part in (parts["last_name"], parts["first_name"]) if part)
    folder_label = full_name or parts["fallback_slug"]
    return _clean_name_part(f"{folder_label} ({parts['user_id']})", f"user_{parts['user_id']}")


def _candidate_short_name(user_or_id) -> str:
    parts = _user_label_parts(user_or_id)
    initials = "".join(part[:1].upper() for part in (parts["first_name"], parts["middle_name"]) if part)

    if parts["last_name"] and initials:
        return _clean_name_part(f"{parts['last_name']} {initials}", parts["fallback_slug"])
    if parts["last_name"]:
        return parts["last_name"]
    if parts["first_name"]:
        return parts["first_name"]
    return parts["fallback_slug"]


def _dated_candidate_filename(label: str, user_or_id, ext: str, unique_suffix: str = "") -> str:
    date_prefix = timezone.localdate().strftime("%y%m%d")
    candidate_name = _candidate_short_name(user_or_id)
    file_stem = _clean_name_part(f"{date_prefix} {label} {candidate_name}", f"{date_prefix} {label}")
    if unique_suffix:
        file_stem = _clean_name_part(f"{file_stem} {unique_suffix}", file_stem)
    return file_stem + ext


def build_video_disk_path(user_or_id, file_name: str, unique_suffix: str = "") -> str:
    ext = _clean_extension(file_name, ".mp4")
    return _join_disk_path(
        _setting("YANDEX_DISK_VIDEO_FOLDER", DEFAULT_VIDEO_FOLDER) or DEFAULT_VIDEO_FOLDER,
        str(timezone.localdate().year),
        _candidate_folder_name(user_or_id),
        _dated_candidate_filename("Видеовизитка", user_or_id, ext, unique_suffix=unique_suffix),
    )


def build_schedule_disk_path(user_or_id, file_name: str, unique_suffix: str = "") -> str:
    ext = _clean_extension(file_name, ".pdf")
    return _join_disk_path(
        _setting("YANDEX_DISK_VIDEO_FOLDER", DEFAULT_VIDEO_FOLDER) or DEFAULT_VIDEO_FOLDER,
        str(timezone.localdate().year),
        _candidate_folder_name(user_or_id),
        _dated_candidate_filename("График занятий", user_or_id, ext, unique_suffix=unique_suffix),
    )


def download_file_from_yandex_disk(disk_path: str, local_path: str, *, log_context=None):
    url = get_download_url(disk_path, log_context=log_context)
    context = _log_context(log_context, disk_path=disk_path, local_path=local_path)
    logger.info("Downloading from Yandex Disk started%s", _log_context_suffix(context))

    started_at = time.monotonic()
    response = requests.get(url, stream=True, timeout=_setting("YANDEX_DISK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось скачать файл с Яндекс Диска.")

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    elapsed = time.monotonic() - started_at
    logger.info("Downloading from Yandex Disk finished elapsed=%.2fs%s", elapsed, _log_context_suffix(context))
