from django import forms
from django.shortcuts import redirect

from .models import UserInfo
from formtools.wizard.views import SessionWizardView

class PersonalForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = [
            'full_name', 'birth_date', 'region', 'address'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Иванов Иван Иванович'}),
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'region': forms.TextInput(attrs={'placeholder': 'Московская область'}),
            'address': forms.TextInput(attrs={'placeholder': 'ул. Ленина, д. 1, кв. 2'}),
        }


class EducationForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = [
            'school_name', 'school_address', 'class_teacher', 'next_year_class',
            'class_profile', 'planned_exams', 'subject_grades'
        ]
        widgets = {
            'school_name': forms.TextInput(attrs={'placeholder': 'МБОУ СОШ №1'}),
            'school_address': forms.TextInput(attrs={'placeholder': 'г. Москва, ул. Школьная, 5'}),
            'class_teacher': forms.TextInput(attrs={'placeholder': 'Петрова Мария Ивановна, +7 (999) 123-45-67'}),
            'next_year_class': forms.TextInput(attrs={'placeholder': '11А'}),
            'class_profile': forms.TextInput(attrs={'placeholder': 'Физико-математический'}),
            'planned_exams': forms.Textarea(attrs={'placeholder': 'Математика, Русский язык, Физика'}),
            'subject_grades': forms.Textarea(attrs={'placeholder': 'Математика — 5, Физика — 4'}),
        }


class AdmissionForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = [
            'olympiad_plans', 'admission_path', 'target_universities', 'specializations'
        ]
        widgets = {
            'olympiad_plans': forms.Textarea(attrs={'placeholder': 'Планирую участвовать в ВОШ, ЯП, Ломоносов'}),
            'admission_path': forms.Textarea(attrs={'placeholder': 'Через ЕГЭ, возможно через олимпиаду'}),
            'target_universities': forms.Textarea(attrs={'placeholder': 'МГУ, ВШЭ, МФТИ'}),
            'specializations': forms.Textarea(attrs={'placeholder': 'Прикладная математика, инженерия'}),
        }


class FamilyForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = [
            'mother', 'father', 'legal_guardian', 'siblings_count', 'siblings_info',
            'family_size', 'income_per_member', 'is_low_income', 'receives_subsidy',
            'other_factors', 'has_pc_with_internet'
        ]
        widgets = {
            'mother': forms.Textarea(attrs={'placeholder': 'Иванова Наталья Петровна, врач, ГКБ №1'}),
            'father': forms.Textarea(attrs={'placeholder': 'Иванов Пётр Сергеевич, инженер, Газпром'}),
            'legal_guardian': forms.Textarea(attrs={'placeholder': 'Не заполняется, если не актуально'}),
            'siblings_count': forms.NumberInput(attrs={'placeholder': '1'}),
            'siblings_info': forms.Textarea(attrs={'placeholder': 'Брат — Иван, 20 лет, студент'}),
            'family_size': forms.NumberInput(attrs={'placeholder': '4'}),
            'income_per_member': forms.TextInput(attrs={'placeholder': '15 000'}),
            'is_low_income': forms.TextInput(attrs={'placeholder': 'Да / Нет'}),
            'receives_subsidy': forms.TextInput(attrs={'placeholder': 'Пособие на ребёнка'}),
            'other_factors': forms.Textarea(attrs={'placeholder': 'Семья арендует жильё, инвалидность'}),
            'has_pc_with_internet': forms.TextInput(attrs={'placeholder': 'Да / Нет'}),
        }


class AdditionalForm(forms.ModelForm):
    agree_processing = forms.BooleanField(label="Согласен(на) на обработку персональных данных")
    agree_documents = forms.BooleanField(label="Обязуюсь предоставить подтверждающие документы")

    class Meta:
        model = UserInfo
        fields = [
            'achievements', 'preparation_plan', 'foundation_help',
            'heard_about_program', 'willing_to_participate',
            'agree_processing', 'agree_documents'
        ]
        widgets = {
            'achievements': forms.Textarea(attrs={'placeholder': 'Призёр олимпиады по физике, волонтёрство'}),
            'preparation_plan': forms.Textarea(attrs={'placeholder': 'Хожу на курсы, решаю задачи'}),
            'foundation_help': forms.Textarea(attrs={'placeholder': 'Поддержка в подготовке, менторство'}),
            'heard_about_program': forms.TextInput(attrs={'placeholder': 'Через учителя'}),
            'willing_to_participate': forms.TextInput(attrs={'placeholder': 'Да / Нет'}),
        }


FORMS = [
    ("step1", PersonalForm),
    ("step2", EducationForm),
    ("step3", AdmissionForm),
    ("step4", FamilyForm),
    ("step5", AdditionalForm),
]

TEMPLATES = {
    "step1": "step1.html",
    "step2": "step2.html",
    "step3": "step3.html",
    "step4": "step4.html",
    "step5": "step5.html",
}

class ApplicationWizard(SessionWizardView):
    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_instance(self, step):
        if not hasattr(self, 'user_info_instance'):
            try:
                self.user_info_instance = UserInfo.objects.get(user=self.request.user)
            except UserInfo.DoesNotExist:
                self.user_info_instance = UserInfo(user=self.request.user)
        return self.user_info_instance

    def done(self, form_list, **kwargs):
        instance = self.get_form_instance(None)
        for form in form_list:
            for field, value in form.cleaned_data.items():
                setattr(instance, field, value)
        instance.save()
        return redirect('thank_you')


class UserInfoForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = "__all__"
        widgets = {
            # Step 1: Address
            'region': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'address': forms.Textarea(attrs={'rows': 2, 'cols': 80}),

            # Step 2: Education
            'school_address': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'class_teacher': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'planned_exams': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'subject_grades': forms.Textarea(attrs={'rows': 2, 'cols': 80}),

            # Step 3: Admission
            'olympiad_plans': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'admission_path': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'target_universities': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'specializations': forms.Textarea(attrs={'rows': 2, 'cols': 80}),

            # Step 4: Family
            'mother': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'father': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'legal_guardian': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'siblings_info': forms.Textarea(attrs={'rows': 2, 'cols': 80}),
            'other_factors': forms.Textarea(attrs={'rows': 2, 'cols': 80}),

            # Step 5: Additional
            'achievements': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'preparation_plan': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'foundation_help': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
        }