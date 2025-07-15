from django import forms
from .models import Document

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'caption']

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            allowed_types = [
                'application/pdf',
                'application/msword',  # .doc
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
                'text/plain',  # .txt
                'image/jpeg',  # .jpg, .jpeg
                'image/png',  # .png
            ]

            if uploaded_file.content_type not in allowed_types:
                raise forms.ValidationError(
                    f"Недопустимый формат файла. Разрешены: PDF, Word (doc/docx), TXT, JPG, PNG."
                )

            max_upload_size = 20 * 1024 * 1024  # 20 MB
            if uploaded_file.size > max_upload_size:
                raise forms.ValidationError(
                    f"Размер файла не должен превышать {max_upload_size / (1024 * 1024):.0f} MB.")

        return uploaded_file