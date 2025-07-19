from django.conf import settings
from django.db import models

class Notification(models.Model):
    message = models.TextField(verbose_name='Сообщение')

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Получатель"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    is_seen = models.BooleanField(default=False, verbose_name="Просмотрено")

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

    def __str__(self):
        return f"Оповещение для {self.recipient.username} от {self.created_at.strftime('%Y-%m-%d %H:%M')}"