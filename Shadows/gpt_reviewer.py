import logging
import os
import time

import django
from dotenv import load_dotenv
from django.db import models, transaction
from openai import OpenAI

import config
from core.llm_safe import parse_llm_json

import httpx

PROXY = os.getenv("OPENAI_PROXY")

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Putevka.settings")
django.setup()

logger = logging.getLogger(__name__)

from core.models import MotivationLetter, MotivationLetterRubricReview

OPENAI_API_KEY = config.GPT_TOKEN
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
http_client = httpx.Client(
    proxy=PROXY if PROXY else None,
    timeout=httpx.Timeout(60.0, connect=30.0),
    verify=True,
)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=http_client,
)

POLLING_INTERVAL = int(os.getenv("SHADOW_POLLING_INTERVAL", 60))
BATCH_LIMIT = int(os.getenv("SHADOW_BATCH_LIMIT", 10))

RUBRIC_VERSION = "v1.0-2025-10-05"

SYSTEM_PROMPT = (
    "Ты — эксперт-проверяющий мотивационные письма фонда. "
    "Строго оцени письмо по рубрике и верни только JSON по заданной схеме."
)

USER_INSTRUCTIONS = (
    "Оцени по рубрике. Баллы: содержательные 6 пунктов full/partial/none → 10/5/0; "
    "речевое: composition 0/-2/-5, style_precision 0/-2/-5; "
    "грамотность: orthography 0/-2/-5, syntax 0/-2/-5. "
    "Если <150 слов — итог 0. Если 150–250 и получилось 60 — снизь до 59. "
    "В extractions выпиши тезисно сведения для профиля."
)

RUBRIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "word_count": {"type": "integer", "minimum": 0},
        "content": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "specialty_choice": {"type": "string", "enum": ["full", "partial", "none"]},
                "university_choice": {"type": "string", "enum": ["full", "partial", "none"]},
                "current_preparation": {"type": "string", "enum": ["full", "partial", "none"]},
                "next_year_plan": {"type": "string", "enum": ["full", "partial", "none"]},
                "higher_ed_value": {"type": "string", "enum": ["full", "partial", "none"]},
                "support_criticality": {"type": "string", "enum": ["full", "partial", "none"]},
            },
            "required": [
                "specialty_choice",
                "university_choice",
                "current_preparation",
                "next_year_plan",
                "higher_ed_value",
                "support_criticality",
            ],
        },
        "rhetoric": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "composition": {"type": "string", "enum": ["good", "minor_issue", "major_issue"]},
                "style_precision": {"type": "string", "enum": ["good", "one_dimensional_or_imprecise", "poor"]},
            },
            "required": ["composition", "style_precision"],
        },
        "literacy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "orthography": {"type": "string", "enum": ["none", "one_two", "three_plus"]},
                "syntax": {"type": "string", "enum": ["none", "one", "two_plus"]},
            },
            "required": ["orthography", "syntax"],
        },
        "extractions": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "family": {"type": "string"},
                "hobbies": {"type": "string"},
                "achievements": {"type": "string"},
                "traits": {"type": "string"},
                "school_teachers": {"type": "string"},
                "prep_subjects": {"type": "string"},
                "specialty": {"type": "string"},
                "preferred_universities": {"type": "string"},
                "relocation": {"type": "string"},
                "olympiads": {"type": "string"},
                "motivation": {"type": "string"},
                "help_criticality": {"type": "string"},
                "extra": {"type": "string"},
            },
            "required": [
                "family",
                "hobbies",
                "achievements",
                "traits",
                "school_teachers",
                "prep_subjects",
                "specialty",
                "preferred_universities",
                "relocation",
                "olympiads",
                "motivation",
                "help_criticality",
                "extra",
            ],
        },
        "justification": {"type": "string"},
    },
    "required": ["word_count", "content", "rhetoric", "literacy", "extractions", "justification"],
}

CONTENT_POINTS = {"full": 10, "partial": 5, "none": 0}
COMPOSITION_PENALTY = {"good": 0, "minor_issue": -2, "major_issue": -5}
STYLE_PENALTY = {"good": 0, "one_dimensional_or_imprecise": -2, "poor": -5}
ORTHO_PENALTY = {"none": 0, "one_two": -2, "three_plus": -5}
SYNTAX_PENALTY = {"none": 0, "one": -2, "two_plus": -5}


def _score_from_json(j: dict) -> tuple[int, str]:
    c = j["content"]
    base = sum(
        CONTENT_POINTS[c[k]]
        for k in [
            "specialty_choice",
            "university_choice",
            "current_preparation",
            "next_year_plan",
            "higher_ed_value",
            "support_criticality",
        ]
    )

    r = j["rhetoric"]
    l = j["literacy"]
    penalties = (
        COMPOSITION_PENALTY[r["composition"]]
        + STYLE_PENALTY[r["style_precision"]]
        + ORTHO_PENALTY[l["orthography"]]
        + SYNTAX_PENALTY[l["syntax"]]
    )

    total = base + penalties
    wc = int(j.get("word_count") or 0)

    if wc < 150:
        return 0, "Менее 150 слов — работа не засчитывается."

    if 150 <= wc <= 250 and total >= 60:
        total = 59

    if total < 0:
        total = 0

    return int(total), ""


def evaluate_with_openai(letter_text: str) -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_INSTRUCTIONS},
        {"role": "user", "content": f"Письмо:\n\n{letter_text}"},
    ]

    raw = None
    last_err = None

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "motivation_letter_scoring",
                    "schema": RUBRIC_SCHEMA,
                    "strict": True,
                },
            },
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        last_err = f"schema mode: {e}"

    if raw is None:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            last_err = f"{last_err} | json_object: {e}"

    if raw is None:
        strict_messages = [
            {"role": "system", "content": SYSTEM_PROMPT + " Верни ТОЛЬКО JSON по схеме, без текста вокруг."},
            {"role": "user", "content": USER_INSTRUCTIONS},
            {"role": "user", "content": f"Письмо:\n\n{letter_text}"},
        ]
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=strict_messages,
            temperature=0,
        )
        raw = resp.choices[0].message.content or ""

    payload, flags = parse_llm_json(raw)
    if not flags.get("ok"):
        short = (raw or "")[:500].replace("\n", " ")
        raise RuntimeError(f"LLM payload invalid: {flags.get('error')} | raw: {short}")

    if hasattr(payload, "dict"):
        j = payload.dict()
    else:
        j = payload

    score, note = _score_from_json(j)

    return {
        "json": j,
        "score": score,
        "note": note,
        "flags": flags,
        "model_name": OPENAI_MODEL,
        "rubric_version": RUBRIC_VERSION,
        "word_count": int(j.get("word_count") or 0),
    }


def _to_review_kwargs(j: dict, *, score: int, model_name: str, rubric_version: str) -> dict:
    c = j["content"]
    r = j["rhetoric"]
    l = j["literacy"]
    e = j["extractions"]

    return {
        "word_count": int(j.get("word_count") or 0),
        "total_score": int(score),
        "model_name": model_name or "",
        "schema_version": rubric_version or "",

        "specialty_choice": c["specialty_choice"],
        "university_choice": c["university_choice"],
        "current_preparation": c["current_preparation"],
        "next_year_plan": c["next_year_plan"],
        "higher_ed_value": c["higher_ed_value"],
        "support_criticality": c["support_criticality"],

        "composition": r["composition"],
        "style_precision": r["style_precision"],

        "orthography": l["orthography"],
        "syntax": l["syntax"],

        "family": e["family"],
        "hobbies": e["hobbies"],
        "achievements": e["achievements"],
        "traits": e["traits"],
        "school_teachers": e["school_teachers"],
        "prep_subjects": e["prep_subjects"],
        "specialty": e["specialty"],
        "preferred_universities": e["preferred_universities"],
        "relocation": e["relocation"],
        "olympiads": e["olympiads"],
        "motivation": e["motivation"],
        "help_criticality": e["help_criticality"],
        "extra": e["extra"],

        "justification": j.get("justification", "") or "",
    }


def review_unreviewed_letters():
    logger.info("Проверка непроанализированных писем (rubric_review)...")

    qs = (
        MotivationLetter.objects
        .filter(status=MotivationLetter.Status.SUBMITTED)
        .exclude(letter_text__exact="")
        .filter(
            models.Q(is_done=False),
        )
        .order_by("id")
    )[:BATCH_LIMIT]

    if not qs:
        logger.info("Нет писем, требующих анализа.")
        return

    logger.info(f"Найдено {len(qs)} писем для анализа.")

    for letter in qs:
        logger.info(f"Анализ письма ID: {letter.id} от пользователя: {letter.user.username[:20]}...")

        try:
            result = evaluate_with_openai(letter.letter_text)
            j = result["json"]
            score = result["score"]

            review_kwargs = _to_review_kwargs(
                j,
                score=score,
                model_name=result.get("model_name"),
                rubric_version=result.get("rubric_version"),
            )

            with transaction.atomic():
                letter_locked = (
                    MotivationLetter.objects
                    .select_for_update()
                    .get(pk=letter.pk)
                )

                MotivationLetterRubricReview.objects.update_or_create(
                    letter=letter_locked,
                    defaults=review_kwargs,
                )

                if not letter_locked.is_done:
                    letter_locked.is_done = True
                    letter_locked.save(update_fields=["is_done", "updated_at"])

            logger.info(f"  -> RubricReview сохранён для письма ID {letter.id}: {score}/60")

        except Exception as e:
            logger.error(f"Ошибка генерации для письма {letter.id}: {e}")
            continue


def main():
    logger.info("Запуск фонового скрипта GPT Rubric Reviewer...")
    while True:
        try:
            review_unreviewed_letters()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)

        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
