from django import forms
from .models import EmailSubscriber

class EmailSubscriberForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "you@example.com",
            "autocomplete": "email",
            "required": True,
        })
    )