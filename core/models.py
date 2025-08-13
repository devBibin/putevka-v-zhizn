from datetime import timezone

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings


class MotivationLetter(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        SUBMITTED = 'submitted', 'Отправлено'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='motivation_letter',
        verbose_name="Стипендиат"
    )

    letter_text = models.CharField(max_length=20000, blank=True, help_text='Вставьте своё мотивационное письмо сюда',
                                   verbose_name='Текст мотивационного письма')  # сколько-то символов ограничение?

    admin_rating = models.TextField(
        verbose_name="Оценка администратора",
        null=True,
        blank=True,
    )

    gpt_review = models.TextField(
        verbose_name="Обзор от ChatGPT",
        null=True,
        blank=True,
        help_text="Обзор мотивационного письма, сгенерированный ChatGPT."
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Статус"
    )
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="Отправлено в")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Мотивационное письмо"
        verbose_name_plural = "Мотивационные письма"
        ordering = ['-created_at']

    def clean(self):
        if self.pk:
            original = MotivationLetter.objects.get(pk=self.pk)
            if original.status == self.Status.SUBMITTED:
                if self.letter_text != original.letter_text:
                    raise ValidationError("Нельзя изменять текст письма после отправки.")
                if self.status != original.status:
                    raise ValidationError("Нельзя менять статус отправленного письма.")

        if self.status == self.Status.SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()
        if self.status == self.Status.SUBMITTED and not self.letter_text.strip():
            raise ValidationError("Нельзя отправить пустое письмо.")

    def save(self, *args, **kwargs):
        if self.status == self.Status.SUBMITTED and self.submitted_at is None:
            self.submitted_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Письмо от {self.user.username} - {self.created_at.strftime('%Y-%m-%d')}"


class Notification(models.Model):
    message = models.TextField(verbose_name='Сообщение')

    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='UserNotification',
        related_name='received_notifications',
        verbose_name="Получатели"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='sent_notifications',
        null=True,
        blank=True,
        verbose_name="Отправитель"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Оповещение"
        verbose_name_plural = "Оповещения"

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.sender:
            obj.sender = request.user
        super().save_model(request, obj, form, change)

    def __str__(self):
        return f"Оповещение {self.message[:50] + '...' if len(self.message) > 50 else self.message} от {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class UserNotification(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        verbose_name="Оповещение"
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )

    is_seen = models.BooleanField(default=False, verbose_name="Просмотрено")

    seen_at = models.DateTimeField(null=True, blank=True, verbose_name="Время просмотра")

    class Meta:
        unique_together = ('notification', 'recipient')
        verbose_name = "Получатель оповещения"
        verbose_name_plural = "Получатели оповещения"
        ordering = ['-notification__created_at']

    def __str__(self):
        status = "Просмотрено" if self.is_seen else "Не просмотрено"
        return f"Оповещение '{self.notification.message[:20]}...' для {self.recipient.username} - {status}"
