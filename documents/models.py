import os
import uuid

from django.contrib.auth.models import User
from django.db import models


def upload_to_path(instance, filename):
    ext = filename.split('.')[-1]
    new_filename = f'{filename.split(".")[0]}-{uuid.uuid4().hex}.{ext}'
    return os.path.join('documents', instance.user.username, new_filename)


class Document(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('PASSPORT', 'Паспорт'),
        ('INN', 'ИНН'),
        ('SNILS', 'СНИЛС'),
        ('GENERAL', 'Общий документ'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=upload_to_path)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPE_CHOICES,
        default='GENERAL',
        verbose_name="Тип документа",
        unique=False
    )

    def __str__(self):
        if self.document_type != 'GENERAL':
            return f"{self.get_document_type_display()} ({self.user.username})"
        return self.caption if self.caption else self.file.name
