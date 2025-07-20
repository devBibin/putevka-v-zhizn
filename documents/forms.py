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

        file_size = 0
        initial_bytes = b''
        mime_checked = False

        for chunk in uploaded_file.chunks():
            file_size += len(chunk)

            if not mime_checked and len(initial_bytes) < 1024:
                initial_bytes += chunk
                if len(initial_bytes) >= 1024:
                    try:
                        file_mime_type = magic.from_buffer(initial_bytes, mime=True)
                        mime_checked = True
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

            if file_size > max_upload_size:
                raise forms.ValidationError(
                    f"Размер файла не должен превышать {max_upload_size / (1024 * 1024):.0f} MB."
                )

        if not mime_checked:
            if not initial_bytes:
                raise forms.ValidationError("Файл пуст.")
            try:
                file_mime_type = magic.from_buffer(initial_bytes, mime=True)
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
