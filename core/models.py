from django.contrib.auth.models import User
from django.db import models


class MotivationLetter(models.Model):
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Мотивационное письмо"
        verbose_name_plural = "Мотивационные письма"
        ordering = ['-created_at']

    def __str__(self):
        return f"Письмо от {self.user.username} - {self.created_at.strftime('%Y-%m-%d')}"

