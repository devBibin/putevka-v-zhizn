import json
import logging
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import models
from django.utils.dateparse import parse_date, parse_datetime

from ai_service.openai_runtime import make_openai_client


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты ассистент интервьюера. Тебе дан транскрипт собеседования и список полей модели. "
    "Верни только JSON-объект, где ключи это имена полей, а значения это данные для записи. "
    "Не выдумывай факты. Если информации нет, верни пустую строку."
)


def ask_openai_fill(fields_schema: dict[str, str], transcript: str) -> dict[str, Any]:
    client = make_openai_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    started = time.monotonic()
    logger.info("OpenAI fill request model=%s fields=%s transcript_chars=%s", model, len(fields_schema), len(transcript or ""))
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Поля модели:\n" + json.dumps(fields_schema, ensure_ascii=False)},
            {"role": "user", "content": "Транскрипт:\n" + transcript},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    answers = json.loads(raw)
    if isinstance(answers, dict) and isinstance(answers.get("answers"), dict):
        answers = answers["answers"]
    logger.info("OpenAI fill response chars=%s answer_fields=%s elapsed=%.2fs", len(raw), len(answers), time.monotonic() - started)
    return answers


def _is_empty_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _normalize_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"да", "true", "истина", "1", "yes", "y"}:
        return True
    if text in {"нет", "false", "ложь", "0", "no", "n"}:
        return False
    return None


def _normalize_int(value: Any) -> Any:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    digits = "".join(ch for ch in text if ch.isdigit())
    return sign * int(digits) if digits else None


def _normalize_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", ".")
    cleaned = "".join(ch for ch in text if ch in set("0123456789.-"))
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalize_value_for_field(field: models.Field, raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return ""
    if isinstance(field, models.BooleanField):
        return _normalize_bool(raw)
    if isinstance(field, (models.IntegerField, models.PositiveIntegerField, models.BigIntegerField, models.SmallIntegerField)):
        return _normalize_int(raw)
    if isinstance(field, models.DecimalField):
        return _normalize_decimal(raw)
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
        if field.name not in answers:
            continue
        old_value = getattr(result_obj, field.name, None)
        new_value = normalize_value_for_field(field, answers.get(field.name))
        if new_value is None or (isinstance(new_value, str) and not new_value.strip()):
            continue
        if isinstance(field, (models.CharField, models.TextField)):
            if _is_empty_value(old_value):
                setattr(result_obj, field.name, new_value)
            else:
                setattr(result_obj, field.name, f"Заметка куратора: {old_value.rstrip()}\n\nВариант нейронки:\n{new_value.strip()}")
            update_fields.append(field.name)
            continue
        if _is_empty_value(old_value):
            setattr(result_obj, field.name, new_value)
            update_fields.append(field.name)
    return update_fields
