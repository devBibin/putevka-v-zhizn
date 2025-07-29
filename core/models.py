from django.db import models

from django.db import models
from django.conf import settings


class TelegramAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_account',
        verbose_name="Пользователь"
    )

    telegram_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Telegram ID"
    )

    username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Имя пользователя Telegram"
    )

    first_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Имя"
    )

    last_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Фамилия"
    )

    language_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name="Языковой код"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Последнее обновление"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    class Meta:
        verbose_name = "Аккаунт Telegram"
        verbose_name_plural = "Аккаунты Telegram"
        indexes = [
            models.Index(fields=['telegram_id']),
        ]

    def __str__(self):
        return f"{self.user.username}'s Telegram Account ({self.telegram_id})"