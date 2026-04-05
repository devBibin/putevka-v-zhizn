import logging
import mimetypes
import re
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


def _request(method: str, resource: str, *, timeout=None, **kwargs):
    try:
        response = requests.request(
            method=method,
            url=f"{YANDEX_DISK_API_BASE}{resource}",
            headers={**_auth_headers(), **kwargs.pop("headers", {})},
            timeout=timeout or _setting("YANDEX_DISK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise YandexDiskError("Не удалось связаться с API Яндекс Диска.") from exc
    return response


def _raise_api_error(response, default_message: str):
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    message = payload.get("message") or payload.get("description") or response.text or default_message
    raise YandexDiskError(message)


def ensure_folder(path: str):
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
        )
        if response.status_code in {201, 409}:
            continue
        _raise_api_error(response, f"Не удалось создать папку {current} на Яндекс Диске.")


def delete_resource(path: str):
    normalized = _normalize_disk_path(path)
    if normalized == "disk:/":
        return

    response = _request(
        "DELETE",
        "/resources",
        params={"path": normalized, "permanently": "true"},
    )
    if response.status_code in {202, 204, 404}:
        return
    _raise_api_error(response, f"Не удалось удалить {normalized} с Яндекс Диска.")


def _get_upload_link(path: str) -> str:
    response = _request(
        "GET",
        "/resources/upload",
        params={"path": _normalize_disk_path(path), "overwrite": "true"},
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось получить ссылку для загрузки на Яндекс Диск.")

    href = response.json().get("href")
    if not href:
        raise YandexDiskError("Яндекс Диск не вернул ссылку для загрузки файла.")
    return href


def get_download_url(path: str) -> str:
    response = _request(
        "GET",
        "/resources/download",
        params={"path": _normalize_disk_path(path)},
    )
    if response.status_code != 200:
        _raise_api_error(response, "Не удалось получить ссылку для скачивания с Яндекс Диска.")

    href = response.json().get("href")
    if not href:
        raise YandexDiskError("Яндекс Диск не вернул ссылку для скачивания файла.")
    return href


def _content_type(uploaded_file) -> str:
    explicit = getattr(uploaded_file, "content_type", "") or ""
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(getattr(uploaded_file, "name", "") or "")
    return guessed or "application/octet-stream"


def upload_file_to_yandex_disk(*, uploaded_file, disk_path: str, previous_path: str = "", progress_callback=None):
    normalized_path = _normalize_disk_path(disk_path)
    parent = str(PurePosixPath(normalized_path.replace("disk:/", "", 1)).parent)
    ensure_folder(parent)

    upload_href = _get_upload_link(normalized_path)
    stream = getattr(uploaded_file, "file", uploaded_file)

    if hasattr(stream, "seek"):
        stream.seek(0)

    total_size = int(getattr(uploaded_file, "size", 0) or 0)
    payload = _ProgressReader(stream, total_size, progress_callback) if progress_callback else stream

    try:
        response = requests.put(
            upload_href,
            data=payload,
            headers={
                "Content-Type": _content_type(uploaded_file),
                "Content-Length": str(total_size),
            },
            timeout=_setting("YANDEX_DISK_UPLOAD_TIMEOUT_SECONDS", DEFAULT_UPLOAD_TIMEOUT_SECONDS),
        )
    except requests.RequestException as exc:
        raise YandexDiskError("Не удалось загрузить файл на Яндекс Диск.") from exc

    if response.status_code not in {201, 202}:
        _raise_api_error(response, "Не удалось загрузить файл на Яндекс Диск.")

    previous_normalized = _normalize_disk_path(previous_path) if previous_path else ""
    if previous_normalized and previous_normalized != normalized_path:
        try:
            delete_resource(previous_normalized)
        except YandexDiskError as exc:
            logger.warning("Failed to delete old Yandex Disk file %s: %s", previous_normalized, exc)


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


def _dated_candidate_filename(label: str, user_or_id, ext: str) -> str:
    date_prefix = timezone.localdate().strftime("%y%m%d")
    candidate_name = _candidate_short_name(user_or_id)
    return _clean_name_part(f"{date_prefix} {label} {candidate_name}", f"{date_prefix} {label}") + ext


def build_video_disk_path(user_or_id, file_name: str) -> str:
    ext = _clean_extension(file_name, ".mp4")
    return _join_disk_path(
        _setting("YANDEX_DISK_VIDEO_FOLDER", DEFAULT_VIDEO_FOLDER) or DEFAULT_VIDEO_FOLDER,
        str(timezone.localdate().year),
        _candidate_folder_name(user_or_id),
        _dated_candidate_filename("Видеовизитка", user_or_id, ext),
    )


def build_schedule_disk_path(user_or_id, file_name: str) -> str:
    ext = _clean_extension(file_name, ".pdf")
    return _join_disk_path(
        _setting("YANDEX_DISK_VIDEO_FOLDER", DEFAULT_VIDEO_FOLDER) or DEFAULT_VIDEO_FOLDER,
        str(timezone.localdate().year),
        _candidate_folder_name(user_or_id),
        _dated_candidate_filename("График занятий", user_or_id, ext),
    )
