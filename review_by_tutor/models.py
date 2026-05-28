from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone

User = get_user_model()
TEST_GRADE_CHOICES = (
    ("A", "A"),
    ("B", "B"),
    ("C", "C"),
    ("D", "D"),
    ("E", "E"),
)


class TestTemplate(models.Model):
    title = models.CharField("Название теста", max_length=200)
    external_url = models.URLField("Ссылка на прохождение", blank=True)
    instructions = models.TextField("Инструкции/Комментарий", blank=True)

    default_due_days = models.PositiveIntegerField(
        "Дедлайн (дней от назначения)",
        null=True, blank=True,
        help_text="Если задано, дедлайн посчитается как assigned_at + N дней",
    )

    is_active = models.BooleanField("Активен", default=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_test_templates",
        verbose_name="Создал",
    )
    created_at = models.DateTimeField("Создано", default=timezone.now)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Шаблон теста"
        verbose_name_plural = "Шаблоны тестов"

    def __str__(self):
        return self.title

class TestingInstruction(models.Model):
    is_active = models.BooleanField("Показывать плашку", default=True)

    title = models.CharField("Заголовок", max_length=120, default="Инструкция к тестированию")
    text = models.TextField("Текст", blank=True, default="Перед выполнением теста ознакомьтесь с инструкцией.")
    url = models.URLField("Ссылка на инструкцию", validators=[URLValidator()])

    button_text = models.CharField("Текст кнопки", max_length=60, default="Открыть инструкцию")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Инструкция к тестированию"
        verbose_name_plural = "Инструкция к тестированию"

    def __str__(self):
        return self.title

    @classmethod
    def get_current(cls):
        obj = cls.objects.filter(is_active=True).order_by("-updated_at").first()
        return obj

class TestAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Назначено"
        IN_PROGRESS = "in_progress", "В процессе"
        NEEDS_REVISION = "needs_revision", "На дописывание"
        COMPLETED = "completed", "Завершено"
        CANCELLED = "cancelled", "Отменено"

    template = models.ForeignKey(
        "TestTemplate",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="assignments",
        verbose_name="Шаблон",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="test_assignments",
        verbose_name="Кандидат",
    )
    title = models.CharField("Название теста", max_length=200)
    external_url = models.URLField("Ссылка на прохождение", blank=True)
    instructions = models.TextField("Инструкции/Комментарий", blank=True)

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="assigned_tests",
        verbose_name="Назначил",
    )
    assigned_at = models.DateTimeField("Назначено", default=timezone.now)
    due_at = models.DateTimeField("Дедлайн", null=True, blank=True)

    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.ASSIGNED,
        db_index=True,
    )

    score_a = models.DecimalField("Баллы A", max_digits=6, decimal_places=2, null=True, blank=True)
    score_b = models.DecimalField("Баллы B", max_digits=6, decimal_places=2, null=True, blank=True)
    score_c = models.DecimalField("Баллы C", max_digits=6, decimal_places=2, null=True, blank=True)

    percentile_a = models.DecimalField(
        "Перцентиль A",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Перцентиль по шкале A (0–100)",
    )

    percentile_b = models.DecimalField(
        "Перцентиль B",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Перцентиль по шкале B (0–100)",
    )

    percentile_c = models.DecimalField(
        "Перцентиль C",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Перцентиль по шкале C (0–100)",
    )

    result_text = models.TextField("Комментарий/результат", blank=True)
    passed = models.BooleanField("Пройдено успешно", null=True, blank=True)

    completed_at = models.DateTimeField("Завершено", null=True, blank=True)
    result_filled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="filled_test_results",
        verbose_name="Результат внёс",
    )
    result_filled_at = models.DateTimeField("Результат внесён", null=True, blank=True)

    revision_comment = models.TextField("Комментарий для дописывания", blank=True)
    revision_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="revision_requested_tests",
        verbose_name="Отправил на дописывание",
    )
    revision_at = models.DateTimeField("Отправлено на дописывание", null=True, blank=True)

    numeric_grade = models.CharField(
        "Грейд числового теста",
        max_length=1,
        choices=TEST_GRADE_CHOICES,
        blank=True,
        default="",
    )
    verbal_grade = models.CharField(
        "Грейд вербального теста",
        max_length=1,
        choices=TEST_GRADE_CHOICES,
        blank=True,
        default="",
    )
    logical_grade = models.CharField(
        "Грейд логического теста",
        max_length=1,
        choices=TEST_GRADE_CHOICES,
        blank=True,
        default="",
    )

    numeric_percentile = models.PositiveSmallIntegerField(
        "Перцентиль числового теста",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Значение от 1 до 99",
    )
    verbal_percentile = models.PositiveSmallIntegerField(
        "Перцентиль вербального теста",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Значение от 1 до 99",
    )
    logical_percentile = models.PositiveSmallIntegerField(
        "Перцентиль логического теста",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Значение от 1 до 99",
    )

    score_a = None
    score_b = None
    score_c = None
    result_score = None
    percentile = None
    percentile_a = None
    percentile_b = None
    percentile_c = None

    class Meta:
        ordering = ["-assigned_at", "-id"]
        verbose_name = "Тестирование кандидата"
        verbose_name_plural = "Тестирования кандидатов"
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.user}"

    def mark_completed(self):
        if not self.completed_at:
            self.completed_at = timezone.now()
        if self.status != self.Status.COMPLETED:
            self.status = self.Status.COMPLETED

    def mark_needs_revision(self, by_user: User, comment: str):
        self.status = self.Status.NEEDS_REVISION
        self.revision_by = by_user
        self.revision_at = timezone.now()
        self.revision_comment = (comment or "").strip()

        self.completed_at = None
        self.passed = None

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_at and not self.completed_at and timezone.now() > self.due_at)

    @property
    def on_time(self):
        if not self.due_at or not self.completed_at:
            return None
        return self.completed_at <= self.due_at

    @property
    def timing_label(self) -> str:
        if self.on_time is True:
            return "Успел"
        if self.on_time is False:
            return "Не успел"
        if self.is_overdue:
            return "Просрочено (ещё не сдано)"
        return "Не определено"


class InterviewPreparation(models.Model):
    title = models.CharField("Заголовок", max_length=200, default="Подготовка к собеседованию")
    description = models.TextField("Описание", blank=True)
    video = models.FileField("Видео", upload_to="interview_prep/")
    is_active = models.BooleanField("Показывать на сайте", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Материал по подготовке к собеседованию"
        verbose_name_plural = "Материалы по подготовке к собеседованию"

    def __str__(self):
        return self.title


class InterviewTemplate(models.Model):
    title = models.CharField(max_length=200, default="Шаблон интервью")
    file = models.FileField(upload_to="interview/templates/")
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class Interview(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="interview")
    notes = models.TextField("Заметки интервьюера", blank=True)

    class AiFillStatus(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        DONE = "DONE"
        FAILED = "FAILED"

    ai_fill_status = models.CharField(
        max_length=16,
        choices=AiFillStatus.choices,
        default=AiFillStatus.PENDING,
    )
    #TODO: удалить это поле
    filled_uploaded_at = models.DateTimeField(null=True, blank=True)
    ai_filled_at = models.DateTimeField(null=True, blank=True)
    ai_fill_error = models.TextField(blank=True)

    video = models.FileField(
        "Видео собеседования",
        upload_to="interview/video/",
        blank=True,
        null=True,
    )
    video_uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interview_video_uploaded",
    )
    video_uploaded_at = models.DateTimeField(null=True, blank=True)
    video_yandex_disk_url = models.TextField("Yandex Disk video link/path", blank=True)
    video_yandex_disk_path = models.CharField(max_length=1024, blank=True, default="")
    video_source_type = models.CharField(
        max_length=32,
        blank=True,
        default="",
        choices=[
            ("", "Local file"),
            ("yandex_disk_path", "Yandex Disk path"),
            ("yandex_public_url", "Yandex Disk public URL"),
        ],
    )
    video_name = models.CharField(max_length=255, blank=True, default="")
    video_size = models.PositiveBigIntegerField(null=True, blank=True)
    video_mime = models.CharField(max_length=127, blank=True, default="")
    video_link_error = models.TextField(blank=True, default="")
    video_link_checked_at = models.DateTimeField(null=True, blank=True)

    transcript = models.TextField("Транскрипт", blank=True)
    transcript_status = models.CharField(
        "Статус транскрибации",
        max_length=20,
        choices=[
            ("PENDING", "Ожидает"),
            ("PROCESSING", "В работе"),
            ("DONE", "Готово"),
            ("FAILED", "Ошибка"),
        ],
        default="PENDING",
    )
    transcript_error = models.TextField("Ошибка транскрибации", blank=True)
    transcript_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


from django.conf import settings
from django.db import models
from django.utils import timezone


from django.db import models
from django.utils import timezone

from review_by_tutor.models import Interview


class InterviewResult(models.Model):
    # ============================================================
    # META
    # ============================================================
    interview = models.OneToOneField(
        Interview,
        on_delete=models.CASCADE,
        related_name="result",
        null=True,
        verbose_name="Собеседование"
    )

    status = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Статус"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено"
    )

    # ============================================================
    # 1. ШКОЛА
    # ============================================================
    school_number = models.CharField(
        max_length=128, blank=True, default="", db_index=True,
        verbose_name="Школа (номер)"
    )

    school_type = models.CharField(
        max_length=128, blank=True, default="", db_index=True,
        verbose_name="Тип школы"
    )

    school_distance_km = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, db_index=True,
        verbose_name="Удалённость от дома (км)"
    )

    school_distance_minutes = models.PositiveIntegerField(
        null=True, blank=True, db_index=True,
        verbose_name="Время в пути до школы (мин)"
    )

    school_specialization = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Специализация школы"
    )

    school_students_total = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Общее количество учеников (оценочно)"
    )

    school_left_after_9_est = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Покинули школу после 9 класса (оценочно)"
    )

    school_students_11 = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Количество учеников в 11 классах"
    )

    class_profile = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Профиль класса"
    )

    has_ege_teachers_all = models.BooleanField(
        null=True, blank=True, db_index=True,
        verbose_name="Есть профильные учителя по всем предметам ЕГЭ"
    )

    teach_quality_ru = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — русский язык"
    )
    teach_quality_math = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — математика"
    )
    teach_quality_phys = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — физика"
    )
    teach_quality_chem = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — химия"
    )
    teach_quality_bio = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — биология"
    )
    teach_quality_inf = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — информатика"
    )
    teach_quality_geo = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — география"
    )
    teach_quality_soc = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — обществознание"
    )
    teach_quality_lit = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — литература"
    )
    teach_quality_hist = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — история"
    )
    teach_quality_lang = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Качество преподавания — иностранные языки"
    )

    triples_reason = models.TextField(
        blank=True, default="",
        verbose_name="Причины троек (если есть)"
    )

    favorite_teacher = models.TextField(
        blank=True, default="",
        verbose_name="Любимый преподаватель и почему"
    )

    favorite_subject = models.TextField(
        blank=True, default="",
        verbose_name="Любимый предмет и почему"
    )

    has_computer_lab = models.BooleanField(
        null=True, blank=True, db_index=True,
        verbose_name="Есть оборудованный компьютерный класс"
    )

    olympiads_frequency = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="Как часто проводятся олимпиады"
    )

    clubs_info = models.TextField(
        blank=True, default="",
        verbose_name="Кружки и внеурочные активности"
    )

    olympiad_support_by_school = models.TextField(
        blank=True, default="",
        verbose_name="Поддержка олимпиадного движения в школе"
    )

    other_school_notes = models.TextField(
        blank=True, default="",
        verbose_name="Другие сведения о школе"
    )

    # ============================================================
    # 2. ПОДГОТОВКА / ЕГЭ
    # ============================================================
    aims_medal = models.BooleanField(
        null=True, blank=True, db_index=True,
        verbose_name="Претендует на медаль / красный аттестат"
    )

    admission_way = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Планируемая траектория поступления",
        help_text="Существует несколько траекторий поступления, опиши ту, которую планируешь использовать сейчас"
    )

    ege_subjects = models.CharField(
        max_length=512, blank=True, default="", db_index=True,
        verbose_name="Планируемые предметы ЕГЭ"
    )

    mock_ru = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — русский")
    mock_math_base = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — математика (база)")
    mock_math_prof = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — математика (профиль)")
    mock_phys = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — физика")
    mock_chem = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — химия")
    mock_bio = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — биология")
    mock_inf = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — информатика")
    mock_geo = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — география")
    mock_soc = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — обществознание")
    mock_lit = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — литература")
    mock_hist = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — история")
    mock_lang = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Пробник ЕГЭ — иностранный язык")

    target_ru = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — русский")
    target_math_base = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — математика (база)")
    target_math_prof = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — математика (профиль)")
    target_phys = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — физика")
    target_chem = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — химия")
    target_bio = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — биология")
    target_inf = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — информатика")
    target_geo = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — география")
    target_soc = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — обществознание")
    target_lit = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — литература")
    target_hist = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — история")
    target_lang = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Целевой балл — иностранный язык")

    had_tutor = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Занимался с репетитором"
    )

    tutor_details = models.TextField(
        blank=True, default="",
        verbose_name="Детали занятий с репетитором"
    )

    had_online_courses = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Занимался на онлайн-курсах"
    )

    online_courses_details = models.TextField(
        blank=True, default="",
        verbose_name="Детали онлайн-курсов"
    )

    olympiad_experience = models.TextField(
        blank=True, default="",
        verbose_name="Опыт участия в олимпиадах"
    )

    olympiads_planned = models.TextField(
        blank=True, default="",
        verbose_name="Планируемые олимпиады"
    )

    need_olympiad_prep = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Нужна подготовка к олимпиадам от фонда"
    )

    specialties = models.TextField(
        blank=True, default="",
        verbose_name="Рассматриваемые специальности"
    )

    need_career_guidance = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Нужна помощь с профориентацией"
    )

    universities = models.TextField(
        blank=True, default="",
        verbose_name="Рассматриваемые вузы"
    )

    need_university_help = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Нужна помощь с выбором вуза"
    )

    why_higher_education = models.TextField(
        blank=True, default="",
        verbose_name="Зачем нужно высшее образование"
    )

    prep_9_10 = models.TextField(
        blank=True, default="",
        verbose_name="Как проходила подготовка в 9–10 классах"
    )

    prep_10_11 = models.TextField(
        blank=True, default="",
        verbose_name="План подготовки в 10–11 классах"
    )

    ready_to_move = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Готовность к переезду"
    )

    discussed_with_parents = models.TextField(
        blank=True, default="",
        verbose_name="Обсуждение поступления с родителями"
    )

    other_support_needed = models.TextField(
        blank=True, default="",
        verbose_name="Другая необходимая поддержка"
    )

    # ============================================================
    # 3. СОСТАВ СЕМЬИ
    # ============================================================
    family_structure = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Состав семьи"
    )

    family_many_children = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Многодетная семья"
    )

    family_people_count = models.PositiveIntegerField(
        null=True, blank=True, db_index=True,
        verbose_name="Количество человек в семье"
    )

    siblings_info = models.TextField(
        blank=True, default="",
        verbose_name="Братья и сёстры"
    )

    grandparents_info = models.TextField(
        blank=True, default="",
        verbose_name="Бабушки и дедушки"
    )

    dependents_info = models.TextField(
        blank=True, default="",
        verbose_name="Другие иждивенцы"
    )

    has_disabled_need_care = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Есть инвалиды, требующие ухода"
    )

    candidate_orphan = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Кандидат — сирота"
    )

    candidate_disabled = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Кандидат — инвалид"
    )

    breadwinner_loss = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        verbose_name="Потеря кормильца"
    )

    family_other_circumstances = models.TextField(
        blank=True, default="",
        verbose_name="Другие обстоятельства семьи"
    )

    # ============================================================
    # 4. РАБОТА / ДОХОД
    # ============================================================
    mother_job = models.TextField(blank=True, default="", verbose_name="Работа матери")
    mother_has_he = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="У матери есть высшее образование")

    father_job = models.TextField(blank=True, default="", verbose_name="Работа отца")
    father_has_he = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="У отца есть высшее образование")

    step_parent_job = models.TextField(blank=True, default="", verbose_name="Работа отчима / мачехи")
    step_parent_has_he = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="У отчима / мачехи есть высшее образование")

    parents_self_employed_details = models.TextField(blank=True, default="", verbose_name="Самозанятость / ИП родителей")
    other_relatives_jobs = models.TextField(blank=True, default="", verbose_name="Работа других родственников")

    parent_on_pension_or_care = models.TextField(blank=True, default="", verbose_name="Родитель на пенсии / уходе")
    why_parent_not_working = models.TextField(blank=True, default="", verbose_name="Причина отсутствия работы у родителя")

    alimony_paid = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Выплачиваются ли алименты")
    benefits_received = models.TextField(blank=True, default="", verbose_name="Получаемые выплаты / пособия")
    low_income_recognized = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Семья признана малоимущей")

    family_other_notes = models.TextField(blank=True, default="", verbose_name="Другие сведения о семье")
    parents_involved_in_study = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Участие родителей в учёбе")
    siblings_interfere_study = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Мешают ли младшие братья/сёстры учёбе")
    household_load = models.TextField(blank=True, default="", verbose_name="Нагрузка по дому")

    # ============================================================
    # 5. УСЛОВИЯ ПРОЖИВАНИЯ
    # ============================================================
    settlement_status = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Тип населённого пункта")
    distance_to_reg_center_km = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, db_index=True, verbose_name="Удалённость от регионального центра (км)")

    housing_type = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Тип жилья")
    utilities = models.TextField(blank=True, default="", verbose_name="Наличие коммуникаций")

    own_room = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие собственной комнаты")
    own_workdesk = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие собственного рабочего стола")

    own_computer = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие компьютера / ноутбука")
    own_phone = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие личного телефона")
    supports_whatsapp_telegram = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Поддерживает ли устройство WhatsApp / Telegram")

    has_printer = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие принтера")
    home_internet = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Интернет дома")
    phone_internet = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Интернет на телефоне")

    family_has_car = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Есть ли автомобиль в семье")
    relatives_in_big_cities = models.TextField(blank=True, default="", verbose_name="Родственники в крупных городах")
    pets = models.CharField(max_length=255, blank=True, default="", verbose_name="Домашние животные")

    has_bank_card = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Наличие банковской карты")
    summer_holidays = models.TextField(blank=True, default="", verbose_name="Как обычно проводит каникулы")
    financial_notes = models.TextField(blank=True, default="", verbose_name="Другие сведения о финансовом положении")

    # ============================================================
    # 6. ИНТЕРЕСЫ И ЛИЧНЫЕ КАЧЕСТВА
    # ============================================================
    weekday_routine = models.TextField(blank=True, default="", verbose_name="Как проходит обычный учебный день")
    weekend_routine = models.TextField(blank=True, default="", verbose_name="Как проходят выходные и каникулы")

    clubs_hobbies = models.TextField(blank=True, default="", verbose_name="Кружки и хобби")
    volunteering = models.TextField(blank=True, default="", verbose_name="Волонтёрская деятельность")

    gto_passed = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Сдавал ли нормы ГТО")
    sport_info = models.TextField(blank=True, default="", verbose_name="Занятия спортом")

    studies_extra_resources_frequency = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Частота использования дополнительных учебных ресурсов")
    self_study_example = models.TextField(blank=True, default="", verbose_name="Пример самостоятельного обучения")

    other_resources = models.TextField(blank=True, default="", verbose_name="Другие ресурсы для обучения")
    reads_books_frequency = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Как часто читает книги")
    favorite_book = models.TextField(blank=True, default="", verbose_name="Любимая книга")

    favorite_games = models.TextField(blank=True, default="", verbose_name="Любимые игры")
    favorite_movies = models.TextField(blank=True, default="", verbose_name="Любимые фильмы")
    favorite_socials = models.TextField(blank=True, default="", verbose_name="Любимые соцсети")

    friends_count_info = models.TextField(blank=True, default="", verbose_name="Друзья и круг общения")
    friends_admission_discussion = models.TextField(blank=True, default="", verbose_name="Обсуждение поступления с друзьями")

    part_time_job = models.TextField(blank=True, default="", verbose_name="Подработка")
    other_achievements = models.TextField(blank=True, default="", verbose_name="Другие достижения")

    success_qualities = models.TextField(blank=True, default="", verbose_name="Качества, помогающие добиваться успеха")
    success_definition = models.TextField(blank=True, default="", verbose_name="Что такое успех")

    unfinished_cases = models.TextField(blank=True, default="", verbose_name="Незавершённые дела и причины")
    asks_for_help_how = models.TextField(blank=True, default="", verbose_name="Как обращается за помощью")

    # ============================================================
    # 7. РАБОТА С ФОНДОМ
    # ============================================================
    heard_about_fund = models.TextField(blank=True, default="", verbose_name="Откуда узнал о фонде")
    parents_know_and_agree = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Родители знают и согласны")

    selection_experience = models.TextField(blank=True, default="", verbose_name="Опыт прохождения отбора")
    knows_support_program = models.TextField(blank=True, default="", verbose_name="Знание программы поддержки")
    most_useful_expected = models.TextField(blank=True, default="", verbose_name="Что представляется самым полезным")

    would_participate_without_stipend = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Участвовал бы без стипендии")

    understands_group_courses = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Понимание формата групповых курсов")
    knows_our_schools = models.TextField(blank=True, default="", verbose_name="Знание школ фонда")

    understands_homework_need = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Понимание необходимости домашних заданий")
    plan_to_combine = models.TextField(blank=True, default="", verbose_name="Как планирует совмещать обучение")

    ready_regular_contact = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Готовность к регулярному общению с фондом")
    will_inform_if_absent = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Обязуется информировать об отсутствии")

    preferred_contact_method = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Предпочтительный способ связи")
    ready_for_chats_webinars = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Готовность участвовать в чатах и вебинарах")

    interesting_topics = models.TextField(blank=True, default="", verbose_name="Интересные темы")
    ready_additional_tests = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Готовность сдавать дополнительные тесты")
    helpful_materials = models.TextField(blank=True, default="", verbose_name="Полезные материалы для подготовки")

    ready_tell_school = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Готов рассказать о программе в школе")
    ready_mentor_next = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Готов помогать следующим стипендиатам")

    fund_questions = models.TextField(blank=True, default="", verbose_name="Вопросы по программе")
    understands_next_steps = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="Понимание следующих шагов")

    # ============================================================
    # 8. ПРОЧЕЕ / ВЫВОДЫ
    # ============================================================
    other_notes = models.TextField(blank=True, default="", verbose_name="Прочие замечания")

    interviewer_summary = models.TextField(blank=True, default="", verbose_name="Сводка интервьюера")
    interviewer_risks = models.TextField(blank=True, default="", verbose_name="Риски")
    interviewer_recommendations = models.TextField(blank=True, default="", verbose_name="Рекомендации")
    interviewer_score = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Итоговая оценка интервьюера")

    class Meta:
        verbose_name = "Результат собеседования"
        verbose_name_plural = "Результаты собеседований"
        indexes = [
            models.Index(fields=["school_type"]),
            models.Index(fields=["class_profile"]),
            models.Index(fields=["admission_way"]),
            models.Index(fields=["ready_to_move"]),
            models.Index(fields=["family_structure"]),
            models.Index(fields=["low_income_recognized"]),
            models.Index(fields=["interviewer_score"]),
        ]
