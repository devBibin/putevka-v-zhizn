import logging
import os
import time
import tempfile
import subprocess

import django
import requests
from dotenv import load_dotenv
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from openai import OpenAI

import config
from core.telegram_proxy import normalize_telegram_proxy_url

import httpx

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Putevka.settings")
django.setup()

from review_by_tutor.models import Interview
from scholar_form.services.yandex_disk import get_download_url, get_public_download_url

logger = logging.getLogger(__name__)

OPENAI_API_KEY = config.GPT_TOKEN
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "5"))
POLLING_INTERVAL = int(os.getenv("INTERVIEW_TRANSCRIBE_POLLING_INTERVAL", 60))
BATCH_LIMIT = int(os.getenv("INTERVIEW_TRANSCRIBE_BATCH_LIMIT", 2))
LANGUAGE = os.getenv("INTERVIEW_TRANSCRIBE_LANGUAGE", "ru").strip() or None

MAX_MODEL_AUDIO_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_MAX_SECONDS", 1400))
CHUNK_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_SECONDS", 1100))
CHUNK_OVERLAP_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_OVERLAP_SECONDS", 2))

PROXY = normalize_telegram_proxy_url(os.getenv("TELEGRAM_SOCKS5_PROXY"))

http_client = httpx.Client(
    proxy=PROXY if PROXY else None,
    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
    limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
    verify=True,
)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=http_client,
    max_retries=OPENAI_MAX_RETRIES,
)


def _probe_duration_seconds(media_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed ({p.returncode})\n{p.stderr}")
    out = (p.stdout or "").strip()
    try:
        return float(out)
    except ValueError:
        raise RuntimeError(f"ffprobe returned non-float duration: {out!r}")


def _extract_audio_chunk(video_path: str, audio_path: str, start_sec: int, duration_sec: int) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        audio_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg chunk extract failed ({p.returncode})\n{p.stderr}")



def _extract_audio(video_path: str, audio_path: str) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        audio_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode})\n{p.stderr}")

def _transcribe_audio_file(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        kwargs = {"model": OPENAI_TRANSCRIBE_MODEL, "file": f}
        if LANGUAGE:
            kwargs["language"] = LANGUAGE
        result = client.audio.transcriptions.create(**kwargs)

    text = getattr(result, "text", None)
    return text or str(result)


def transcribe_video_file(video_path: str) -> str:
    video_duration = _probe_duration_seconds(video_path)

    if video_duration <= MAX_MODEL_AUDIO_SECONDS:
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "audio.wav")
            _extract_audio(video_path, audio_path)
            return _transcribe_audio_file(audio_path)

    parts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        step = max(1, CHUNK_SECONDS - CHUNK_OVERLAP_SECONDS)

        start = 0
        idx = 0
        total_int = int(video_duration) + 1

        while start < total_int:
            dur = min(CHUNK_SECONDS, total_int - start)
            audio_chunk_path = os.path.join(tmp, f"chunk_{idx:03d}.wav")

            _extract_audio_chunk(video_path, audio_chunk_path, start_sec=start, duration_sec=dur)

            chunk_text = _transcribe_audio_file(audio_chunk_path).strip()

            hh = start // 3600
            mm = (start % 3600) // 60
            ss = start % 60
            parts.append(f"[{hh:02d}:{mm:02d}:{ss:02d}]\n{chunk_text}\n")

            idx += 1
            start += step

    return "\n".join(parts).strip()


def pick_interviews_to_transcribe():
    return Interview.objects.filter(
        Q(video__isnull=False) & ~Q(video__exact="") |
        Q(video_source_type="yandex_disk_path", video_yandex_disk_path__gt="") |
        Q(video_source_type="yandex_public_url", video_yandex_disk_url__gt="")
    ).filter(
        transcript_status__in=["PENDING", "FAILED"]
    ).order_by("updated_at")[:BATCH_LIMIT]


def interview_video_download_href(interview: "Interview") -> str:
    if interview.video_source_type == "yandex_disk_path" and interview.video_yandex_disk_path:
        return get_download_url(
            interview.video_yandex_disk_path,
            log_context={"interview_id": interview.pk, "user_id": interview.user_id},
        )
    if interview.video_source_type == "yandex_public_url" and interview.video_yandex_disk_url:
        return get_public_download_url(
            interview.video_yandex_disk_url,
            public_path=interview.video_yandex_disk_path,
            log_context={"interview_id": interview.pk, "user_id": interview.user_id},
        )
    return ""


def download_interview_video_to_temp(interview: "Interview") -> str:
    href = interview_video_download_href(interview)
    suffix = os.path.splitext(interview.video_name or "interview_video.mp4")[1] or ".mp4"
    fd, temp_path = tempfile.mkstemp(prefix=f"interview_{interview.pk}_", suffix=suffix)
    os.close(fd)

    response = requests.get(href, stream=True, timeout=60)
    response.raise_for_status()
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return temp_path


def process_one(interview: "Interview") -> None:
    with transaction.atomic():
        obj = Interview.objects.select_for_update().get(pk=interview.pk)
        if obj.transcript_status == "DONE":
            return
        has_yandex_video = bool(
            (obj.video_source_type == "yandex_disk_path" and obj.video_yandex_disk_path) or
            (obj.video_source_type == "yandex_public_url" and obj.video_yandex_disk_url)
        )
        if not obj.video and not has_yandex_video:
            obj.transcript_status = "FAILED"
            obj.transcript_error = "Video missing"
            obj.save(update_fields=["transcript_status", "transcript_error"])
            return

        obj.transcript_status = "PROCESSING"
        obj.transcript_error = ""
        obj.save(update_fields=["transcript_status", "transcript_error"])

    temp_video_path = None
    try:
        if obj.video_source_type:
            temp_video_path = download_interview_video_to_temp(obj)
            video_path = temp_video_path
        else:
            video_path = obj.video.path
            if not os.path.exists(video_path):
                raise FileNotFoundError(video_path)

        text = transcribe_video_file(video_path)
    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)

    obj.transcript = text
    obj.transcript_status = "DONE"
    obj.transcript_updated_at = timezone.now()
    obj.save(update_fields=["transcript", "transcript_status", "transcript_updated_at"])


def transcribe_pending_interviews():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    interviews = pick_interviews_to_transcribe()
    if not interviews.exists():
        logger.info("Нет интервью для транскрибации.")
        return

    logger.info(f"Найдено {interviews.count()} интервью для транскрибации.")

    for interview in interviews:
        logger.info(f"Транскрибация Interview ID: {interview.id} (user_id={interview.user_id}) ...")
        try:
            process_one(interview)
            logger.info(f"  -> OK Interview ID {interview.id}")
        except Exception as e:
            logger.error(f"  -> FAIL Interview ID {interview.id}: {e}")
            Interview.objects.filter(pk=interview.pk).update(
                transcript_status="FAILED",
                transcript_error=str(e)[:5000],
            )


def main():
    logger.info("Запуск фонового скрипта Interview Transcriber...")
    while True:
        try:
            transcribe_pending_interviews()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)

        logger.info(f"Следующая проверка через {POLLING_INTERVAL} секунд...")
        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
