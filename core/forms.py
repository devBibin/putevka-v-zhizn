from django import forms

class SendNotificationForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea, label="Текст оповещения")