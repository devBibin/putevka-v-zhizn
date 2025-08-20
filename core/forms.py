from django import forms
from .models import MotivationLetter
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import TelegramAccount
from scholar_form.models import UserInfo

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = True
        if commit:
            user.save()
            TelegramAccount.objects.create(user=user, telegram_id=None, telegram_verified=False)
        return user

class RegistrationForm(forms.Form):
    email = forms.EmailField(
        label="Ваш Email",
        max_length=255,
        widget=forms.EmailInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
        error_messages={'unique': 'Пользователь с таким email уже существует.'}
    )
    password = forms.CharField(
        label="Пароль",
        min_length=8,
        widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
        help_text="Минимум 8 символов."
    )
    password_confirm = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'})
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'Пароли не совпадают.')
        return cleaned_data

    def clean_password(self):
        password = self.cleaned_data.get("password")
        validate_password(password, user=None)
        return password

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).filter(is_active=True).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован, если вы не закончили регистрацию, попробуйте авторизоваться")
        return email

class VerifyEmailForm(forms.Form):
    code = forms.CharField(
        label="Код из письма",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'Введите 6-значный код'}),
        error_messages={'required': 'Пожалуйста, введите код.', 'min_length': 'Код должен содержать 6 цифр.', 'max_length': 'Код должен содержать 6 цифр.'}
    )

class PhoneNumberForm(forms.Form):
    phone = forms.CharField(
        label="Ваш номер телефона",
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': '+7 (XXX) XXX-XX-XX'}),
        help_text="Введите номер телефона для подтверждения по звонку."
    )

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        normalized = (
            phone.replace(' ', '')
            .replace('(', '')
            .replace(')', '')
            .replace('-', '')
        )
        if normalized.startswith('8') and len(normalized) == 11:
            normalized = '+7' + normalized[1:]
        if normalized.startswith('7') and len(normalized) == 11:
            normalized = '+7' + normalized[1:]

        if UserInfo.objects.filter(phone=normalized).exists():
            raise forms.ValidationError("Этот номер уже зарегистрирован")

        return normalized

class MotivationLetterForm(forms.ModelForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.status == MotivationLetter.Status.SUBMITTED:
            self.fields["letter_text"].disabled = True

    class Meta:
        model = MotivationLetter
        fields = ['letter_text']
        widgets = {
            'letter_text': forms.Textarea(attrs={'rows': 15, 'cols': 80, 'placeholder': 'Начните вводить текст мотивационного письма здесь...'}),
        }
        labels = {
            'letter_text': 'Мотивационное письмо',
        }

class SendNotificationForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea, label="Текст оповещения")
