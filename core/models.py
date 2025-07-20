from django.conf import settings
from django.db import models


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