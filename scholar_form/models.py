import mimetypes
import os
import uuid
from pathlib import Path

from importlib.resources._common import _

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class UserInfo(models.Model):
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True, verbose_name="Аватар")

    is_done = models.BooleanField(default=False, verbose_name='Анкета уже отправлена')

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, related_name='user_info')

    # Step 1: Personal Info
    last_name = models.CharField(max_length=255, verbose_name="Фамилия", blank=True)
    first_name = models.CharField(max_length=255, verbose_name="Имя", blank=True)
    middle_name = models.CharField(max_length=255, verbose_name="Отчество", blank=True)
    birth_date = models.DateField(verbose_name="Дата рождения", null=True)
    phone = models.CharField(max_length=20, verbose_name="Телефон", blank=True)
    email = models.EmailField(verbose_name="Email", blank=True)
    region = models.CharField(max_length=1000, verbose_name="Регион проживания", blank=True)
    address = models.CharField(max_length=1000, verbose_name="Адрес проживания", blank=True)

    # Step 2: Education
    school_name = models.CharField(max_length=255, verbose_name="Название школы", blank=True)
    school_address = models.CharField(max_length=1000, verbose_name="Адрес школы", blank=True)
    class_teacher = models.CharField(max_length=1000, verbose_name="Классный руководитель", blank=True)
    next_year_class = models.CharField(max_length=10, verbose_name="Класс в следующем учебном году", blank=True)
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
    siblings_count = models.IntegerField(verbose_name="Количество братьев и сестёр", null=True)
    siblings_info = models.CharField(max_length=10000, verbose_name="Информация о братьях и сёстрах", blank=True)
    family_size = models.IntegerField(verbose_name="Общий состав семьи", null=True)
    income_per_member = models.CharField(max_length=255, verbose_name="Доход на одного члена семьи", blank=True)
    is_low_income = models.CharField(max_length=10, verbose_name="Малообеспеченная семья", blank=True)
    receives_subsidy = models.CharField(max_length=255, verbose_name="Получает ли семья пособия", blank=True)
    other_factors = models.CharField(max_length=10000, blank=True, verbose_name="Другие важные факторы")
    has_pc_with_internet = models.CharField(max_length=1000, verbose_name="Есть ли дома компьютер с интернетом",
                                            blank=True)

    # Step 5: Additional
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

class ScholarVideo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="scholar_video")
    review = models.TextField(verbose_name="Отзыв", blank=True, null=True)
    score = models.PositiveIntegerField(verbose_name="Оценка в баллах", blank=True, null=True)
    file = models.FileField(
        "Видео",
        upload_to=video_upload_to,
        validators=[validate_video_size, validate_video_ext],
        help_text="MP4/WebM, до 200 МБ"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Видеовизитка"
        verbose_name_plural = "Видеовизитки"

    def __str__(self):
        return f"Видеовизитка {self.user.get_full_name() or self.user.username}"