from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

from core.models import MotivationLetter
from my_study.models import CourseSelection, UniversityPriority
from review_by_tutor.models import InterviewTemplate, TestAssignment
from scholar_form.models import ScholarVideo, UserInfo


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if hasattr(value, "strftime"):
        return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if hasattr(value, "tzinfo") else value.strftime("%d.%m.%Y")
    return str(value).strip()


def _join(items) -> str:
    return "\n".join(_text(item) for item in items if _text(item))


def _field(obj, name: str) -> str:
    if not obj:
        return ""
    display = getattr(obj, f"get_{name}_display", None)
    if callable(display):
        value = display()
        if value:
            return _text(value)
    return _text(getattr(obj, name, ""))


def _safe_set(ws, coord: str, value):
    cell = ws[coord]
    if isinstance(cell, MergedCell):
        for merged in ws.merged_cells.ranges:
            if coord in merged:
                cell = ws.cell(merged.min_row, merged.min_col)
                break
    cell.value = value or None


def _latest_completed_test(user):
    return (
        TestAssignment.objects
        .filter(user=user)
        .order_by("-completed_at", "-assigned_at", "-id")
        .first()
    )


def _template_path() -> Path:
    template = InterviewTemplate.objects.filter(is_active=True).order_by("-uploaded_at").first()
    if template and template.file:
        return Path(template.file.path)

    root_template = Path(settings.BASE_DIR) / "Шаблон 2025.xlsx"
    if root_template.exists():
        return root_template

    raise FileNotFoundError("Interview XLSX template not found")


def _build_application_values(user, interview, result) -> dict[str, str]:
    info = UserInfo.objects.filter(user=user).first()
    letter = MotivationLetter.objects.filter(user=user).first()
    rubric = getattr(letter, "rubric_review", None) if letter else None
    video = ScholarVideo.objects.filter(user=user).first()
    test = _latest_completed_test(user)

    planned_exams = ""
    if info:
        planned_exams = _join(info.planned_exams.values_list("name", flat=True))

    universities = _join(
        f"{u.priority}. {u.university}{', ' + u.city if u.city else ''}{' - ' + u.specialty if u.specialty else ''}"
        for u in UniversityPriority.objects.filter(user=user).order_by("priority")
    )
    courses = _join(
        f"{s.course.school.name}: {s.course.title} ({s.course.subject.name})"
        for s in CourseSelection.objects.select_related("course__school", "course__subject").filter(user=user)
    )

    full_name = _join([_field(info, "last_name"), _field(info, "first_name"), _field(info, "middle_name")])
    if not full_name:
        full_name = user.get_full_name() or user.username

    one_parent_not_working = "Да" if info and info.is_single_parent_family else ""
    both_parents_not_working = ""

    return {
        "ФИО": full_name.replace("\n", " "),
        "Дата_рождения": _field(info, "birth_date"),
        "Телефон": _field(info, "phone") or getattr(user, "email", ""),
        "Email": _field(info, "email") or user.email,
        "Город_область_регион": _join([_field(info, "region"), _field(info, "city")]),
        "Наименование_и_номер_школы": _field(info, "school_name"),
        "В какой класс ты пойдешь в следующем году?": _field(info, "next_year_class_digit"),
        "Профиль_класса_при_наличии": _field(info, "class_profile"),
        "Предметы_по_которым_планируешь_сдавать_ЕГЭ": planned_exams,
        "Средний_балл_за_последний_учебный_год_по_предметам": _field(info, "subject_grades") or _field(info, "avg_grade_last_period"),
        "Планируешь_ли_ты_участвовать_в_олимпиадах": _field(info, "olympiad_plans"),
        "Ты_планируешь_поступать_по_ЕГЭ_или_олимпиадам_": _field(info, "admission_path"),
        "Список_наиболее_приоритетных_ВУЗов_в_которые_планируешь_поступать_не_более_5": universities or _field(info, "target_universities"),
        "Список_специальностей_которые_рассматриваешь_для_поступления": _field(info, "specializations"),
        "Мать": _field(info, "mother"),
        "Отец": _field(info, "father"),
        "Иной_законный_представитель": _field(info, "legal_guardian"),
        "Количество_братьев_и_сестёр": _field(info, "siblings_count"),
        "Братья_и_сёстры": _field(info, "siblings_info"),
        "Количественный_состав_семьи_": _field(info, "family_size"),
        "Среднемесячный_доход_на_1_члена_семьи_за_последние_12_месяцев_руб_": _field(info, "income_per_member"),
        "Имеет_ли_семья_статус_малоимущей": _field(info, "is_low_income"),
        "Получает_ли_семья_субсидии_от_государства_": _field(info, "receives_subsidy"),
        "Есть_какие-либо_иные_обстоятельства_о_которых_ты_хотел-a_бы_сообщить": _join([_field(info, "other_factors"), _field(info, "life_situation_notes")]),
        "Есть_ли_у_тебя_дома_компьютер_с_доступом_в_интернет": _field(info, "has_pc_with_internet"),
        "Кратко_опиши_свои_достижения_за_последние_два_года": _field(info, "achievements"),
        "Как_ты_планируешь_свою_подготовку_к_поступлению_на_следующий_год_": _join([_field(info, "preparation_plan"), courses]),
        "Какую_помощь_ты_ожидаешь_от_Фонда": _field(info, "foundation_help"),
        "Как_ты_узнал_о_программе": _field(info, "heard_about_program"),
        "Гуманитарий": "Да" if _field(info, "internal_study_profile") == "Гуманитарий" else "",
        "Инвалидность ребенка": _field(info, "has_candidate_disability"),
        "Многодетная семья": _field(info, "is_large_family"),
        "Неполная семья": _field(info, "is_single_parent_family"),
        "Сирота / под опекой": _field(info, "is_orphan_or_under_guardianship"),
        "Один из родителей не работает": one_parent_not_working,
        "Оба родителя не работают": both_parents_not_working,
        "Родитель пенсионер / инвалид": _field(info, "is_parent_pensioner"),
        "Другое важное": _join([_field(info, "other_factors"), _field(info, "family_material_status")]),
        "Числовой (процентиль)": _field(test, "numeric_percentile"),
        "Числовой (грейд)": _field(test, "numeric_grade"),
        "Вербальный (процентиль)": _field(test, "verbal_percentile"),
        "Вербальный (грейд)": _field(test, "verbal_grade"),
        "Логический (процентиль)": _field(test, "logical_percentile"),
        "Логический (грейд)": _field(test, "logical_grade"),
        "Дата получения мотивационного письма": _field(letter, "submitted_at"),
        "Число слов": _field(rubric, "word_count") or (letter.word_count() if letter else ""),
        "Вопрос 2 (специальность)": _field(rubric, "specialty_choice_score"),
        "Вопрос 3 (ВУЗ)": _field(rubric, "university_choice_score"),
        "Вопрос 4 (текущая подготовка)": _field(rubric, "current_preparation_score"),
        "Вопрос 5 (подготовка в следующем году)": _field(rubric, "next_year_preparation_score"),
        "Вопрос 6 (значимость ВО)": _field(rubric, "higher_education_value_score"),
        "Вопрос 7 (критичность помощи)": _field(rubric, "support_criticality_score"),
        "Последовательность": _field(rubric, "composition_penalty"),
        "Точность и выразительность": _field(rubric, "style_penalty"),
        "Орфография": _field(rubric, "orthography_penalty"),
        "Пунктуация": _field(rubric, "syntax_penalty"),
        "Итоговый балл за мотивационное письмо": _field(rubric, "total_score") or _field(letter, "admin_score"),
        "Предварительная оценка мотивации": _field(rubric, "motivation"),
        "Предварительная оценка критичности": _field(rubric, "help_criticality"),
        "Олимпиадник": _field(rubric, "olympiads"),
        "Про олимпиады": _field(info, "olympiad_plans"),
        "Категория": _field(info, "internal_study_profile"),
        "Оценка амбиций": _field(rubric, "justification"),
        "Выписки из мотивационного письма": _join([
            _field(rubric, "specialty"),
            _field(rubric, "preferred_universities"),
            _field(rubric, "motivation"),
            _field(rubric, "help_criticality"),
        ]),
        "Вопросы на собеседование после мотписьма": _field(rubric, "reviewer_comment"),
        "Вопросы на собеседование от интервьюера": _join([_field(interview, "notes"), _field(video, "online_school_interview_questions"), _field(video, "schedule_interview_questions")]),
    }


INTERVIEW_RESULT_ROWS = {
    12: "school_number",
    13: "school_type",
    14: "school_distance_km",
    15: "school_specialization",
    16: "school_students_total",
    17: "school_left_after_9_est",
    18: "school_students_11",
    19: "class_profile",
    20: "has_ege_teachers_all",
    33: "triples_reason",
    34: "favorite_teacher",
    35: "favorite_subject",
    36: "has_computer_lab",
    37: "olympiads_frequency",
    38: "clubs_info",
    46: "olympiad_support_by_school",
    47: "other_school_notes",
    49: "aims_medal",
    50: "admission_way",
    51: "ege_subjects",
    63: "olympiad_experience",
    75: "other_support_needed",
    99: "had_tutor",
}


def build_prefilled_interview_xlsx(user, interview, result) -> bytes:
    workbook = load_workbook(_template_path())
    ws = workbook.active

    _safe_set(ws, "D6", user.get_full_name() or user.username)
    _safe_set(ws, "D8", "")
    _safe_set(ws, "D9", timezone.localdate().strftime("%d.%m.%Y"))

    values = _build_application_values(user, interview, result)
    for row in range(1, ws.max_row + 1):
        label = _text(ws[f"H{row}"].value)
        if label in values:
            _safe_set(ws, f"I{row}", values[label])

    if result:
        for row, field_name in INTERVIEW_RESULT_ROWS.items():
            _safe_set(ws, f"E{row}", _field(result, field_name))
        _safe_set(ws, "F255", _field(result, "interviewer_summary"))
        _safe_set(ws, "F256", _field(result, "interviewer_risks"))
        _safe_set(ws, "F257", _field(result, "interviewer_recommendations"))
        _safe_set(ws, "F258", _field(result, "interviewer_score"))

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
