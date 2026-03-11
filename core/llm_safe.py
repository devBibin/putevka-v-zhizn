from __future__ import annotations

import json
import re
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError, constr

try:
    import bleach

    def _clean(s: str) -> str:
        return bleach.clean(s or "", tags=[], strip=True)

except Exception:
    def _clean(s: str) -> str:
        s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", s or "")
        s = re.sub(r"<[^>]+>", "", s)
        return s


Content15 = Literal["15", "8", "3", "0"]
Content15Trajectory = Literal["15", "10", "5", "0"]
Content10 = Literal["10", "5", "0"]
Penalty = Literal["0", "-2", "-5"]


class Content(BaseModel):
    specialty_choice_score: Content15
    university_choice_score: Content15
    current_preparation_score: Content10
    admission_trajectory_score: Content15Trajectory
    next_year_preparation_score: Content10
    higher_education_value_score: Content10
    support_criticality_score: Content10


class Rhetoric(BaseModel):
    composition_penalty: Penalty
    style_penalty: Penalty


class Literacy(BaseModel):
    orthography_penalty: Penalty
    syntax_penalty: Penalty


class Flags(BaseModel):
    suspected_ai_generated: bool = False
    returned_for_revision: bool = False


class Extractions(BaseModel):
    family: str = ""
    hobbies: str = ""
    achievements: str = ""
    traits: str = ""
    school_teachers: str = ""
    prep_subjects: str = ""
    specialty: str = ""
    preferred_universities: str = ""
    relocation: str = ""
    olympiads: str = ""
    motivation: str = ""
    help_criticality: str = ""
    extra: str = ""

    def sanitized(self) -> "Extractions":
        data = self.model_dump()
        data = {k: _clean((v or ""))[:2000] for k, v in data.items()}
        return Extractions(**data)


class RubricPayload(BaseModel):
    char_count: int = Field(ge=0)
    word_count: int = Field(ge=0)

    content: Content
    rhetoric: Rhetoric
    literacy: Literacy
    flags: Flags
    extractions: Extractions

    reviewer_comment: constr(max_length=4000) = ""
    justification: constr(max_length=8000) = ""

    def sanitized(self) -> "RubricPayload":
        return RubricPayload(
            char_count=self.char_count,
            word_count=self.word_count,
            content=self.content,
            rhetoric=self.rhetoric,
            literacy=self.literacy,
            flags=self.flags,
            extractions=self.extractions.sanitized(),
            reviewer_comment=_clean(self.reviewer_comment or "")[:2000],
            justification=_clean(self.justification or "")[:4000],
        )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compute_score(p: RubricPayload) -> Tuple[int, str]:
    if p.flags.suspected_ai_generated:
        return 0, "Есть признаки непосредственного написания письма нейросетью."

    if p.char_count < 1000:
        return 0, "Менее 1000 символов — работа не засчитывается."

    total = 0

    total += _safe_int(p.content.specialty_choice_score)
    total += _safe_int(p.content.university_choice_score)
    total += _safe_int(p.content.current_preparation_score)
    total += _safe_int(p.content.admission_trajectory_score)
    total += _safe_int(p.content.next_year_preparation_score)
    total += _safe_int(p.content.higher_education_value_score)
    total += _safe_int(p.content.support_criticality_score)

    total += _safe_int(p.rhetoric.composition_penalty)
    total += _safe_int(p.rhetoric.style_penalty)

    total += _safe_int(p.literacy.orthography_penalty)
    total += _safe_int(p.literacy.syntax_penalty)

    if 1000 <= p.char_count < 1500 and total >= 85:
        total = 84

    if total < 0:
        total = 0

    return total, ""


def parse_llm_json(raw: str) -> Tuple[Optional[RubricPayload], Dict[str, Any]]:
    """
    Возвращает (payload|None, flags).

    flags:
    {
        "ok": bool,
        "error": "...",
        "details": [...],
        "warnings": [...]
    }
    """
    flags: Dict[str, Any] = {"ok": False, "warnings": []}

    try:
        data = json.loads(raw)
    except Exception as e:
        flags["error"] = f"JSON decode error: {e}"
        return None, flags

    try:
        payload = RubricPayload(**data).sanitized()
        flags["ok"] = True

        if payload.word_count > 10000:
            flags["warnings"].append("word_count слишком велик — возможно, ошибка разбора.")

        if payload.char_count > 50000:
            flags["warnings"].append("char_count слишком велик — возможно, ошибка разбора.")

        return payload, flags

    except ValidationError as ve:
        flags["error"] = "Schema validation failed"
        flags["details"] = ve.errors()
        return None, flags