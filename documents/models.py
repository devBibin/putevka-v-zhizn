import os
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


def upload_to_path(instance, filename):
    ext = filename.split('.')[-1]
    new_filename = f'{filename.split(".")[0]}_{uuid.uuid4().hex}.{ext}'
    return os.path.join('documents', instance.user.username, new_filename)


class Document(models.Model):
    STATUSES = [
        ('PENDING', 'На проверке'),
        ('APPROVED', 'Подтверждено'),
        ('QUESTION', 'Уточнить'),
        ('PENDING_SIGNATURE', 'Ожидает подписи'),
        ('SIGNED', 'Подписан'),
        ('REJECTED_SIGNATURE', 'Подпись отклонена'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=upload_to_path)
    user_file_name = models.CharField(max_length=100, null=True, blank=True)
    caption = models.CharField(max_length=255, blank=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    status = models.CharField(max_length=18, choices=STATUSES, default='PENDING')

    only_staff_comment = models.TextField(blank=True, null=True)

    uploaded_by_staff = models.BooleanField(default=False)

    related_documents = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='document_relations')

    is_locked = models.BooleanField(default=False, verbose_name="Заблокирован")

    def clean(self):
        super().clean()
        if not self.caption:
            raise ValidationError({'caption': 'Это поле не может быть пустым.'})

        if self.pk and self.is_locked and not hasattr(self, '_ignore_lock_validation'):
            raise ValidationError("Этот документ заблокирован и не может быть изменен.")

    def save(self, *args, **kwargs):
        if self.pk is None and self.file:
            if not self.user_file_name:
                self.user_file_name = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.file.name
