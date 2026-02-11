import mimetypes
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

class StaffNote(models.Model):
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_notes")

    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="staff_notes_authored")

    text = models.TextField()

    is_favorite = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Заметка стаффа"
        verbose_name_plural = "Заметки стаффа"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_user", "-created_at"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Заметка по {self.target_user_id} | {self.text[:60]}"


class UserInfo(models.Model):
    GENDERS = [('MAN', 'Мужчина'), ('WOMAN', 'Женщина')]
    STATUSES = [('CANDIDATE', 'Кандидат'), ('ALTERNATIVE', 'Альтернативный трек'), ('FINAL STAGE', 'Финалист'), ('SCHOLAR', 'Участник'),
                ('ALUMNUS', 'Выпускник')]
    PROFILES = [
        ("humanities", "Гуманитарный профиль"),
        ("chem_bio", "Химико-биологический профиль"),
        ("technical", "Технический профиль"),
        ("creative", "Творческий профиль"),
    ]

    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True, verbose_name="Аватар")

    is_done = models.BooleanField(default=False, verbose_name='Анкета уже отправлена')

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, related_name='user_info')
    status = models.CharField(max_length=100, choices=STATUSES, default='CANDIDATE', verbose_name='Статус в программе')

    profile = models.CharField(max_length=100, choices=PROFILES, verbose_name='Профиль', blank=True, null=True)

    # Step 1: Personal Info
    last_name = models.CharField(max_length=255, verbose_name="Фамилия", blank=True)
    first_name = models.CharField(max_length=255, verbose_name="Имя", blank=True)
    middle_name = models.CharField(max_length=255, verbose_name="Отчество", blank=True)
    gender = models.CharField(max_length=10, choices=GENDERS, default='MAN', verbose_name="Пол")
    birth_date = models.DateField(verbose_name="Дата рождения", null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Телефон", blank=True)
    email = models.EmailField(verbose_name="Email", blank=True)
    region = models.CharField(max_length=1000, verbose_name="Регион проживания", blank=True)
    city = models.CharField(max_length=1000, verbose_name="Город проживания", blank=True)
    address = models.CharField(max_length=1000, verbose_name="Адрес проживания", blank=True)

    # Step 2: Education
    school_name = models.CharField(max_length=255, verbose_name="Название школы", blank=True)
    school_address = models.CharField(max_length=1000, verbose_name="Адрес школы", blank=True)
    class_teacher = models.CharField(max_length=1000, verbose_name="Классный руководитель", blank=True)

    # TODO: оставим, чтобы не удалять бд, потом удалить
    next_year_class = models.CharField(max_length=10, verbose_name="Класс в следующем учебном году", blank=True)

    next_year_class_digit = models.IntegerField(verbose_name="Класс в следующем учебном году", blank=True, null=True,
                                                validators=[
                                                    MinValueValidator(1),
                                                    MaxValueValidator(11)
                                                ])

    class_profile = models.CharField(max_length=255, blank=True, verbose_name="Профиль класса")
    planned_exams = models.CharField(max_length=1000, verbose_name="Планируемые экзамены", blank=True)
    subject_grades = models.CharField(max_length=1000, verbose_name="Оценки по предметам", blank=True)

    # Step 3: Admission Plans
    olympiad_plans = models.CharField(max_length=10000, verbose_name="Планы участия в олимпиадах", blank=True)
    admission_path = models.CharField(max_length=10000, verbose_name="Планируемый путь поступления", blank=True)
    target_universities = models.CharField(max_length=10000, verbose_name="Целевые вузы", blank=True)
    specializations = models.CharField(max_length=10000, verbose_name="Интересующие направления", blank=True)

    # Step 4: Family
    mother = models.CharField(max_length=10000, verbose_name="Мама", blank=True)
    father = models.CharField(max_length=10000, verbose_name="Папа", blank=True)
    legal_guardian = models.CharField(max_length=10000, blank=True, verbose_name="Опекун")
    siblings_count = models.IntegerField(verbose_name="Количество братьев и сестёр", null=True, blank=True)
    siblings_info = models.CharField(max_length=10000, verbose_name="Информация о братьях и сёстрах", blank=True)
    family_size = models.IntegerField(verbose_name="Общий состав семьи", null=True, blank=True)
    income_per_member = models.CharField(max_length=255, verbose_name="Доход на одного члена семьи", blank=True)
    is_low_income = models.CharField(max_length=10, verbose_name="Малообеспеченная семья", blank=True)
    receives_subsidy = models.CharField(max_length=255, verbose_name="Получает ли семья пособия", blank=True)
    other_factors = models.CharField(max_length=10000, blank=True, verbose_name="Другие важные факторы")
    has_pc_with_internet = models.CharField(max_length=1000, verbose_name="Есть ли дома компьютер с интернетом",
                                            blank=True)

    # Step 5: Additional
    vk = models.URLField(max_length=500, verbose_name="Ссылка на вк", blank=True, null=True)
    achievements = models.CharField(max_length=10000, verbose_name="Достижения", blank=True)
    preparation_plan = models.CharField(max_length=10000, verbose_name="План подготовки к поступлению", blank=True)
    foundation_help = models.CharField(max_length=10000, verbose_name="Какая помощь от фонда нужна", blank=True)
    heard_about_program = models.CharField(max_length=255, verbose_name="Как узнали о программе", blank=True)
    willing_to_participate = models.CharField(max_length=10, verbose_name="Готов(а) участвовать в программе",
                                              blank=True)
    agree_processing = models.BooleanField(verbose_name="Согласие на обработку данных", null=True)
    agree_documents = models.BooleanField(verbose_name="Согласие на предоставление документов", null=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата заполнения анкеты")

    tutor_summary = models.TextField(verbose_name="Заметки куратора", blank=True, null=True)

    class Meta:
        verbose_name = "Анкета участника"
        verbose_name_plural = "Анкеты участников"


def video_upload_to(instance, filename):
    return f"videos/visits/{instance.user_id}/{filename}"


def validate_video_size(f):
    max_mb = 200
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Файл больше {max_mb} МБ.")


def validate_video_ext(f):
    allowed_ext = {".mp4", ".webm"}
    name = getattr(f, "name", "") or ""
    ext = Path(name).suffix.lower()
    ctype = getattr(f, "content_type", "") or mimetypes.guess_type(name)[0] or ""
    if ext not in allowed_ext and ctype not in {"video/mp4", "video/webm"}:
        raise ValidationError("Допустимы только MP4 или WebM.")


def default_video_deadline():
    return timezone.now() + timedelta(days=30)


class ScholarVideo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="scholar_video")
    review = models.TextField(verbose_name="Отзыв", blank=True, null=True)
    score = models.PositiveIntegerField(verbose_name="Оценка в баллах", blank=True, null=True)

    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дедлайн сдачи видеовизитки",
        default=None,
        db_index=True,
    )

    file = models.FileField(
        "Видео",
        upload_to=video_upload_to,
        validators=[validate_video_size, validate_video_ext],
        help_text="MP4/WebM, до 200 МБ",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = GenericRelation(StaffNote, related_query_name="videos")

    class Meta:
        verbose_name = "Видеовизитка"
        verbose_name_plural = "Видеовизитки"

    def __str__(self):
        return f"Видеовизитка {self.user.get_full_name() or self.user.username}"


class UserPersonalData(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_data",
    )

    last_name = models.CharField("Фамилия", max_length=150, blank=True)
    first_name = models.CharField("Имя", max_length=150, blank=True)
    middle_name = models.CharField("Отчество", max_length=150, blank=True)

    passport_series = models.CharField("Серия паспорта", max_length=10, blank=True)
    passport_number = models.CharField("Номер паспорта", max_length=20, blank=True)
    passport_issued_at = models.DateField("Дата выдачи", blank=True, null=True)
    passport_issued_by = models.CharField("Кем выдан", max_length=255, blank=True)
    passport_department_code = models.CharField("Код подразделения", max_length=20, blank=True)

    registration_address = models.TextField("Адрес регистрации", blank=True)

    bank_name = models.CharField("Банк", max_length=255, blank=True)
    bank_account = models.CharField("Номер счёта", max_length=34, blank=True)
    bank_bik = models.CharField("БИК", max_length=20, blank=True)
    bank_correspondent_account = models.CharField("Корр. счёт", max_length=34, blank=True)

    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)

    inn = models.CharField("ИНН", max_length=20, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Персональные данные"
        verbose_name_plural = "Персональные данные"

    def __str__(self):
        return f"Персональные данные {self.user}"
