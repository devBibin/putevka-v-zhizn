import random
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings

from scholar_form.models import StaffNote


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

    email_verification_code = models.UUIDField(
        "Токен для подтверждения email",
        default=uuid.uuid4,
        unique=True,
        editable=False,
        null=True, blank=True,
        db_index=True,
    )

    email_code_sent_at = models.DateTimeField(null=True, blank=True,
                                                help_text="Время истечения срока действия кода email.")

    email_code_expires_at = models.DateTimeField(null=True, blank=True,
                                                 help_text="Время истечения срока действия кода email.")

    email_verified = models.BooleanField(default=False,
                                         help_text="True, если email был успешно подтвержден.")

    telegram_account = models.OneToOneField(TelegramAccount, on_delete=models.SET_NULL, null=True, blank=True,
                                            help_text="Ссылка на связанный TelegramAccount для активации.")

    phone = models.CharField(max_length=20, blank=True, null=True,
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
        self.email_verification_code = uuid.uuid4()
        self.email_code_sent_at = timezone.now()
        self.email_code_expires_at = timezone.now() + timedelta(minutes=15)
        self.save()

class MotivationLetter(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        SUBMITTED = 'submitted', 'Отправлено'
        REVISION = 'revision', 'На дописывании'

    is_done = models.BooleanField(default=False, verbose_name='Мотивационное письмо принято')

    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дедлайн сдачи мотивационного письма",
        db_index=True,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='motivation_letter',
        verbose_name="Стипендиат"
    )

    letter_text = models.TextField(
        blank=True,
        help_text='Вставьте своё мотивационное письмо сюда',
        verbose_name='Текст мотивационного письма'
    )

    admin_score = models.PositiveSmallIntegerField(
        verbose_name='Итоговый балл',
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        help_text="Введите значение от 0 до 60",
        blank=True,
        null=True
    )

    admin_rating = models.TextField(
        verbose_name="Оценка администратора",
        null=True,
        blank=True,
    )

    revision_comment = models.TextField(
        null=True, blank=True,
        verbose_name="Комментарий на доработку (видит соискатель)"
    )
    revision_requested_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Отправлено на доработку в",
        db_index=True
    )
    revision_requested_by = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="motivation_letters_revision_requested",
        verbose_name="Кто отправил на доработку"
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Статус",
        db_index=True
    )
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="Отправлено в", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = GenericRelation(StaffNote, related_query_name="documents")

    class Meta:
        verbose_name = "Мотивационное письмо"
        verbose_name_plural = "Мотивационные письма"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['created_at']),
        ]

    def clean(self):
        if self.pk:
            original = MotivationLetter.objects.get(pk=self.pk)

            if (
                original.status == self.Status.SUBMITTED
                and self.status == self.Status.SUBMITTED
                and self.letter_text != original.letter_text
            ):
                raise ValidationError("Нельзя изменять текст письма после отправки.")

        if self.status == self.Status.SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()

        if self.status == self.Status.SUBMITTED and not (self.letter_text or "").strip():
            raise ValidationError("Нельзя отправить пустое письмо.")

    def save(self, *args, **kwargs):
        if self.status == self.Status.SUBMITTED and self.submitted_at is None:
            self.submitted_at = timezone.now()
            self.is_done = True

        if self.status == self.Status.REVISION:
            self.is_done = False

        super().save(*args, **kwargs)

    def word_count(self) -> int:
        txt = (self.letter_text or "").strip()
        return len([w for w in txt.split() if w])

    def apply_gpt_result(self, *, score: int | None, word_count: int | None,
                         payload_json: dict | None, summary: str | None,
                         flags: dict | None = None, model_name: str | None = None,
                         rubric_version: str | None = None):
        if summary is not None:
            self.gpt_review = summary
        if score is not None:
            self.gpt_score = int(score)
        if word_count is not None:
            self.gpt_word_count = int(word_count)
        if payload_json is not None:
            self.gpt_json = payload_json
        if flags is not None:
            self.gpt_flags = flags
        if model_name is not None:
            self.gpt_model = model_name
        if rubric_version is not None:
            self.gpt_version = rubric_version
        self.gpt_scored_at = timezone.now()

    def send_to_revision(self, *, comment: str, by_user):
        self.status = self.Status.REVISION
        self.revision_comment = comment
        self.revision_requested_at = timezone.now()
        self.revision_requested_by = by_user
        self.is_done = False

    def is_deadline_passed(self) -> bool:
        return bool(self.deadline_at and timezone.now() > self.deadline_at)

    def days_left(self) -> int | None:
        if not self.deadline_at:
            return None
        delta = self.deadline_at.date() - timezone.now().date()
        return max(delta.days, 0)

    def __str__(self):
        return f"Письмо от {self.user.username} - {self.created_at.strftime('%Y-%m-%d')}"


class MotivationLetterRubricReview(models.Model):
    class ContentGrade(models.TextChoices):
        FULL = "full", "Полное раскрытие"
        PARTIAL = "partial", "Частично"
        NONE = "none", "Не раскрыто"

    class CompositionGrade(models.TextChoices):
        GOOD = "good", "Хорошая"
        MINOR = "minor_issue", "Незначительные проблемы"
        MAJOR = "major_issue", "Серьёзные проблемы"

    class StylePrecisionGrade(models.TextChoices):
        GOOD = "good", "Точный стиль"
        ONE_DIM = "one_dimensional_or_imprecise", "Однообразный / неточный"
        POOR = "poor", "Плохой стиль"

    class OrthographyGrade(models.TextChoices):
        NONE = "none", "Ошибок нет"
        ONE_TWO = "one_two", "1–2 ошибки"
        THREE_PLUS = "three_plus", "3 и более ошибок"

    class SyntaxGrade(models.TextChoices):
        NONE = "none", "Ошибок нет"
        ONE = "one", "1 ошибка"
        TWO_PLUS = "two_plus", "2 и более ошибок"

    letter = models.OneToOneField(
        MotivationLetter,
        on_delete=models.CASCADE,
        related_name="rubric_review",
        verbose_name="Мотивационное письмо",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата оценки",
    )

    model_name = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Модель ИИ",
    )

    schema_version = models.CharField(
        max_length=32,
        blank=True,
        default="v1",
        verbose_name="Версия рубрики",
    )

    word_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество слов",
    )

    total_score = models.IntegerField(
        default=0,
        verbose_name="Итоговый балл",
    )

    specialty_choice = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="Выбор специальности",
    )
    university_choice = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="Выбор университета",
    )
    current_preparation = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="Текущая подготовка",
    )
    next_year_plan = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="План на следующий год",
    )
    higher_ed_value = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="Ценность высшего образования",
    )
    support_criticality = models.CharField(
        max_length=16,
        choices=ContentGrade.choices,
        verbose_name="Критичность поддержки",
    )

    composition = models.CharField(
        max_length=16,
        choices=CompositionGrade.choices,
        verbose_name="Композиция текста",
    )
    style_precision = models.CharField(
        max_length=32,
        choices=StylePrecisionGrade.choices,
        verbose_name="Точность стиля",
    )

    orthography = models.CharField(
        max_length=16,
        choices=OrthographyGrade.choices,
        verbose_name="Орфография",
    )
    syntax = models.CharField(
        max_length=16,
        choices=SyntaxGrade.choices,
        verbose_name="Синтаксис",
    )

    family = models.TextField(blank=True, default="", verbose_name="Семья")
    hobbies = models.TextField(blank=True, default="", verbose_name="Хобби")
    achievements = models.TextField(blank=True, default="", verbose_name="Достижения")
    traits = models.TextField(blank=True, default="", verbose_name="Личные качества")
    school_teachers = models.TextField(blank=True, default="", verbose_name="Учителя")
    prep_subjects = models.TextField(blank=True, default="", verbose_name="Предметы подготовки")
    specialty = models.TextField(blank=True, default="", verbose_name="Предполагаемая специальность")
    preferred_universities = models.TextField(blank=True, default="", verbose_name="Предпочтительные вузы")
    relocation = models.TextField(blank=True, default="", verbose_name="Готовность к переезду")
    olympiads = models.TextField(blank=True, default="", verbose_name="Олимпиады")
    motivation = models.TextField(blank=True, default="", verbose_name="Мотивация")
    help_criticality = models.TextField(blank=True, default="", verbose_name="Критичность помощи")
    extra = models.TextField(blank=True, default="", verbose_name="Дополнительная информация")

    justification = models.TextField(
        blank=True,
        default="",
        verbose_name="Пояснение эксперта",
    )

    class Meta:
        verbose_name = "Оценка мотивационного письма по рубрике"
        verbose_name_plural = "Оценки мотивационных писем по рубрике"
        indexes = [
            models.Index(fields=["total_score"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["schema_version"]),
        ]

    def __str__(self) -> str:
        return f"Рубрика: письмо #{self.letter_id}, {self.total_score} баллов"


class MotivationLetterInstruction(models.Model):
    title = models.CharField(max_length=200, default="Требования к мотивационному письму")
    file = models.FileField(upload_to="motivation/instructions/")
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


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
