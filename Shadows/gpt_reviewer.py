import json
import logging
import os
import time
import django
from dotenv import load_dotenv
from django.db import models

from openai import OpenAI

import config

load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Putevka.settings')
django.setup()

logger = logging.getLogger(__name__)

from core.models import MotivationLetter

# Ключ можно брать из .env (OPENAI_API_KEY) или из config.GPT_TOKEN
OPENAI_API_KEY = config.GPT_TOKEN
OPENAI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=OPENAI_API_KEY)

POLLING_INTERVAL = int(os.getenv("SHADOW_POLLING_INTERVAL", 60))

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
                "support_criticality"
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
                "extra"
            ],
        },
        "justification": {"type": "string"},
    },
    "required": [
        "word_count",
        "content",
        "rhetoric",
        "literacy",
        "extractions",
        "justification"
    ],
}


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

CONTENT_POINTS = {"full": 10, "partial": 5, "none": 0}
COMPOSITION_PENALTY = {"good": 0, "minor_issue": -2, "major_issue": -5}
STYLE_PENALTY = {"good": 0, "one_dimensional_or_imprecise": -2, "poor": -5}
ORTHO_PENALTY = {"none": 0, "one_two": -2, "three_plus": -5}
SYNTAX_PENALTY = {"none": 0, "one": -2, "two_plus": -5}

def _score_from_json(j):
    c = j["content"]
    base = sum(CONTENT_POINTS[c[k]] for k in [
        "specialty_choice","university_choice","current_preparation",
        "next_year_plan","higher_ed_value","support_criticality"
    ])
    r = j["rhetoric"]; l = j["literacy"]
    penalties = (
        COMPOSITION_PENALTY[r["composition"]] +
        STYLE_PENALTY[r["style_precision"]] +
        ORTHO_PENALTY[l["orthography"]] +
        SYNTAX_PENALTY[l["syntax"]]
    )
    total = base + penalties
    wc = j["word_count"]

    if wc < 150:
        return 0, "Менее 150 слов — работа не засчитывается."

    if 150 <= wc <= 250 and total >= 60:
        total = 59

    if total < 0:
        total = 0

    return total, ""


def evaluate_with_openai(letter_text: str):
    """
    Версия на старом Chat Completions API:
    - client.chat.completions.create(...)
    - response_format со схемой, если доступно в SDK/модели
    - JSON парсится из message.content
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY/GPT_TOKEN не установлен.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_INSTRUCTIONS},
        {"role": "user", "content": f"Письмо:\n\n{letter_text}"},
    ]

    # Пытаемся использовать строгую схему (Structured Outputs в chat.completions)
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
        data = json.loads(raw)
    except Exception as e_schema:
        # Фолбэк: более совместимый json_object
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            data = json.loads(raw)
        except Exception as e_json_obj:
            # Последний фолбэк: без response_format, но с жёсткой инструкцией
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
            try:
                data = json.loads(raw)
            except Exception as e_plain:
                # Отладочная информация в логи и проброс исключения
                raise RuntimeError(
                    f"Не удалось разобрать JSON от модели. "
                    f"Ошибка schema: {e_schema}; json_object: {e_json_obj}; plain: {e_plain}; "
                    f"Сырой ответ: {raw[:500]}"
                )

    # На этом этапе data — это валидный dict по ожидаемой схеме
    score, note = _score_from_json(data)

    parts = []
    if note:
        parts.append(note)
    parts.append(
        f"Итог: {score}/60. Содержание: "
        f"{sum(CONTENT_POINTS[v] for v in data['content'].values())} баллов; "
        f"штрафы: "
        f"{COMPOSITION_PENALTY[data['rhetoric']['composition']]:+d}"
        f"{STYLE_PENALTY[data['rhetoric']['style_precision']]:+d}"
        f"{ORTHO_PENALTY[data['literacy']['orthography']]:+d}"
        f"{SYNTAX_PENALTY[data['literacy']['syntax']]:+d}. "
        f"Слов: {data['word_count']}."
    )
    summary = " ".join(parts)

    return {"json": data, "score": score, "summary": summary}

def review_unreviewed_letters():
    logger.info("Проверка непроанализированных писем...")

    letters_to_review = MotivationLetter.objects.filter(
        models.Q(gpt_review__isnull=True) | models.Q(gpt_review__exact=''),
        models.Q(admin_rating__isnull=True) | models.Q(admin_rating__exact=''),
        status=MotivationLetter.Status.SUBMITTED
    ).exclude(letter_text__exact='')

    if not letters_to_review.exists():
        logger.info("Нет писем, требующих анализа.")
        return

    logger.info(f"Найдено {letters_to_review.count()} писем для анализа.")

    for letter in letters_to_review:
        logger.info(f"Анализ письма ID: {letter.id} от пользователя: {letter.user.username[:20]}...")
        try:
            result = evaluate_with_openai(letter.letter_text)
        except Exception as e:
            logger.error(f"Ошибка генерации для письма {letter.id}: {e}")
            continue

        letter.gpt_review = result["summary"]

        if hasattr(letter, "gpt_score"):
            setattr(letter, "gpt_score", result["score"])
        if hasattr(letter, "gpt_word_count"):
            setattr(letter, "gpt_word_count", int(result["json"].get("word_count", 0)))
        if hasattr(letter, "gpt_json"):
            import json as _json
            try:
                setattr(letter, "gpt_json", result["json"])
            except Exception:
                setattr(letter, "gpt_json", _json.dumps(result["json"], ensure_ascii=False))

        letter.save(update_fields=[f for f in ["gpt_review","gpt_score","gpt_word_count","gpt_json","updated_at"]
                                   if hasattr(letter, f)])
        logger.info(f"  -> Оценка для письма ID {letter.id}: {result['score']}/60")

def main():
    logger.info("Запуск фонового скрипта GPT Reviewer...")
    while True:
        try:
            review_unreviewed_letters()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            time.sleep(30)
        logger.info(f"Следующая проверка через {POLLING_INTERVAL} секунд...")
        time.sleep(POLLING_INTERVAL)

if __name__ == "__main__":
    main()
