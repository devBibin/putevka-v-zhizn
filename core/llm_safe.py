from __future__ import annotations
from typing import Literal, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field, ValidationError, constr
import json
import re
try:
    import bleach
    def _clean(s: str) -> str:
        return bleach.clean(s or "", tags=[], strip=True)
except Exception:
    def _clean(s: str) -> str:
        # минимальный «санитайз»: убираем управляющие и теги
        s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", s or "")
        s = re.sub(r"<[^>]+>", "", s)
        return s

ContentChoice = Literal["full", "partial", "none"]
RhetComp = Literal["good", "minor_issue", "major_issue"]
RhetStyle = Literal["good", "one_dimensional_or_imprecise", "poor"]
Ortho = Literal["none", "one_two", "three_plus"]
Syntax = Literal["none", "one", "two_plus"]

class Content(BaseModel):
    specialty_choice: ContentChoice
    university_choice: ContentChoice
    current_preparation: ContentChoice
    next_year_plan: ContentChoice
    higher_ed_value: ContentChoice
    support_criticality: ContentChoice

class Rhetoric(BaseModel):
    composition: RhetComp
    style_precision: RhetStyle

class Literacy(BaseModel):
    orthography: Ortho
    syntax: Syntax

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
        data = self.dict()
        data = {k: _clean((v or ""))[:2000] for k, v in data.items()}
        return Extractions(**data)

class RubricPayload(BaseModel):
    word_count: int = Field(ge=0)
    content: Content
    rhetoric: Rhetoric
    literacy: Literacy
    extractions: Extractions
    justification: constr(max_length=8000) = ""

    def sanitized(self) -> "RubricPayload":
        return RubricPayload(
            word_count=self.word_count,
            content=self.content,
            rhetoric=self.rhetoric,
            literacy=self.literacy,
            extractions=self.extractions.sanitized(),
            justification=_clean(self.justification or "")[:4000],
        )

CONTENT_POINTS = {"full": 10, "partial": 5, "none": 0}
COMPOSITION_PENALTY = {"good": 0, "minor_issue": -2, "major_issue": -5}
STYLE_PENALTY = {"good": 0, "one_dimensional_or_imprecise": -2, "poor": -5}
ORTHO_PENALTY = {"none": 0, "one_two": -2, "three_plus": -5}
SYNTAX_PENALTY = {"none": 0, "one": -2, "two_plus": -5}

def compute_score(p: RubricPayload) -> Tuple[int, str]:
    c = p.content
    base = (
        CONTENT_POINTS[c.specialty_choice] + CONTENT_POINTS[c.university_choice] +
        CONTENT_POINTS[c.current_preparation] + CONTENT_POINTS[c.next_year_plan] +
        CONTENT_POINTS[c.higher_ed_value] + CONTENT_POINTS[c.support_criticality]
    )
    penalties = (
        COMPOSITION_PENALTY[p.rhetoric.composition] +
        STYLE_PENALTY[p.rhetoric.style_precision] +
        ORTHO_PENALTY[p.literacy.orthography] +
        SYNTAX_PENALTY[p.literacy.syntax]
    )
    total = base + penalties

    wc = p.word_count
    if wc < 150:
        return 0, "Менее 150 слов — работа не засчитывается."
    if 150 <= wc <= 250 and total >= 60:
        total = 59
    if total < 0:
        total = 0
    return total, ""

def parse_llm_json(raw: str) -> Tuple[Optional[RubricPayload], Dict[str, Any]]:
    """
    Возвращает (payload|None, flags).
    flags: {"ok": bool, "error": "...", "warnings": [...]} — для сохранения в gpt_flags.
    """
    flags: Dict[str, Any] = {"ok": False, "warnings": []}
    try:
        data = json.loads(raw)
    except Exception as e:
        flags["error"] = f"JSON decode error: {e}"
        return None, flags

    # Жёсткая типизация + авто-санитайз:
    try:
        payload = RubricPayload(**data).sanitized()
        flags["ok"] = True
        # sanity: word_count разумный?
        if payload.word_count > 5000:
            flags["warnings"].append("word_count слишком велик — возможно, ошибка разбора.")
        return payload, flags
    except ValidationError as ve:
        flags["error"] = "Schema validation failed"
        flags["details"] = ve.errors()
        return None, flags
