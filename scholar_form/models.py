import os
import uuid

from django.contrib.auth.models import User
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

    class Meta:
        verbose_name = "Анкета участника"
        verbose_name_plural = "Анкеты участников"


def video_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1] or ".mp4"
    return f"videos/{instance.user_id}/{uuid.uuid4().hex}{ext}"


class VideoSubmission(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Получено"
        SAVED = "saved", "Сохранено"
        REJECTED = "rejected", "Отклонено"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="video_submissions")
    tg_user_id = models.CharField(max_length=32, blank=True, default="")
    tg_file_id = models.CharField(max_length=256, blank=True, default="")
    tg_file_path = models.CharField(max_length=256, blank=True, default="")

    file = models.FileField(upload_to=video_upload_to, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)

    duration_sec = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)

    created_at = models.DateTimeField(auto_now_add=True)

    review = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"VideoSubmission(user={self.user_id}, id={self.id}, {self.status})"
