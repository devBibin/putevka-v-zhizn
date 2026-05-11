import os
import logging
import time

from core.llm_safe import parse_llm_json

from ai_service.openai_runtime import make_openai_client


logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
RUBRIC_VERSION = "v3.0-2026-04-25"

SYSTEM_PROMPT = (
    "Ты эксперт, проверяющий мотивационные письма фонда. "
    "Строго оцени письмо по рубрике и верни только JSON по заданной схеме."
)

USER_INSTRUCTIONS = """
Оцени мотивационное письмо строго по рубрике фонда.

Правила:
1. Верни char_count и word_count.
2. Если письмо короче 1000 символов, итоговый балл равен 0.
3. Если письмо выглядит как непосредственно написанное нейросетью, suspected_ai_generated=true и итоговый балл равен 0.
4. Если письмо от 1000 до 1500 символов и расчет дает 70 баллов, снизить итог до 69.
5. Содержательные критерии: specialty_choice_score, university_choice_score, current_preparation_score,
   admission_trajectory_score, next_year_preparation_score, higher_education_value_score,
   support_criticality_score.
6. Штрафы: composition_penalty, style_penalty, orthography_penalty, syntax_penalty.
7. В flags верни suspected_ai_generated и returned_for_revision.
8. В reviewer_comment дай короткий комментарий проверяющего.
9. В justification дай краткое объяснение оценки.
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
                key: {"type": "string"}
                for key in [
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
                ]
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
    "required": ["char_count", "word_count", "content", "rhetoric", "literacy", "flags", "extractions", "reviewer_comment", "justification"],
}


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _raw_total(j: dict) -> int:
    return sum(
        _safe_int(value)
        for value in [
            *j["content"].values(),
            *j["rhetoric"].values(),
            *j["literacy"].values(),
        ]
    )


def _score(j: dict) -> int:
    if j["flags"].get("suspected_ai_generated") or _safe_int(j.get("char_count")) < 1000:
        return 0
    total = max(_raw_total(j), 0)
    if 1000 <= _safe_int(j.get("char_count")) < 1500 and total >= 70:
        return 69
    return total


def _review_kwargs(j: dict, score: int) -> dict:
    content = j["content"]
    rhetoric = j["rhetoric"]
    literacy = j["literacy"]
    flags = j["flags"]
    extractions = j["extractions"]
    char_count = _safe_int(j.get("char_count"))
    return {
        "char_count": char_count,
        "word_count": _safe_int(j.get("word_count")),
        "total_score": score,
        "model_name": OPENAI_MODEL,
        "schema_version": RUBRIC_VERSION,
        "is_too_short": char_count < 1000,
        "score_capped_for_short_length": 1000 <= char_count < 1500 and _raw_total(j) >= 70,
        "suspected_ai_generated": bool(flags.get("suspected_ai_generated")),
        "returned_for_revision": bool(flags.get("returned_for_revision")),
        "reviewer_comment": j.get("reviewer_comment", "") or "",
        "justification": j.get("justification", "") or "",
        **content,
        **rhetoric,
        **literacy,
        **extractions,
    }


def review_letter(letter_text: str) -> dict:
    client = make_openai_client()
    started = time.monotonic()
    logger.info("OpenAI review request model=%s rubric=%s text_chars=%s", OPENAI_MODEL, RUBRIC_VERSION, len(letter_text or ""))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_INSTRUCTIONS},
        {"role": "user", "content": f"Письмо:\n\n{letter_text}"},
    ]
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "motivation_letter_scoring_v3", "schema": RUBRIC_SCHEMA, "strict": True}},
    )
    raw = response.choices[0].message.content or ""
    logger.info("OpenAI review response chars=%s elapsed=%.2fs", len(raw), time.monotonic() - started)
    payload, flags = parse_llm_json(raw)
    if not flags.get("ok"):
        logger.warning("OpenAI review payload invalid error=%s", flags.get("error"))
        raise RuntimeError(f"LLM payload invalid: {flags.get('error')}")
    j = payload.model_dump()
    score = _score(j)
    logger.info("OpenAI review parsed score=%s suspected_ai=%s too_short=%s", score, j["flags"].get("suspected_ai_generated"), _safe_int(j.get("char_count")) < 1000)
    return {"review": _review_kwargs(j, score), "raw": j}
