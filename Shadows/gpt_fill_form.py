import json
import logging
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

import django
from dotenv import load_dotenv
from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from openai import OpenAI

import httpx

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "Putevka.settings"))
django.setup()

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

from review_by_tutor.models import Interview, InterviewResult

PROXY = os.getenv("OPENAI_PROXY")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GPT_TOKEN")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

POLLING_INTERVAL = int(os.getenv("INTERVIEW_RESULT_FILL_POLLING_INTERVAL", "60"))
BATCH_LIMIT = int(os.getenv("INTERVIEW_RESULT_FILL_BATCH_LIMIT", "2"))

http_client = httpx.Client(
    proxy=PROXY if PROXY else None,
    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
    limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
    verify=True,
)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=http_client,
)

SKIP_FIELDS = {
    "id",
    "pk",
    "interview",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "status",
}

def _is_empty_value(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    return False

def _iter_fillable_model_fields() -> List[models.Field]:
    out: List[models.Field] = []
    for f in InterviewResult._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if getattr(f, "many_to_many", False):
            continue
        if getattr(f, "is_relation", False) and f.name != "interview":
            # OneToOne/ForeignKey кроме interview — если появятся, не трогаем
            continue

        if f.name in SKIP_FIELDS:
            continue

        out.append(f)
    return out

def build_llm_schema_from_model() -> Tuple[Dict[str, str], List[models.Field]]:
    fields = _iter_fillable_model_fields()

    schema: Dict[str, str] = {}
    for f in fields:
        # verbose_name иногда lazy — приводим к str
        vn = str(getattr(f, "verbose_name", f.name))
        itype = f.__class__.__name__
        schema[f.name] = f"{vn} (поле: {f.name}, тип: {itype})"

    return schema, fields


# ------------------------------------------------------------
# LLM + normalization
# ------------------------------------------------------------

SYSTEM_PROMPT = (
    "Ты — ассистент интервьюера. "
    "Тебе дан транскрипт собеседования и список полей модели (имя поля + описание). "
    "Верни ТОЛЬКО JSON-объект, где ключи — это имена полей модели (field_name), "
    "а значения — что записать в эти поля.\n\n"
    "Правила:\n"
    "1) Не выдумывай факты. Если информации нет — верни пустую строку.\n"
    "2) Коротко и по делу.\n"
    "3) Для булевых полей верни 'да'/'нет' или пусто.\n"
    "4) Для чисел верни число или пусто.\n"
)

def ask_openai_fill(fields_schema: Dict[str, str], transcript: str) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Поля модели (field_name -> описание):\n" + json.dumps(fields_schema, ensure_ascii=False)},
            {"role": "user", "content": "Транскрипт:\n" + transcript},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)

def _normalize_bool(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"да", "true", "истина", "1", "yes", "y"}:
        return True
    if s in {"нет", "false", "ложь", "0", "no", "n"}:
        return False
    return None

def _normalize_int(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s == "":
        return None
    digits = []
    sign = 1
    for ch in s:
        if ch == "-" and not digits:
            sign = -1
        elif ch.isdigit():
            digits.append(ch)
    if not digits:
        return None
    try:
        return sign * int("".join(digits))
    except Exception:
        return None

def _normalize_decimal(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    s = str(v).strip().replace(",", ".")
    if s == "":
        return None
    allowed = set("0123456789.-")
    s2 = "".join(ch for ch in s if ch in allowed)
    if s2 in {"", "-", ".", "-."}:
        return None
    try:
        return Decimal(s2)
    except InvalidOperation:
        return None

def _normalize_date(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        return v.date() if hasattr(v, "hour") else v
    s = str(v).strip()
    if s == "":
        return None
    d = parse_date(s)
    return d

def _normalize_datetime(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "year") and hasattr(v, "hour"):
        return v
    s = str(v).strip()
    if s == "":
        return None
    dt = parse_datetime(s)
    return dt

def normalize_value_for_field(field: models.Field, raw: Any) -> Any:
    if raw is None:
        return None

    if isinstance(raw, str) and raw.strip() == "":
        return ""

    if isinstance(field, models.BooleanField):
        b = _normalize_bool(raw)
        return b

    if isinstance(field, (models.IntegerField, models.PositiveIntegerField, models.BigIntegerField, models.SmallIntegerField)):
        return _normalize_int(raw)

    if isinstance(field, models.DecimalField):
        return _normalize_decimal(raw)

    if isinstance(field, models.DateField) and not isinstance(field, models.DateTimeField):
        return _normalize_date(raw)

    if isinstance(field, models.DateTimeField):
        return _normalize_datetime(raw)

    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False)

    return str(raw).strip()


def pick_interviews_to_fill(limit: int) -> models.QuerySet:
    return (
        Interview.objects.filter(
            transcript_status="DONE",
            ai_fill_status__in=["PENDING", "FAILED"],
        )
    )

def has_any_empty_fillable_fields(result_obj: InterviewResult, fillable_fields: List[models.Field]) -> bool:
    for f in fillable_fields:
        if _is_empty_value(getattr(result_obj, f.name, None)):
            return True
    return False

def apply_answers_to_result(
    result_obj: InterviewResult,
    fields: List[models.Field],
    answers: Dict[str, Any],
) -> List[str]:
    update_fields: List[str] = []

    for field in fields:
        name = field.name

        if name not in answers:
            continue

        old_val = getattr(result_obj, name, None)
        new_raw = answers.get(name)
        new_val = normalize_value_for_field(field, new_raw)

        if new_val is None:
            continue
        if isinstance(new_val, str) and not new_val.strip():
            continue

        if isinstance(field, (models.CharField, models.TextField)):
            if _is_empty_value(old_val):
                setattr(result_obj, name, new_val)
                update_fields.append(name)
            else:
                combined = f"Заметка куратора: {old_val.rstrip()}\n\nВариант нейронки: \n{new_val.strip()}"
                setattr(result_obj, name, combined)
                update_fields.append(name)

            continue

        if not _is_empty_value(old_val):
            continue

        setattr(result_obj, name, new_val)
        update_fields.append(name)

    return update_fields


from django.utils import timezone
from django.db import transaction

def process_one(interview_id: int) -> None:
    fields_schema, fillable_fields = build_llm_schema_from_model()

    with transaction.atomic():
        interview = Interview.objects.select_for_update().get(pk=interview_id)

        if not interview.transcript or not interview.transcript.strip():
            return

        result_obj, _ = InterviewResult.objects.get_or_create(interview=interview)

        if not has_any_empty_fillable_fields(result_obj, fillable_fields):
            if interview.ai_fill_status != Interview.AiFillStatus.DONE:
                interview.ai_fill_status = Interview.AiFillStatus.DONE
                interview.ai_filled_at = timezone.now()
                interview.ai_fill_error = ""
                interview.save(update_fields=["ai_fill_status", "ai_filled_at", "ai_fill_error"])
            return

        interview.ai_fill_status = Interview.AiFillStatus.PROCESSING
        interview.ai_fill_error = ""
        interview.save(update_fields=["ai_fill_status", "ai_fill_error"])

        transcript = interview.transcript.strip()

    try:
        answers = ask_openai_fill(fields_schema, transcript)
    except Exception as e:
        with transaction.atomic():
            interview = Interview.objects.select_for_update().get(pk=interview_id)
            interview.ai_fill_status = Interview.AiFillStatus.FAILED
            interview.ai_fill_error = str(e)
            interview.save(update_fields=["ai_fill_status", "ai_fill_error"])
        raise

    with transaction.atomic():
        interview = Interview.objects.select_for_update().get(pk=interview_id)
        result_obj, _ = InterviewResult.objects.get_or_create(interview=interview)

        update_fields = apply_answers_to_result(result_obj, fillable_fields, answers)
        if not update_fields:
            interview.ai_fill_status = Interview.AiFillStatus.FAILED
            interview.ai_fill_error = "LLM returned no applicable updates"
            interview.save(update_fields=["ai_fill_status", "ai_fill_error"])
            return

        result_obj.updated_at = timezone.now()
        update_fields.append("updated_at")
        result_obj.save(update_fields=update_fields)

        interview.ai_fill_status = Interview.AiFillStatus.DONE
        interview.ai_filled_at = timezone.now()
        interview.ai_fill_error = ""
        interview.save(update_fields=["ai_fill_status", "ai_filled_at", "ai_fill_error"])

def fill_pending_interviews():
    interviews = pick_interviews_to_fill(BATCH_LIMIT)
    if not interviews.exists():
        logger.info("Нет интервью для заполнения InterviewResult.")
        return

    logger.info(f"Найдено {interviews.count()} интервью для заполнения InterviewResult.")

    for it in interviews:
        logger.info(f"Заполнение InterviewResult для Interview ID {it.id} ...")
        try:
            process_one(it.id)
            logger.info(f"  -> OK Interview ID {it.id}")
        except Exception as e:
            logger.exception(f"  -> FAIL Interview ID {it.id}: {e}")


def main():
    logger.info("Запуск воркера InterviewResult filler...")
    while True:
        try:
            fill_pending_interviews()
        except Exception as e:
            logger.exception(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)

        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
