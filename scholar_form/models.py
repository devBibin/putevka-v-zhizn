from django.contrib.auth.models import User
from django.db import models

class UserInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True)

    # Step 1: Personal Info
    full_name = models.CharField(max_length=255, verbose_name="ФИО")
    birth_date = models.DateField(verbose_name="Дата рождения")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    email = models.EmailField(verbose_name="Email")
    region = models.CharField(max_length=1000, verbose_name="Регион проживания")
    address = models.CharField(max_length=1000, verbose_name="Адрес проживания")

    # Step 2: Education
    school_name = models.CharField(max_length=255, verbose_name="Название школы")
    school_address = models.CharField(max_length=1000, verbose_name="Адрес школы")
    class_teacher = models.CharField(max_length=1000, verbose_name="Классный руководитель")
    next_year_class = models.CharField(max_length=10, verbose_name="Класс в следующем учебном году")
    class_profile = models.CharField(max_length=255, blank=True, verbose_name="Профиль класса")
    planned_exams = models.CharField(max_length=1000, verbose_name="Планируемые экзамены")
    subject_grades = models.CharField(max_length=1000, verbose_name="Оценки по предметам")

    # Step 3: Admission Plans
    olympiad_plans = models.CharField(max_length=10000, verbose_name="Планы участия в олимпиадах")
    admission_path = models.CharField(max_length=10000, verbose_name="Планируемый путь поступления")
    target_universities = models.CharField(max_length=10000, verbose_name="Целевые вузы")
    specializations = models.CharField(max_length=10000, verbose_name="Интересующие направления")

    # Step 4: Family
    mother = models.CharField(max_length=10000, verbose_name="Мама")
    father = models.CharField(max_length=10000, verbose_name="Папа")
    legal_guardian = models.CharField(max_length=10000, blank=True, verbose_name="Опекун")
    siblings_count = models.IntegerField(verbose_name="Количество братьев и сестёр")
    siblings_info = models.CharField(max_length=10000, verbose_name="Информация о братьях и сёстрах")
    family_size = models.IntegerField(verbose_name="Общий состав семьи")
    income_per_member = models.CharField(max_length=255, verbose_name="Доход на одного члена семьи")
    is_low_income = models.CharField(max_length=10, verbose_name="Малообеспеченная семья")
    receives_subsidy = models.CharField(max_length=255, verbose_name="Получает ли семья пособия")
    other_factors = models.CharField(max_length=10000, blank=True, verbose_name="Другие важные факторы")
    has_pc_with_internet = models.CharField(max_length=1000, verbose_name="Есть ли дома компьютер с интернетом")

    # Step 5: Additional
    achievements = models.CharField(max_length=10000, verbose_name="Достижения")
    preparation_plan = models.CharField(max_length=10000, verbose_name="План подготовки к поступлению")
    foundation_help = models.CharField(max_length=10000, verbose_name="Какая помощь от фонда нужна")
    heard_about_program = models.CharField(max_length=255, verbose_name="Как узнали о программе")
    willing_to_participate = models.CharField(max_length=10, verbose_name="Готов(а) участвовать в программе")
    agree_processing = models.BooleanField(verbose_name="Согласие на обработку данных")
    agree_documents = models.BooleanField(verbose_name="Согласие на предоставление документов")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата заполнения анкеты")

    class Meta:
        verbose_name = "Анкета участника"
        verbose_name_plural = "Анкеты участников"