import random
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


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
        null=True,
        blank=True,
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

    activation_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Токен активации Telegram",
        help_text="Уникальный токен для активации аккаунта через Telegram."
    )
    telegram_verified = models.BooleanField(
        default=False,
        verbose_name="Активен ли веб-аккаунт",
        help_text="Определяет, активирован ли пользовательский аккаунт на сайте после привязки Telegram."
    )

    class Meta:
        verbose_name = "Аккаунт Telegram"
        verbose_name_plural = "Аккаунты Telegram"
        indexes = [
            models.Index(fields=['telegram_id']),
            models.Index(fields=['activation_token']),
        ]

    def __str__(self):
        return f"{self.user.username}'s Telegram Account ({self.telegram_id if self.telegram_id else 'Не привязан'})"


class RegistrationPersonalData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True,
                                help_text="Ссылка на созданного пользователя после завершения регистрации.")

    email = models.EmailField(unique=True, help_text="Email, введенный пользователем.")
    password = models.CharField(max_length=128, help_text="Хешированный пароль пользователя.")

    email_verification_code = models.CharField(max_length=6, blank=True, null=True,
                                               help_text="Код для подтверждения email.")

    email_code_expires_at = models.DateTimeField(blank=True, null=True,
                                                 help_text="Время истечения срока действия кода email.")

    email_verified = models.BooleanField(default=False,
                                         help_text="True, если email был успешно подтвержден.")

    telegram_account = models.OneToOneField(TelegramAccount, on_delete=models.SET_NULL, null=True, blank=True,
                                            help_text="Ссылка на связанный TelegramAccount для активации.")

    phone_number = models.CharField(max_length=20, blank=True, null=True,
                                    help_text="Номер телефона, введенный пользователем (если не из Telegram).")

    phone_verified = models.BooleanField(default=False,
                                         help_text="True, если номер телефона был успешно подтвержден.")

    current_step = models.CharField(max_length=50, default='initial_data',
                                    choices=[
                                        ('initial_data', 'Ввод начальных данных'),
                                        ('email_verification', 'Подтверждение Email'),
                                        ('telegram_connection', 'Подключение Telegram'),
                                        ('phone_verification_needed', 'Требуется подтверждение телефона'),
                                        ('phone_verification_code', 'Ввод кода подтверждения телефона'),
                                        ('finish', 'Завершение регистрации'),
                                    ],
                                    help_text="Текущий шаг в процессе регистрации.")

    token = models.UUIDField(default=uuid.uuid4, unique=True,
                             help_text="Уникальный токен для отслеживания сессии регистрации.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Попытка регистрации"
        verbose_name_plural = "Попытки регистрации"

    def __str__(self):
        return f"Попытка регистрации для {self.email} (Шаг: {self.current_step})"

    def is_email_code_expired(self):
        return self.email_code_expires_at and self.email_code_expires_at < timezone.now()

    def generate_email_code(self):
        self.email_verification_code = str(random.randint(100000, 999999))
        self.email_code_expires_at = datetime.now() + timedelta(minutes=15)
        self.save()


class UserInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_info', )
    phone_number = models.CharField(max_length=20, blank=True, null=True, )
