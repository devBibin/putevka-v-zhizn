import os
import uuid

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from scholar_form.models import StaffNote


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
    file = models.FileField(upload_to=upload_to_path, blank=True)
    user_file_name = models.CharField(max_length=100, null=True, blank=True)
    yandex_disk_path = models.CharField(max_length=1024, blank=True, default="")
    yandex_disk_uploaded_at = models.DateTimeField(blank=True, null=True)
    yandex_disk_error = models.TextField(blank=True, default="")
    caption = models.CharField(max_length=255, blank=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    status = models.CharField(max_length=18, choices=STATUSES, default='PENDING')

    only_staff_comment = models.TextField(blank=True, null=True)

    uploaded_by_staff = models.BooleanField(default=False)

    related_documents = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='document_relations')

    notes = GenericRelation(StaffNote, related_query_name="letters")

    def clean(self):
        super().clean()
        if not self.caption:
            raise ValidationError({'caption': 'Это поле не может быть пустым.'})

    def save(self, *args, **kwargs):
        if self.pk is None and self.file:
            if not self.user_file_name:
                self.user_file_name = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user_file_name or self.file.name or self.yandex_disk_path


class DocTemplate(models.Model):
    name = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    file = models.FileField(
        "Файл шаблона (.docx)",
        upload_to="doc_templates/",
        validators=[FileExtensionValidator(["docx"])],
    )
    required_params = models.JSONField("Требуемые параметры", default=dict, blank=True)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"

    def __str__(self):
        return self.name
