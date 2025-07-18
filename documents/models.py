import os
import uuid

from django.contrib.auth.models import User
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
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=upload_to_path)
    user_file_name = models.CharField(max_length=100, null=True, blank=True)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUSES, default='PENDING')

    def save(self, *args, **kwargs):
        if self.pk is None and self.file:
            if not self.user_file_name:
                self.user_file_name = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.caption if self.caption else self.file.name
