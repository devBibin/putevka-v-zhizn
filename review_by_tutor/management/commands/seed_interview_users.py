from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import MotivationLetter, MotivationLetterRubricReview
from my_study.models import Course, CourseSelection, School, Subject, UniversityPriority
from review_by_tutor.models import Interview, InterviewResult, TestAssignment
from scholar_form.models import ScholarVideo, UserInfo


class Command(BaseCommand):
    help = "Seed filled candidate users with linked interview data for local/container databases."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5, help="How many candidate users to create/update.")
        parser.add_argument("--prefix", default="seed", help="Username/email prefix.")
        parser.add_argument("--password", default="seed12345", help="Password for seeded users.")
        parser.add_argument("--staff", action="store_true", help="Also create/update a staff interviewer account.")

    @transaction.atomic
    def handle(self, *args, **options):
        count = max(1, options["count"])
        prefix = options["prefix"]
        password = options["password"]

        subjects = self._ensure_subjects()
        course = self._ensure_course(subjects["math"])

        if options["staff"]:
            self._ensure_staff(password)

        for index in range(1, count + 1):
            user = self._ensure_user(index, prefix, password)
            info = self._ensure_user_info(user, index, subjects)
            self._ensure_study(user, index, subjects, course)
            letter = self._ensure_letter(user, index)
            self._ensure_rubric(letter, index)
            self._ensure_test(user, index)
            self._ensure_video(user, index)
            interview = self._ensure_interview(user, index)
            self._ensure_interview_result(interview, info, index)

            self.stdout.write(self.style.SUCCESS(f"Seeded {user.email}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Seeded/updated {count} filled users."))
        self.stdout.write(f"Password for seeded users: {password}")

    def _ensure_subjects(self):
        data = {
            "math": ("Математика", "math"),
            "russian": ("Русский язык", "russian"),
            "physics": ("Физика", "physics"),
            "informatics": ("Информатика", "informatics"),
            "social": ("Обществознание", "social"),
        }
        result = {}
        for key, (name, slug) in data.items():
            result[key], _ = Subject.objects.get_or_create(slug=slug, defaults={"name": name})
        return result

    def _ensure_course(self, subject):
        school, _ = School.objects.get_or_create(
            name="Онлайн-школа Путевка Seed",
            defaults={"description": "Тестовая школа для локального заполнения данных.", "website": "https://example.org"},
        )
        course, _ = Course.objects.get_or_create(
            school=school,
            title="Подготовка к ЕГЭ по математике",
            defaults={"subject": subject, "description": "Тестовый курс для демонстрации.", "link": "https://example.org/math"},
        )
        if course.subject_id != subject.id:
            course.subject = subject
            course.save(update_fields=["subject"])
        return course

    def _ensure_staff(self, password):
        User = get_user_model()
        staff, _ = User.objects.update_or_create(
            username="seed_interviewer",
            defaults={
                "email": "seed_interviewer@example.test",
                "first_name": "Ирина",
                "last_name": "Интервьюерова",
                "is_staff": True,
                "is_active": True,
            },
        )
        staff.set_password(password)
        staff.save(update_fields=["password", "is_staff", "is_active", "email", "first_name", "last_name"])

    def _ensure_user(self, index, prefix, password):
        User = get_user_model()
        username = f"{prefix}_candidate_{index:02d}"
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "email": f"{username}@example.test",
                "first_name": ["Анна", "Иван", "Мария", "Артем", "Софья"][(index - 1) % 5],
                "last_name": ["Сидорова", "Петров", "Кузнецова", "Иванов", "Смирнова"][(index - 1) % 5],
                "is_active": True,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password", "email", "first_name", "last_name", "is_active"])
        return user

    def _ensure_user_info(self, user, index, subjects):
        info, _ = UserInfo.objects.update_or_create(
            user=user,
            defaults={
                "form_status": UserInfo.FormStatus.SUBMITTED,
                "selection_step": UserInfo.SelectionStep.INTERVIEW_PREP,
                "status": "CANDIDATE",
                "last_name": user.last_name,
                "first_name": user.first_name,
                "middle_name": "Александровна" if index % 2 else "Сергеевич",
                "gender": "WOMAN" if index % 2 else "MAN",
                "birth_date": date(2008, min(index, 12), min(10 + index, 28)),
                "phone": f"+7 900 100-{index:02d}-{index:02d}",
                "email": user.email,
                "region": "Томская область" if index % 2 else "Новосибирская область",
                "city": "Томск" if index % 2 else "Бердск",
                "address": f"ул. Учебная, д. {index}",
                "school_name": f"МБОУ СОШ №{20 + index}",
                "school_address": f"Школьная улица, {index}",
                "class_teacher": "Елена Викторовна",
                "next_year_class_digit": 11,
                "class_profile": "физико-математический" if index % 2 else "информационно-технологический",
                "subject_grades": "Математика 5, русский язык 5, физика 4, информатика 5",
                "avg_grade_last_period": Decimal("4.70"),
                "olympiad_plans": "Планирует муниципальный этап по математике и информатике.",
                "admission_path": "ЕГЭ, дополнительно пробует олимпиады.",
                "target_universities": "ТГУ, ТПУ, НГУ",
                "specializations": "Прикладная математика, ИТ, инженерные направления",
                "mother": "Мать работает медсестрой, среднее специальное образование.",
                "father": "Отец водитель, помогает с подготовкой по математике.",
                "siblings_count": 2,
                "siblings_info": "Младшие брат и сестра учатся в школе.",
                "family_size": 5,
                "income_per_member": "18000",
                "is_low_income": "Да",
                "receives_subsidy": "Детские пособия, компенсация питания.",
                "other_factors": "Семье сложно оплачивать регулярные курсы и поездки на олимпиады.",
                "has_pc_with_internet": "Есть ноутбук, интернет нестабильный.",
                "vk": f"https://vk.com/id10000{index}",
                "achievements": "Призер школьной олимпиады, ведет проект по программированию.",
                "preparation_plan": "Самостоятельная подготовка, пробники раз в месяц, онлайн-курс по математике.",
                "foundation_help": "Нужны курсы, наставник и помощь с выбором вуза.",
                "heard_about_program": "От классного руководителя.",
                "willing_to_participate": "Да",
                "internal_study_profile": UserInfo.InternalStudyProfile.PHYS_MATH if index % 2 else UserInfo.InternalStudyProfile.IT,
                "is_large_family": True,
                "is_single_parent_family": index % 3 == 0,
                "has_candidate_disability": False,
                "is_orphan_or_under_guardianship": False,
                "has_breadwinner_loss": False,
                "has_relative_disability": index % 2 == 0,
                "is_parent_pensioner": index % 4 == 0,
                "settlement_type": UserInfo.SettlementType.MID_CITY,
                "life_situation_notes": "Высокая мотивация, но ограничены финансовые ресурсы семьи.",
            },
        )
        info.planned_exams.set([subjects["math"], subjects["russian"], subjects["physics"], subjects["informatics"]])
        return info

    def _ensure_study(self, user, index, subjects, course):
        CourseSelection.objects.update_or_create(
            user=user,
            course=course,
            defaults={"motivation": "Нужно подтянуть профильную математику до 85+.", "need_tutor": index % 2 == 0},
        )
        for priority, university in enumerate(["ТГУ", "НГУ", "ТПУ"], start=1):
            item, _ = UniversityPriority.objects.update_or_create(
                user=user,
                priority=priority,
                defaults={
                    "university": university,
                    "city": "Томск" if university != "НГУ" else "Новосибирск",
                    "specialty": "Прикладная математика и информатика",
                    "is_targeted": priority == 1 and index % 2 == 0,
                    "notes": "Основной приоритет" if priority == 1 else "",
                },
            )
            item.subjects.set([subjects["math"], subjects["russian"], subjects["informatics"]])

    def _ensure_letter(self, user, index):
        letter, _ = MotivationLetter.objects.update_or_create(
            user=user,
            defaults={
                "letter_text": (
                    "Я хочу поступить на направление, связанное с математикой и программированием. "
                    "Сейчас готовлюсь самостоятельно, решаю варианты ЕГЭ и участвую в олимпиадах. "
                    "Поддержка фонда поможет мне системно заниматься с преподавателями, выбрать вуз "
                    "и не отказываться от подготовки из-за финансовых ограничений семьи. "
                ) * 8,
                "status": MotivationLetter.Status.SUBMITTED,
                "submitted_at": timezone.now() - timedelta(days=10 + index),
                "is_done": True,
                "admin_score": 58 + index,
                "admin_rating": "Хорошая мотивация, конкретный профиль, нужна проверка реалистичности плана.",
            },
        )
        return letter

    def _ensure_rubric(self, letter, index):
        MotivationLetterRubricReview.objects.update_or_create(
            letter=letter,
            defaults={
                "model_name": "seed",
                "schema_version": "seed-2026",
                "char_count": len(letter.letter_text),
                "word_count": letter.word_count(),
                "specialty_choice_score": "10",
                "university_choice_score": "10",
                "current_preparation_score": "10",
                "admission_trajectory_score": "10",
                "next_year_preparation_score": "10",
                "higher_education_value_score": "10",
                "support_criticality_score": "10",
                "composition_penalty": "0",
                "style_penalty": "-2" if index % 2 else "0",
                "orthography_penalty": "0",
                "syntax_penalty": "0",
                "suspected_ai_generated": False,
                "returned_for_revision": False,
                "reviewer_comment": "Уточнить, какие олимпиады уже писал и какой график подготовки выдержит.",
                "family": "Многодетная семья, доход ограничен.",
                "hobbies": "Программирование, волонтерство, школьные проекты.",
                "achievements": "Призовые места на школьном уровне.",
                "traits": "Самостоятельность, настойчивость.",
                "school_teachers": "Хороший контакт с учителем математики.",
                "prep_subjects": "Математика, русский язык, информатика.",
                "specialty": "ИТ и прикладная математика.",
                "preferred_universities": "ТГУ, НГУ, ТПУ.",
                "olympiads": "Есть школьный опыт, хочет попробовать региональный этап.",
                "motivation": "Мотивация высокая, цель сформулирована.",
                "help_criticality": "Без поддержки семье сложно оплатить подготовку.",
                "extra": "Нужно обсудить нагрузку и стабильность интернета.",
                "justification": "Кандидат демонстрирует реалистичный профиль и высокий потенциал.",
            },
        )

    def _ensure_test(self, user, index):
        test, _ = TestAssignment.objects.update_or_create(
            user=user,
            title="Seed тестирование способностей",
            defaults={
                "instructions": "Тестовая запись для проверки карточки интервью.",
                "assigned_at": timezone.now() - timedelta(days=8),
                "due_at": timezone.now() - timedelta(days=1),
                "status": TestAssignment.Status.COMPLETED,
                "numeric_grade": ["A", "B", "C"][index % 3],
                "numeric_percentile": min(99, 70 + index),
                "verbal_grade": ["B", "A", "C"][index % 3],
                "verbal_percentile": min(99, 65 + index),
                "logical_grade": ["A", "B", "A"][index % 3],
                "logical_percentile": min(99, 75 + index),
                "result_text": "Сильная логика, средний вербальный блок, рекомендована профильная подготовка.",
                "passed": True,
                "completed_at": timezone.now() - timedelta(days=2),
                "result_filled_at": timezone.now() - timedelta(days=2),
            },
        )
        return test

    def _ensure_video(self, user, index):
        ScholarVideo.objects.update_or_create(
            user=user,
            defaults={
                "review": "Говорит спокойно, мотивация выглядит устойчивой.",
                "score": 8 + index % 3,
                "transcript_text": "Кандидат рассказал о целях, семье, школе и подготовке к поступлению.",
                "transcript_status": "DONE",
                "transcript_updated_at": timezone.now() - timedelta(days=3),
                "online_school_prior_experience": "Раньше занимался на бесплатных вебинарах.",
                "online_school_selected_courses": "Математика профиль, информатика.",
                "online_school_choice_reason": "Нужна структура и регулярная проверка домашних заданий.",
                "online_school_interview_questions": "Готов ли выполнять домашние задания каждую неделю?",
                "schedule_school_day": "Школа до 15:00, затем домашние задания.",
                "schedule_homework_time": "2-3 часа в день.",
                "schedule_exam_prep_time": "1 час в будни, 3 часа в выходные.",
                "schedule_interview_questions": "Как будет совмещать курсы, школу и олимпиады?",
            },
        )

    def _ensure_interview(self, user, index):
        interview, _ = Interview.objects.update_or_create(
            user=user,
            defaults={
                "notes": "Перед собеседованием уточнить расписание, поддержку семьи и готовность к регулярным курсам.",
                "transcript": "Тестовая транскрипция интервью для проверки выгрузки.",
                "transcript_status": "DONE",
                "transcript_updated_at": timezone.now() - timedelta(days=1),
                "ai_fill_status": Interview.AiFillStatus.DONE,
                "ai_filled_at": timezone.now() - timedelta(days=1),
            },
        )
        return interview

    def _ensure_interview_result(self, interview, info, index):
        InterviewResult.objects.update_or_create(
            interview=interview,
            defaults={
                "school_number": info.school_name,
                "school_type": "обычная городская школа",
                "school_distance_km": Decimal("3.50"),
                "school_distance_minutes": 20,
                "school_specialization": info.class_profile,
                "school_students_total": 650,
                "school_left_after_9_est": 35,
                "school_students_11": 48,
                "class_profile": info.class_profile,
                "has_ege_teachers_all": True,
                "teach_quality_ru": "хорошее",
                "teach_quality_math": "сильное",
                "triples_reason": "Троек нет, иногда проседает из-за нагрузки.",
                "favorite_teacher": "Учитель математики, потому что дает дополнительные задачи.",
                "favorite_subject": "Математика и информатика.",
                "has_computer_lab": True,
                "olympiads_frequency": "Проводятся школьные этапы, региональный уровень редко.",
                "clubs_info": "Есть спортивные и творческие кружки, профильных ИТ мало.",
                "olympiad_support_by_school": "Учителя предлагают участие, но готовят нерегулярно.",
                "other_school_notes": "Школа поддерживает кандидата рекомендательным письмом.",
                "aims_medal": True,
                "admission_way": "ЕГЭ плюс олимпиады как дополнительная возможность.",
                "ege_subjects": "Русский язык, профильная математика, информатика.",
                "mock_ru": "82",
                "mock_math_prof": "76",
                "mock_inf": "80",
                "target_ru": "90",
                "target_math_prof": "85",
                "target_inf": "88",
                "had_tutor": "Нет, платные занятия недоступны.",
                "tutor_details": "Разовые консультации у школьного учителя.",
                "had_online_courses": "Да, бесплатные интенсивы.",
                "online_courses_details": "Записи вебинаров и открытые варианты.",
                "olympiad_experience": "Школьный этап, призер по математике.",
                "olympiads_planned": "Математика, информатика.",
                "need_olympiad_prep": "Да",
                "specialties": info.specializations,
                "need_career_guidance": "Да",
                "universities": info.target_universities,
                "need_university_help": "Да",
                "why_higher_education": "Хочет получить профессию в ИТ и помогать семье.",
                "ready_to_move": "Да, если будет общежитие и поддержка.",
                "discussed_with_parents": "Да, родители поддерживают.",
                "other_support_needed": "Нужна помощь с курсами и планом подготовки.",
                "family_structure": "Родители и трое детей.",
                "family_many_children": "Да",
                "family_people_count": 5,
                "siblings_info": info.siblings_info,
                "family_other_circumstances": info.other_factors,
                "mother_job": info.mother,
                "father_job": info.father,
                "benefits_received": info.receives_subsidy,
                "low_income_recognized": info.is_low_income,
                "family_other_notes": info.life_situation_notes,
                "settlement_status": "Средний город",
                "housing_type": "Квартира",
                "own_computer": "Есть ноутбук",
                "home_internet": "Нестабильный",
                "financial_notes": "Семья экономит на дополнительном образовании.",
                "weekday_routine": "Школа, домашние задания, самостоятельная подготовка.",
                "clubs_hobbies": "Программирование, чтение, волонтерство.",
                "other_achievements": info.achievements,
                "success_qualities": "Настойчивость и умение просить обратную связь.",
                "heard_about_fund": info.heard_about_program,
                "parents_know_and_agree": "Да",
                "most_useful_expected": info.foundation_help,
                "would_participate_without_stipend": "Да",
                "preferred_contact_method": "Telegram",
                "fund_questions": "Как устроены занятия и отчетность?",
                "understands_next_steps": "Да",
                "other_notes": "Тестовая запись заполнена сидом.",
                "interviewer_summary": "Кандидат мотивирован, профиль подходит программе.",
                "interviewer_risks": "Риск перегруза и нестабильного интернета.",
                "interviewer_recommendations": "Рекомендовать поддержку по математике и информатике.",
                "interviewer_score": 80 + index,
            },
        )
