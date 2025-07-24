import logging

import magic
from django import forms

from .models import Document

logger = logging.getLogger(__name__)

class AttachDocumentsForm(forms.Form):
    documents_to_attach = forms.ModelMultipleChoiceField(
        queryset=Document.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Выберите документы пользователя для прикрепления"
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['documents_to_attach'].queryset = Document.objects.filter(
                user=user,
                uploaded_by_staff=False,
                is_deleted=False
            ).order_by('-uploaded_at')

            self.fields['documents_to_attach'].label_from_instance = self._get_document_label

    def _get_document_label(self, obj):
        if obj.caption:
            return f"{obj.caption} ({obj.user_file_name or 'файл без имени'})"
        return obj.user_file_name or obj.file.name

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'caption']

        labels = {
            'caption': 'Описание документа',
            'file': 'Выберите файл',
        }

        widgets = {
                'caption': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Введите описание документа', 'max_length': '255'}),
            }

    def __init__(self, *args, **kwargs):
        self.specific_caption = kwargs.pop('specific_caption', None)

        super().__init__(*args, **kwargs)

        self.fields['caption'].required = True

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
