import os
import logging
import subprocess
import tempfile
import time

from ai_service.openai_runtime import make_openai_client


logger = logging.getLogger(__name__)

OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
MAX_MODEL_AUDIO_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_MAX_SECONDS", "1400"))
CHUNK_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_SECONDS", "1100"))
CHUNK_OVERLAP_SECONDS = int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_OVERLAP_SECONDS", "2"))


def _run(cmd: list[str], error_prefix: str) -> str:
    started = time.monotonic()
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        logger.error("%s failed returncode=%s elapsed=%.2fs stderr=%s", error_prefix, proc.returncode, time.monotonic() - started, proc.stderr[-1000:])
        raise RuntimeError(f"{error_prefix} failed ({proc.returncode})\n{proc.stderr}")
    logger.debug("%s finished elapsed=%.2fs", error_prefix, time.monotonic() - started)
    return proc.stdout


def _probe_duration_seconds(media_path: str) -> float:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            media_path,
        ],
        "ffprobe",
    ).strip()
    return float(out)


def _extract_audio(video_path: str, audio_path: str, start_sec: int | None = None, duration_sec: int | None = None) -> None:
    cmd = ["ffmpeg", "-y"]
    if start_sec is not None:
        cmd += ["-ss", str(start_sec)]
    if duration_sec is not None:
        cmd += ["-t", str(duration_sec)]
    cmd += ["-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio_path]
    _run(cmd, "ffmpeg")


def _transcribe_audio_file(audio_path: str, language: str | None) -> str:
    client = make_openai_client()
    started = time.monotonic()
    size = os.path.getsize(audio_path)
    logger.info("OpenAI transcription request model=%s audio_bytes=%s language=%s", OPENAI_TRANSCRIBE_MODEL, size, language or "-")
    with open(audio_path, "rb") as fh:
        kwargs = {"model": OPENAI_TRANSCRIBE_MODEL, "file": fh}
        if language:
            kwargs["language"] = language
        result = client.audio.transcriptions.create(**kwargs)
    text = getattr(result, "text", None) or str(result)
    logger.info("OpenAI transcription response chars=%s elapsed=%.2fs", len(text), time.monotonic() - started)
    return text


def transcribe_media_file(media_path: str, language: str | None = "ru") -> str:
    started = time.monotonic()
    duration = _probe_duration_seconds(media_path)
    logger.info("Media duration probed file=%s duration=%.2fs", media_path, duration)
    if duration <= MAX_MODEL_AUDIO_SECONDS:
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "audio.wav")
            _extract_audio(media_path, audio_path)
            text = _transcribe_audio_file(audio_path, language)
            logger.info("Media transcription finished chunks=1 elapsed=%.2fs", time.monotonic() - started)
            return text

    parts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        step = max(1, CHUNK_SECONDS - CHUNK_OVERLAP_SECONDS)
        start = 0
        idx = 0
        total = int(duration) + 1
        while start < total:
            chunk_path = os.path.join(tmp, f"chunk_{idx:03d}.wav")
            chunk_duration = min(CHUNK_SECONDS, total - start)
            logger.info("Transcribing media chunk index=%s start=%s duration=%s", idx, start, chunk_duration)
            _extract_audio(media_path, chunk_path, start_sec=start, duration_sec=chunk_duration)
            text = _transcribe_audio_file(chunk_path, language).strip()
            hh = start // 3600
            mm = (start % 3600) // 60
            ss = start % 60
            parts.append(f"[{hh:02d}:{mm:02d}:{ss:02d}]\n{text}\n")
            idx += 1
            start += step
    result = "\n".join(parts).strip()
    logger.info("Media transcription finished chunks=%s chars=%s elapsed=%.2fs", idx, len(result), time.monotonic() - started)
    return result
