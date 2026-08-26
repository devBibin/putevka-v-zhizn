from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class IncomeYear(models.Model):
    year = models.PositiveSmallIntegerField("Год", unique=True)
    is_active = models.BooleanField("Активен", default=True)
    sort_order = models.PositiveSmallIntegerField("Порядок отображения", default=0)

    class Meta:
        ordering = ("sort_order", "-year")
        verbose_name = "Год дохода"
        verbose_name_plural = "Годы дохода"

    def __str__(self):
        return str(self.year)


class SocialBenefitType(models.Model):
    name = models.CharField("Наименование", max_length=255, unique=True)
    is_other = models.BooleanField("Вариант «другое»", default=False)
    is_active = models.BooleanField("Активен", default=True)
    sort_order = models.PositiveSmallIntegerField("Порядок отображения", default=0)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "Тип социальной выплаты"
        verbose_name_plural = "Типы социальных выплат"

    def __str__(self):
        return self.name


class FamilyIncomeCase(models.Model):
    class Status(models.TextChoices):
        STAFF_DRAFT = "staff_draft", "Черновик сотрудника"
        REVISION = "revision", "На доработке"
        PENDING_REVIEW = "pending_review", "На проверке"
        APPROVED = "approved", "Подтверждено"

    user_info = models.OneToOneField(
        "scholar_form.UserInfo", on_delete=models.CASCADE,
        related_name="family_income_case", verbose_name="Анкета пользователя",
    )
    status = models.CharField("Статус", max_length=32, choices=Status.choices, default=Status.STAFF_DRAFT, db_index=True)
    family_members_count = models.PositiveSmallIntegerField("Количество членов семьи", validators=[MinValueValidator(1)])
    family_members_description = models.TextField("Состав семьи и занятия")
    family_characteristics = models.TextField("Характеристика семьи", blank=True)
    low_income_recognized = models.BooleanField("Семья признана малоимущей", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Карточка семьи и дохода"
        verbose_name_plural = "Карточки семьи и дохода"

    def __str__(self):
        return f"Семья и доход: {self.user_info}"


class FamilyIncomeDocument(models.Model):
    class Category(models.TextChoices):
        FAMILY_CHARACTERISTIC = "family_characteristic", "Подтверждение статуса"
        INCOME = "income", "Доход"
        SOCIAL_BENEFIT = "social_benefit", "Социальные выплаты"
        OTHER = "other", "Иные документы"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Подтверждено"
        CLARIFICATION = "clarification", "Требуется уточнение"

    case = models.ForeignKey(FamilyIncomeCase, on_delete=models.CASCADE, related_name="family_income_documents", verbose_name="Карточка")
    document = models.OneToOneField("documents.Document", on_delete=models.PROTECT, related_name="family_income_link", verbose_name="Файл")
    category = models.CharField("Категория", max_length=32, choices=Category.choices, db_index=True)
    candidate_comment = models.TextField("Комментарий кандидата")
    staff_comment = models.TextField("Комментарий сотрудника", blank=True)
    review_status = models.CharField("Статус проверки", max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING, db_index=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="family_income_documents_added", verbose_name="Добавил")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Документ семьи и дохода"
        verbose_name_plural = "Документы семьи и дохода"
        indexes = [models.Index(fields=("case", "category"))]

    def clean(self):
        super().clean()
        if self.category in {self.Category.FAMILY_CHARACTERISTIC, self.Category.OTHER}:
            has_file = bool(getattr(self.document, "file", None) and self.document.file.name) or bool(getattr(self.document, "yandex_disk_path", ""))
            if not has_file:
                raise ValidationError({"document": "Для этой категории необходим загруженный файл."})

    def __str__(self):
        return f"{self.get_category_display()}: {self.document}"


class IncomeEvidence(models.Model):
    family_income_document = models.OneToOneField(FamilyIncomeDocument, on_delete=models.CASCADE, related_name="income_evidence", verbose_name="Документ")
    year = models.ForeignKey(IncomeYear, on_delete=models.PROTECT, related_name="income_evidence", verbose_name="Год")
    owner_name = models.CharField("Чей документ", max_length=255)
    gross_amount = models.DecimalField("Общая сумма", max_digits=14, decimal_places=2, null=True, blank=True)
    net_amount = models.DecimalField("Сумма после налога", max_digits=14, decimal_places=2, null=True, blank=True)
    average_monthly_amount = models.DecimalField("Средний годовой доход", max_digits=14, decimal_places=2, null=True, blank=True)
    months_received = models.PositiveSmallIntegerField("Месяцев получения", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    absence_reason = models.TextField("Причина отсутствия сумм", blank=True)
    staff_decision_comment = models.TextField("Комментарий сотрудника об учёте", blank=True)

    class Meta:
        verbose_name = "Сведения о доходе"
        verbose_name_plural = "Сведения о доходах"

    def clean(self):
        super().clean()
        if self.family_income_document_id and self.family_income_document.category != FamilyIncomeDocument.Category.INCOME:
            raise ValidationError({"family_income_document": "Сведения о доходе можно добавить только к документу категории «Доход»."})

    def __str__(self):
        return f"{self.owner_name}, {self.year}"


class SocialBenefitEvidence(models.Model):
    family_income_document = models.OneToOneField(FamilyIncomeDocument, on_delete=models.CASCADE, related_name="social_benefit_evidence", verbose_name="Документ")
    recipient_name = models.CharField("Получатель", max_length=255)
    benefit_type = models.ForeignKey(SocialBenefitType, on_delete=models.PROTECT, related_name="evidence", verbose_name="Тип выплаты")
    other_benefit_name = models.CharField("Иная выплата", max_length=255, blank=True)

    class Meta:
        verbose_name = "Сведения о социальной выплате"
        verbose_name_plural = "Сведения о социальных выплатах"

    def clean(self):
        super().clean()
        if self.family_income_document_id and self.family_income_document.category != FamilyIncomeDocument.Category.SOCIAL_BENEFIT:
            raise ValidationError({"family_income_document": "Сведения о выплате можно добавить только к документу категории «Социальные выплаты»."})
        if self.benefit_type_id and self.benefit_type.is_other and not self.other_benefit_name.strip():
            raise ValidationError({"other_benefit_name": "Укажите название выплаты."})

    def __str__(self):
        return f"{self.recipient_name}: {self.benefit_type}"


class FamilyIncomeDecision(models.Model):
    case = models.ForeignKey(FamilyIncomeCase, on_delete=models.CASCADE, related_name="decisions", verbose_name="Карточка")
    year = models.ForeignKey(IncomeYear, on_delete=models.PROTECT, related_name="decisions", verbose_name="Год")
    amount_per_member = models.DecimalField("Среднемесячный доход на члена семьи", max_digits=14, decimal_places=2, null=True, blank=True)
    comment = models.TextField("Пояснение")
    is_low_income_recognized = models.BooleanField("Семья признана малоимущей за год", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="family_income_decisions_created", verbose_name="Создал")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="family_income_decisions_updated", verbose_name="Изменил")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("case", "year"), name="family_income_unique_decision_year")]
        verbose_name = "Ручной итог дохода"
        verbose_name_plural = "Ручные итоги дохода"

    def __str__(self):
        return f"{self.case} — {self.year}"


class FamilyIncomeInstruction(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликована"
        ARCHIVED = "archived", "Архив"

    url = models.URLField("Ссылка")
    version = models.CharField("Версия", max_length=64, unique=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField("Опубликована", null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="family_income_instructions_updated", verbose_name="Изменил")
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("status",), condition=Q(status="published"), name="family_income_one_published_instruction")]
        verbose_name = "Инструкция по семье и доходу"
        verbose_name_plural = "Инструкции по семье и доходу"

    def __str__(self):
        return f"Инструкция {self.version}"


class FamilyIncomeAuditEvent(models.Model):
    case = models.ForeignKey(FamilyIncomeCase, on_delete=models.CASCADE, related_name="audit_events", verbose_name="Карточка")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="family_income_audit_events", verbose_name="Исполнитель")
    action = models.CharField("Действие", max_length=100)
    target_model = models.CharField("Модель объекта", max_length=100)
    target_id = models.PositiveBigIntegerField("ID объекта")
    before = models.JSONField("До изменения", default=dict, blank=True)
    after = models.JSONField("После изменения", default=dict, blank=True)
    reason = models.TextField("Причина", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Событие аудита семьи и дохода"
        verbose_name_plural = "События аудита семьи и дохода"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("События аудита неизменяемы.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("События аудита неизменяемы.")

    def __str__(self):
        return f"{self.action}: {self.target_model} #{self.target_id}"
