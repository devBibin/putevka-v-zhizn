from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Interview(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="interview",
        help_text="Пользователь, проходящий собеседование"
    )
    notes = models.TextField(
        "Заметки интервьюера",
        blank=True,
        help_text="Свободные заметки по итогам собеседования"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Собеседование"
        verbose_name_plural = "Собеседования"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Собеседование: {self.user}"


class TestAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Назначено"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершено"
        CANCELLED = "cancelled", "Отменено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="test_assignments",
        verbose_name="Кандидат",
    )
    title = models.CharField("Название теста", max_length=200)
    external_url = models.URLField("Ссылка на прохождение", blank=True)
    instructions = models.TextField("Инструкции/Комментарий", blank=True)

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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

    result_score = models.DecimalField("Баллы", max_digits=6, decimal_places=2, null=True, blank=True)
    result_text = models.TextField("Комментарий/результат", blank=True)
    passed = models.BooleanField("Пройдено успешно", null=True, blank=True)

    completed_at = models.DateTimeField("Завершено", null=True, blank=True)
    result_filled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="filled_test_results",
        verbose_name="Результат внёс",
    )
    result_filled_at = models.DateTimeField("Результат внесён", null=True, blank=True)

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
