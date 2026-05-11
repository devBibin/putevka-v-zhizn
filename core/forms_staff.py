from django import forms

class SetVideoScoreForm(forms.Form):
    score = forms.IntegerField(min_value=0, max_value=100, required=False, label="Баллы (0–100)")
    review = forms.CharField(widget=forms.Textarea, required=False, label="Короткий отзыв")

class SendNotificationForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Сообщение")

DOC_STATUSES = [
    ('PENDING', 'На проверке'),
    ('APPROVED', 'Подтверждено'),
    ('QUESTION', 'Уточнить'),
    ('PENDING_SIGNATURE', 'Ожидает подписи'),
    ('SIGNED', 'Подписан'),
    ('REJECTED_SIGNATURE', 'Подпись отклонена'),
]

class UploadStaffDocForm(forms.Form):
    file = forms.FileField(label="Файл")
    caption = forms.CharField(max_length=255, label="Название/подпись")
    status = forms.ChoiceField(choices=DOC_STATUSES, initial='PENDING', label="Статус")
