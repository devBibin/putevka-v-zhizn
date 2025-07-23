from django import forms
from .models import MotivationLetter

class MotivationLetterForm(forms.ModelForm):
    class Meta:
        model = MotivationLetter
        fields = ['letter_text']
        widgets = {
            'letter_text': forms.Textarea(attrs={'rows': 15, 'cols': 80, 'placeholder': 'Начните вводить текст мотивационного письма здесь...'}),
        }
        labels = {
            'letter_text': 'Мотивационное письмо',
        }

    def clean_letter_text(self):
        new_letter_text = self.cleaned_data.get('letter_text')

        if self.instance.pk:
            try:
                original_letter = MotivationLetter.objects.get(pk=self.instance.pk)
            except MotivationLetter.DoesNotExist:
                raise forms.ValidationError("Ошибка: письмо не найдено.")

            if original_letter.admin_rating:
                if new_letter_text != original_letter.letter_text:
                    raise forms.ValidationError(
                        "Невозможно изменить текст письма, так как администратор уже выставил оценку.")

        return new_letter_text