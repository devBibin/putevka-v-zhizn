import logging
import os
import time

import django
from django.db import models, transaction
from dotenv import load_dotenv
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
    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=300.0),
    limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
    verify=True,
)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=http_client,
)

POLLING_INTERVAL = int(os.getenv("SHADOW_POLLING_INTERVAL", 60))
BATCH_LIMIT = int(os.getenv("SHADOW_BATCH_LIMIT", 10))

RUBRIC_VERSION = "v3.0-2026-04-25"

SYSTEM_PROMPT = (
    "Ты — эксперт-проверяющий мотивационные письма фонда. "
    "Строго оцени письмо по рубрике и верни только JSON по заданной схеме."
)

USER_INSTRUCTIONS = """
Оцени мотивационное письмо строго по рубрике фонда.

ВАЖНО:
1. Важен объём в символах. Верни char_count и word_count.
2. Если в письме менее 1000 символов, итоговый балл = 0.
3. Если письмо выглядит как непосредственно написанное нейросетью, выставь suspected_ai_generated=true, итоговый балл = 0.
4. Если письмо объёмом от 1000 до 1500 символов и расчёт даёт 70 баллов, снизь итог до 69.
5. Оцени содержательные критерии так:
   - specialty_choice_score: только одно из "10", "5", "2", "0"
   - university_choice_score: только одно из "10", "5", "2", "0"
   - current_preparation_score: только одно из "10", "5", "0"
   - admission_trajectory_score: только одно из "10", "5", "2", "0"
   - next_year_preparation_score: только одно из "10", "5", "0"
   - higher_education_value_score: только одно из "10", "5", "0"
   - support_criticality_score: только одно из "10", "5", "0"
6. Речевые и грамотностные критерии — это штрафы:
   - composition_penalty: только одно из "0", "-2", "-5"
   - style_penalty: только одно из "0", "-2", "-5"
   - orthography_penalty: только одно из "0", "-2", "-5"
   - syntax_penalty: только одно из "0", "-2", "-5"
7. В flags:
   - suspected_ai_generated: true/false
   - returned_for_revision: true/false
8. В reviewer_comment дай короткий комментарий проверяющего.
9. В justification дай краткое, но содержательное пояснение оценки.
10. В extractions кратко выпиши сведения для профиля кандидата.

Верни только JSON, без пояснений вокруг.
""".strip()

RUBRIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "char_count": {"type": "integer", "minimum": 0},
        "word_count": {"type": "integer", "minimum": 0},
        "content": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "specialty_choice_score": {"type": "string", "enum": ["10", "5", "2", "0"]},
                "university_choice_score": {"type": "string", "enum": ["10", "5", "2", "0"]},
                "current_preparation_score": {"type": "string", "enum": ["10", "5", "0"]},
                "admission_trajectory_score": {"type": "string", "enum": ["10", "5", "2", "0"]},
                "next_year_preparation_score": {"type": "string", "enum": ["10", "5", "0"]},
                "higher_education_value_score": {"type": "string", "enum": ["10", "5", "0"]},
                "support_criticality_score": {"type": "string", "enum": ["10", "5", "0"]},
            },
            "required": [
                "specialty_choice_score",
                "university_choice_score",
                "current_preparation_score",
                "admission_trajectory_score",
                "next_year_preparation_score",
                "higher_education_value_score",
                "support_criticality_score",
            ],
        },
        "rhetoric": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "composition_penalty": {"type": "string", "enum": ["0", "-2", "-5"]},
                "style_penalty": {"type": "string", "enum": ["0", "-2", "-5"]},
            },
            "required": ["composition_penalty", "style_penalty"],
        },
        "literacy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "orthography_penalty": {"type": "string", "enum": ["0", "-2", "-5"]},
                "syntax_penalty": {"type": "string", "enum": ["0", "-2", "-5"]},
            },
            "required": ["orthography_penalty", "syntax_penalty"],
        },
        "flags": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "suspected_ai_generated": {"type": "boolean"},
                "returned_for_revision": {"type": "boolean"},
            },
            "required": ["suspected_ai_generated", "returned_for_revision"],
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
        "reviewer_comment": {"type": "string"},
        "justification": {"type": "string"},
    },
    "required": [
        "char_count",
        "word_count",
        "content",
        "rhetoric",
        "literacy",
        "flags",
        "extractions",
        "reviewer_comment",
        "justification",
    ],
}


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _raw_total_from_json(j: dict) -> int:
    c = j["content"]
    r = j["rhetoric"]
    l = j["literacy"]

    return (
        _safe_int(c["specialty_choice_score"])
        + _safe_int(c["university_choice_score"])
        + _safe_int(c["current_preparation_score"])
        + _safe_int(c["admission_trajectory_score"])
        + _safe_int(c["next_year_preparation_score"])
        + _safe_int(c["higher_education_value_score"])
        + _safe_int(c["support_criticality_score"])
        + _safe_int(r["composition_penalty"])
        + _safe_int(r["style_penalty"])
        + _safe_int(l["orthography_penalty"])
        + _safe_int(l["syntax_penalty"])
    )


def _score_from_json(j: dict) -> tuple[int, str]:
    c = j["content"]
    r = j["rhetoric"]
    l = j["literacy"]
    f = j["flags"]

    char_count = _safe_int(j.get("char_count"), 0)

    if bool(f.get("suspected_ai_generated")):
        return 0, "Есть признаки непосредственного написания письма нейросетью."

    if char_count < 1000:
        return 0, "Менее 1000 символов — работа не засчитывается."

    total = _raw_total_from_json(j)

    if 1000 <= char_count < 1500 and total >= 70:
        total = 69

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
                    "name": "motivation_letter_scoring_v3",
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
            {
                "role": "system",
                "content": SYSTEM_PROMPT + " Верни ТОЛЬКО JSON по схеме, без текста вокруг.",
            },
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
        dump_path = f"/tmp/ml_letter_invalid_{int(time.time())}.txt"
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(raw or "")
        raise RuntimeError(
            f"LLM payload invalid: {flags.get('error')} | raw saved to {dump_path}"
        )

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
        "word_count": _safe_int(j.get("word_count"), 0),
        "char_count": _safe_int(j.get("char_count"), 0),
        "suspected_ai_generated": bool(j.get("flags", {}).get("suspected_ai_generated")),
        "returned_for_revision": bool(j.get("flags", {}).get("returned_for_revision")),
    }


def _to_review_kwargs(j: dict, *, score: int, model_name: str, rubric_version: str) -> dict:
    c = j["content"]
    r = j["rhetoric"]
    l = j["literacy"]
    f = j["flags"]
    e = j["extractions"]

    char_count = _safe_int(j.get("char_count"), 0)

    return {
        "char_count": char_count,
        "word_count": _safe_int(j.get("word_count"), 0),
        "total_score": int(score),
        "model_name": model_name or "",
        "schema_version": rubric_version or "",

        "specialty_choice_score": c["specialty_choice_score"],
        "university_choice_score": c["university_choice_score"],
        "current_preparation_score": c["current_preparation_score"],
        "admission_trajectory_score": c["admission_trajectory_score"],
        "next_year_preparation_score": c["next_year_preparation_score"],
        "higher_education_value_score": c["higher_education_value_score"],
        "support_criticality_score": c["support_criticality_score"],

        "composition_penalty": r["composition_penalty"],
        "style_penalty": r["style_penalty"],

        "orthography_penalty": l["orthography_penalty"],
        "syntax_penalty": l["syntax_penalty"],

        "is_too_short": char_count < 1000,
        "score_capped_for_short_length": 1000 <= char_count < 1500 and _raw_total_from_json(j) >= 70,
        "suspected_ai_generated": bool(f.get("suspected_ai_generated")),
        "returned_for_revision": bool(f.get("returned_for_revision")),

        "reviewer_comment": j.get("reviewer_comment", "") or "",

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

            logger.info(
                "  -> RubricReview сохранён для письма ID %s: %s баллов (chars=%s, ai=%s)",
                letter.id,
                score,
                result.get("char_count"),
                result.get("suspected_ai_generated"),
            )

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
