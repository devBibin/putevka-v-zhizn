from django import forms
from .models import Document
import magic

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'caption', 'document_type']

        labels = {
            'caption': 'Описание документа',
            'file': 'Выберите файл',
            'document_type': 'Тип документа',
        }
        widgets = {
            'document_type': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.specific_document_type = kwargs.pop('specific_document_type', None)
        self.specific_caption = kwargs.pop('specific_caption', None)

        super().__init__(*args, **kwargs)

        if self.specific_document_type:
            self.initial['document_type'] = self.specific_document_type
            self.fields['document_type'].required = True
            self.fields['document_type'].widget = forms.HiddenInput()

            if self.specific_caption:
                self.initial['caption'] = self.specific_caption
                self.fields['caption'].widget = forms.TextInput(attrs={'readonly': 'readonly'})
                self.fields['caption'].required = False
            else:
                self.fields['caption'].required = True
        else:
            self.fields['document_type'].initial = 'GENERAL'
            self.fields['document_type'].widget = forms.HiddenInput()
            self.fields['caption'].required = False
            self.fields['caption'].widget = forms.TextInput(attrs={'placeholder': 'Введите описание (необязательно)'})

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise forms.ValidationError("Выберите файл для загрузки.")
        else:
            initial_bytes = uploaded_file.read(1024)
            uploaded_file.seek(0)

            try:
                file_mime_type = magic.from_buffer(initial_bytes, mime=True)
            except Exception as e:
                raise forms.ValidationError(f"Не удалось определить тип файла: {e}")

        allowed_types_map = {
            'PASSPORT': ['application/pdf', 'image/jpeg', 'image/png'],
            'INN': ['application/pdf', 'image/jpeg', 'image/png'],
            'SNILS': ['application/pdf', 'image/jpeg', 'image/png'],
            'GENERAL': [
                'application/pdf',
                'application/msword',
                'text/plain',
                'image/jpeg',
                'image/png',
            ]
        }

        doc_type_for_validation = self.specific_document_type or self.initial.get('document_type', 'GENERAL')

        allowed_types = allowed_types_map.get(doc_type_for_validation, allowed_types_map['GENERAL'])

        if file_mime_type not in allowed_types:
            type_names = ", ".join([t.split('/')[-1] for t in allowed_types])
            raise forms.ValidationError(
                f"Недопустимый формат файла. Разрешены: {type_names.upper().replace('JPEG', 'JPG')}."
            )

        max_upload_size = 20 * 1024 * 1024  # 20 MB
        if uploaded_file.size > max_upload_size:
            raise forms.ValidationError(f"Размер файла не должен превышать {max_upload_size / (1024 * 1024):.0f} MB.")

        return uploaded_file

    def clean_document_type(self):
        if self.specific_document_type and self.cleaned_data.get('document_type') != self.specific_document_type:
            raise forms.ValidationError("Тип документа не может быть изменен.")
        return self.cleaned_data.get('document_type')