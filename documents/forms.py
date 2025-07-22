import logging

import magic
from django import forms

from .models import Document

logger = logging.getLogger(__name__)


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'caption']

        labels = {
            'caption': 'Описание документа',
            'file': 'Выберите файл',
        }

    def __init__(self, *args, **kwargs):
        self.specific_caption = kwargs.pop('specific_caption', None)

        super().__init__(*args, **kwargs)

        self.fields['caption'].required = False
        self.fields['caption'].widget = forms.TextInput(attrs={'placeholder': 'Введите описание'})

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')

        if not uploaded_file:
            raise forms.ValidationError("Выберите файл для загрузки.")

        max_upload_size = 20 * 1024 * 1024  # 20 MB

        try:
            file_content = uploaded_file.read()
            file_size = len(file_content)
        except Exception as e:
            logger.error(f'Ошибка при чтении файла: {e}')
            raise forms.ValidationError("Не удалось прочитать файл.")

        if file_size > max_upload_size:
            logger.info('Пользователь пытается загрузить слишком большой файл')
            raise forms.ValidationError(
                f"Размер файла не должен превышать {max_upload_size / (1024 * 1024):.0f} MB."
            )

        if not file_content:
            raise forms.ValidationError("Файл пуст.")

        try:
            file_mime_type = magic.from_buffer(file_content[:1024], mime=True)
        except Exception as e:
            logger.info(f'При определении типа файла произошла ошибка: {e}')
            raise forms.ValidationError(f"Не удалось определить тип файла: {e}")

        allowed_types = [
            'application/pdf',
            'application/msword',
            'text/plain',
            'image/jpeg',
            'image/png',
        ]

        if file_mime_type not in allowed_types:
            type_names = ", ".join([t.split('/')[-1] for t in allowed_types])
            raise forms.ValidationError(
                f"Недопустимый формат файла. Разрешены: {type_names.upper().replace('JPEG', 'JPG')}."
            )

        uploaded_file.seek(0)
        return uploaded_file
