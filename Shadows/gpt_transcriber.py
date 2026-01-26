import logging
import os
import time
import tempfile
import subprocess

import django
from dotenv import load_dotenv
from django.db import transaction
from django.utils import timezone

from openai import OpenAI

import config

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Putevka.settings")
django.setup()

from review_by_tutor.models import Interview

logger = logging.getLogger(__name__)

OPENAI_API_KEY = config.GPT_TOKEN
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
POLLING_INTERVAL = int(os.getenv("INTERVIEW_TRANSCRIBE_POLLING_INTERVAL", 60))
BATCH_LIMIT = int(os.getenv("INTERVIEW_TRANSCRIBE_BATCH_LIMIT", 2))
LANGUAGE = os.getenv("INTERVIEW_TRANSCRIBE_LANGUAGE", "ru").strip() or None

client = OpenAI(api_key=OPENAI_API_KEY)


def _extract_audio(video_path: str, audio_path: str) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        audio_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def transcribe_video_file(video_path: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, "audio.mp3")
        _extract_audio(video_path, audio_path)

        with open(audio_path, "rb") as f:
            kwargs = {
                "model": OPENAI_TRANSCRIBE_MODEL,
                "file": f,
            }
            if LANGUAGE:
                kwargs["language"] = LANGUAGE

            result = client.audio.transcriptions.create(**kwargs)

    text = getattr(result, "text", None)
    if not text:
        text = str(result)
    return text


def pick_interviews_to_transcribe():
    return Interview.objects.filter(
        video__isnull=False
    ).exclude(video__exact="").filter(
        transcript_status__in=["PENDING", "FAILED"]
    ).order_by("updated_at")[:BATCH_LIMIT]


def process_one(interview: "Interview") -> None:
    with transaction.atomic():
        obj = Interview.objects.select_for_update().get(pk=interview.pk)
        if obj.transcript_status == "DONE":
            return
        if not obj.video:
            obj.transcript_status = "FAILED"
            obj.transcript_error = "Video missing"
            obj.save(update_fields=["transcript_status", "transcript_error"])
            return

        obj.transcript_status = "PROCESSING"
        obj.transcript_error = ""
        obj.save(update_fields=["transcript_status", "transcript_error"])

    video_path = obj.video.path
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    text = transcribe_video_file(video_path)

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
