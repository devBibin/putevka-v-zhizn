import logging
import os
import time
import tempfile
import subprocess

import django
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Putevka.settings")
django.setup()

from django.db import transaction, models
from django.utils import timezone

from openai import OpenAI

import config
from scholar_form.models import ScholarVideo
from scholar_form.services.yandex_disk import download_file_from_yandex_disk

logger = logging.getLogger(__name__)

OPENAI_API_KEY = config.GPT_TOKEN
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
POLLING_INTERVAL = int(os.getenv("VIDEO_TRANSCRIBE_POLLING_INTERVAL", 60))
BATCH_LIMIT = int(os.getenv("VIDEO_TRANSCRIBE_BATCH_LIMIT", 2))
LANGUAGE = os.getenv("VIDEO_TRANSCRIBE_LANGUAGE", "ru").strip() or None

MAX_MODEL_AUDIO_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_MAX_SECONDS", 1400))
CHUNK_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_SECONDS", 1100))
CHUNK_OVERLAP_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_OVERLAP_SECONDS", 2))

client = OpenAI(api_key=OPENAI_API_KEY)


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


def pick_videos_to_transcribe():
    return ScholarVideo.objects.filter(
        models.Q(file__isnull=False) & ~models.Q(file__exact="") |
        models.Q(yandex_disk_path__isnull=False) & ~models.Q(yandex_disk_path__exact="")
    ).filter(
        transcript_status__in=["PENDING", "FAILED"]
    ).order_by("updated_at")[:BATCH_LIMIT]


def process_one(video_obj: "ScholarVideo") -> None:
    with transaction.atomic():
        obj = ScholarVideo.objects.select_for_update().get(pk=video_obj.pk)
        if obj.transcript_status == "DONE":
            return

        has_local = obj.file and obj.file.name
        has_remote = obj.yandex_disk_path

        if not has_local and not has_remote:
            obj.transcript_status = "FAILED"
            obj.transcript_error = "Video missing (no local file and no Yandex Disk path)"
            obj.save(update_fields=["transcript_status", "transcript_error"])
            return

        obj.transcript_status = "PROCESSING"
        obj.transcript_error = ""
        obj.save(update_fields=["transcript_status", "transcript_error"])

    temp_video_path = None
    try:
        if has_local:
            video_path = obj.file.path
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Local file not found: {video_path}")
        else:
            # Download from Yandex Disk
            suffix = os.path.splitext(obj.yandex_disk_path)[1] or ".mp4"
            fd, temp_video_path = tempfile.mkstemp(suffix=suffix, prefix="transcribe_video_")
            os.close(fd)
            
            logger.info(f"Downloading video from Yandex Disk: {obj.yandex_disk_path} -> {temp_video_path}")
            download_file_from_yandex_disk(obj.yandex_disk_path, temp_video_path, log_context={"user_id": obj.user_id})
            video_path = temp_video_path

        text = transcribe_video_file(video_path)

        obj.transcript_text = text
        obj.transcript_status = "DONE"
        obj.transcript_updated_at = timezone.now()
        obj.save(update_fields=["transcript_text", "transcript_status", "transcript_updated_at"])
    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file {temp_video_path}: {e}")


def transcribe_pending_videos():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    videos = pick_videos_to_transcribe()
    if not videos.exists():
        logger.info("Нет видеовизиток для транскрибации.")
        return

    logger.info(f"Найдено {videos.count()} видеовизиток для транскрибации.")

    for video_obj in videos:
        logger.info(f"Транскрибация ScholarVideo ID: {video_obj.id} (user_id={video_obj.user_id}) ...")
        try:
            process_one(video_obj)
            logger.info(f"  -> OK ScholarVideo ID {video_obj.id}")
        except Exception as e:
            logger.error(f"  -> FAIL ScholarVideo ID {video_obj.id}: {e}")
            ScholarVideo.objects.filter(pk=video_obj.pk).update(
                transcript_status="FAILED",
                transcript_error=str(e)[:5000],
            )


def main():
    logger.info("Запуск фонового скрипта ScholarVideo Transcriber...")
    while True:
        try:
            transcribe_pending_videos()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)

        logger.info(f"Следующая проверка через {POLLING_INTERVAL} секунд...")
        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
