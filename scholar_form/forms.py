from django import forms
from django.contrib import messages
from django.db import transaction
from django.dispatch import Signal
from django.forms import HiddenInput
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.db import models
from formtools.wizard.views import SessionWizardView

from my_study.models import Subject
from .models import UserInfo, ScholarVideo, UserPersonalData


def _sync_user_from_userinfo(userinfo: UserInfo):
    user = getattr(userinfo, "user", None)
    if not user:
        return
    updated_fields = []

    if userinfo.first_name and user.first_name != userinfo.first_name:
        user.first_name = userinfo.first_name
        updated_fields.append("first_name")

    if userinfo.last_name and user.last_name != userinfo.last_name:
        user.last_name = userinfo.last_name
        updated_fields.append("last_name")

    if userinfo.email and user.email != userinfo.email:
        user.email = userinfo.email
        updated_fields.append("email")

    if updated_fields:
        user.save(update_fields=updated_fields)


wizard_done = Signal()


class PersonalForm(forms.ModelForm):
    birth_date = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        ),
        input_formats=['%Y-%m-%d'],
        label='Дата рождения',
        required=True,
        help_text="От рождества Христова"
    )

    class Meta:
        model = UserInfo
        fields = [
            'last_name', 'first_name', 'middle_name', 'gender', 'birth_date', 'region', 'city', 'address'
        ]
        widgets = {
            'last_name': forms.TextInput(attrs={'placeholder': 'Иванов'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Иван'}),
            'middle_name': forms.TextInput(attrs={'placeholder': 'Иванович'}),
            'gender': forms.Select(
                attrs={'class': 'form-control'},
                choices=[('', '— Выберите пол —')] + UserInfo.GENDERS
            ),
            'region': forms.TextInput(attrs={'placeholder': 'Московская область'}),
            'city': forms.TextInput(attrs={'placeholder': 'Город N'}),
            'address': forms.TextInput(attrs={'placeholder': 'ул. Ленина, д. 1, кв. 2'}),
        }
        help_texts = {
            'middle_name': 'при наличии'
        }


class EducationForm(forms.ModelForm):
    class_teacher = forms.CharField(
        widget=forms.TextInput(
            attrs={'placeholder': 'Петрова Мария Ивановна, +7 (999) 123-45-67'}
        ),
        label='Классный руководитель',
        required=True,
        help_text="ФИО, телефон, email"
    )

    subject_grades = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Математика — 5, Физика — 4'}),
        help_text="в т.ч.: Русский язык, Алгебра, Геометрия, Биология, Химия, Физика, Иностранный язык, Информатика",
        required=True,
        label='Средние оценки по предметам'
    )

    planned_exams = forms.ModelMultipleChoiceField(
        label="Планируемые экзамены",
        queryset=Subject.objects.all(),
        required=False,
        widget=forms.SelectMultiple()
    )

    class Meta:
        model = UserInfo
        fields = [
            'school_name',
            'school_address',
            'class_teacher',
            'next_year_class_digit',
            'class_profile',
            'planned_exams',
            'subject_grades',

            'avg_grade_last_period',
            'avg_russian_last_2_periods',
            'avg_math_last_2_periods',
            'avg_profile_subjects_last_2_periods',
        ]

        widgets = {
            'school_name': forms.TextInput(attrs={'placeholder': 'МБОУ СОШ №1'}),
            'school_address': forms.TextInput(attrs={'placeholder': 'г. Москва, ул. Школьная, 5'}),
            'class_profile': forms.TextInput(attrs={'placeholder': 'Физико-математический'}),
            'subject_grades': forms.Textarea(attrs={'placeholder': 'Математика — 5, Физика — 4'}),

            'avg_grade_last_period': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '1',
                'max': '10',
                'placeholder': 'Например: 4.75'
            }),
            'avg_russian_last_2_periods': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '1',
                'max': '10',
                'placeholder': 'Например: 4.80'
            }),
            'avg_math_last_2_periods': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '1',
                'max': '10',
                'placeholder': 'Например: 4.60'
            }),
            'avg_profile_subjects_last_2_periods': forms.TextInput(attrs={'placeholder': 'География - 4.9, ...'}),
        }

        help_texts = {
            'avg_grade_last_period': 'Средний балл за последнюю четверть / семестр.',
            'avg_profile_subjects_last_2_periods': 'Профильные предметы — важные для выбранного направления.',
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
        help_texts = {
            'specializations': 'Мы не требуем от тебя железного решения уже сейчас. Но наверняка у тебя есть примерный '
                               'перечень специальностей, о которых ты задумывался. Укажи в заявке те направления, '
                               'которые тебе были бы интересны.',
            'target_universities': 'Список наиболее приоритетных ВУЗов, в которые планируешь поступать (не более 5).\nНаименование, город, факультет.\nМы не требуем от тебя железного решения уже сейчас. Укажи те вузы, о которых ты слышал, что они выпускают специалистов твоего направления; те вузы, в которых ты хотел бы учиться.'
        }


class FamilyForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = [
            'mother',
            'father',
            'legal_guardian',
            'siblings_count',
            'siblings_info',
            'family_size',
            'income_per_member',
            'is_low_income',
            'receives_subsidy',

            'family_material_status',

            'other_factors',
            'has_pc_with_internet'
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

            'family_material_status': forms.Select(attrs={
                'class': 'form-control'
            }),

            'other_factors': forms.Textarea(attrs={'placeholder': 'Семья арендует жильё, инвалидность'}),
            'has_pc_with_internet': forms.TextInput(attrs={'placeholder': 'Да / Нет'}),
        }

        help_texts = {
            'receives_subsidy': 'Если да, то на каком основании?',
            'family_material_status': 'Оцените общее материальное положение вашей семьи.',
            'income_per_member': 'Сложи годовой доход «на руки» каждого родителя, раздели на 12 и затем на число членов семьи.',
        }


class AdditionalForm(forms.ModelForm):
    agree_processing = forms.BooleanField(label="Согласен(на) на обработку персональных данных")
    agree_documents = forms.BooleanField(label="Обязуюсь предоставить подтверждающие документы")

    class Meta:
        model = UserInfo
        fields = [
            'vk', 'achievements', 'preparation_plan', 'foundation_help',
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
    def _get_model_fields(self):
        normal = set()
        m2m = set()
        for f in UserInfo._meta.get_fields():
            if f.auto_created and not f.concrete:
                continue
            if isinstance(f, models.ManyToManyField):
                m2m.add(f.name)
            elif getattr(f, "attname", None):
                normal.add(f.name)
        return normal, m2m

    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_instance(self, step):
        if not hasattr(self, 'user_info_instance'):
            try:
                self.user_info_instance = UserInfo.objects.get(user=self.request.user)
            except UserInfo.DoesNotExist:
                self.user_info_instance = UserInfo(user=self.request.user)
        return self.user_info_instance

    def get_form(self, step=None, data=None, files=None):
        form = super().get_form(step, data, files)

        instance = self.get_form_instance(step or self.steps.current)

        locked = getattr(instance, "form_status", "draft") in {"submitted", "approved"}

        if locked:
            for name, field in form.fields.items():
                if isinstance(field.widget, HiddenInput):
                    continue
                field.disabled = True
                field.required = False
                if hasattr(field.widget, "attrs"):
                    field.widget.attrs.pop("required", None)
            return form

        required_false_list = ['legal_guardian', 'vk', 'middle_name']
        for name, field in form.fields.items():
            if name in required_false_list:
                field.required = False
                if hasattr(field.widget, 'attrs'):
                    field.widget.attrs.pop('required', None)
                continue

            field.required = True
            if hasattr(field.widget, 'attrs') and not isinstance(field.widget, HiddenInput):
                field.widget.attrs['required'] = ''

        return form

    def get_form_initial(self, step):
        instance = self.get_form_instance(step)
        initial = {}
        form_class = self.form_list[step]
        model_fields = {f.name for f in UserInfo._meta.get_fields() if getattr(f, 'attname', None)}
        for name in form_class.base_fields.keys():
            if name in model_fields:
                val = getattr(instance, name, None)

                if hasattr(val, "all") and hasattr(val, "values_list"):
                    val = list(val.values_list("pk", flat=True))

                initial[name] = val
        return initial

    @transaction.atomic
    def process_step(self, form):
        instance = self.get_form_instance(self.steps.current)
        normal_fields, m2m_fields = self._get_model_fields()

        m2m_to_set = {}

        for field, value in form.cleaned_data.items():
            if field in normal_fields:
                setattr(instance, field, value)
            elif field in m2m_fields:
                m2m_to_set[field] = value

        instance.save()

        for field, value in m2m_to_set.items():
            getattr(instance, field).set(value or [])

        _sync_user_from_userinfo(instance)
        return super().process_step(form)

    def done(self, form_list, **kwargs):
        instance = self.get_form_instance(None)
        normal_fields, m2m_fields = self._get_model_fields()

        m2m_to_set = {}

        for form in form_list:
            for field, value in form.cleaned_data.items():
                if field in normal_fields:
                    setattr(instance, field, value)
                elif field in m2m_fields:
                    m2m_to_set[field] = value

        instance.form_status = "submitted"
        wizard_done.send(sender=self.__class__, instance=instance, forms=form_list)
        instance.save()

        for field, value in m2m_to_set.items():
            getattr(instance, field).set(value or [])

        _sync_user_from_userinfo(instance)
        return redirect('thank_you')

    def post(self, *args, **kwargs):
        request = self.request
        is_autosave = request.POST.get("_autosave") == "1"

        if is_autosave:
            form = self.get_form(data=request.POST, files=request.FILES, step=self.steps.current)
            for f in form.fields.values():
                f.required = False

            if form.is_valid():
                instance = self.get_form_instance(self.steps.current)
                normal_fields, m2m_fields = self._get_model_fields()

                m2m_to_set = {}
                for field, value in form.cleaned_data.items():
                    if field in normal_fields:
                        setattr(instance, field, value)
                    elif field in m2m_fields:
                        m2m_to_set[field] = value

                instance.save()
                for field, value in m2m_to_set.items():
                    getattr(instance, field).set(value or [])

                _sync_user_from_userinfo(instance)

                from django.http import HttpResponse
                return HttpResponse(status=204)

            return self.render(self.get_form_step_data(form))

        return super().post(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)

        instance = self.get_form_instance(self.steps.current)
        locked = instance.form_status in {"submitted", "approved"}

        step = request.GET.get("step")
        if locked and step:
            all_steps = list(self.get_form_list().keys())
            if step in all_steps:
                self.storage.current_step = step
                return self.render(self.get_form(step=step))

        return response

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["active"] = "apply"
        return context

    def is_locked(self) -> bool:
        instance = self.get_form_instance(self.steps.current)
        return getattr(instance, "form_status", "draft") in {"submitted", "approved"}

    def dispatch(self, request, *args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            instance = self.get_form_instance(getattr(self, "steps", None).current if hasattr(self, "steps") else None)

            locked = getattr(instance, "form_status", "draft") in {"submitted", "approved"}

            if locked:
                if request.POST.get("_autosave") == "1":
                    return HttpResponseForbidden()

                messages.error(request, "Анкета уже отправлена и не может быть изменена.")
                return redirect("thank_you")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        instance = self.get_form_instance(self.steps.current)
        context["active"] = "apply"
        context["is_locked"] = getattr(instance, "form_status", "draft") in {"submitted", "approved"}
        return context


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


class UserProfileForm(forms.ModelForm):
    avatar = forms.ImageField(required=False, widget=forms.FileInput(attrs={"accept": "image/*"}))

    class Meta:
        model = UserInfo
        fields = ["avatar"]


class ScholarVideoForm(forms.ModelForm):
    class Meta:
        model = ScholarVideo
        fields = ["file"]

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            raise forms.ValidationError("Нужно выбрать видеофайл.")
        return f


class UserPersonalDataForm(forms.ModelForm):
    class Meta:
        model = UserPersonalData
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "passport_series",
            "passport_number",
            "passport_issued_at",
            "passport_issued_by",
            "passport_department_code",
            "registration_address",
            "bank_name",
            "bank_account",
            "bank_bik",
            "bank_correspondent_account",
            "phone",
            "email",
            "inn",
        ]
        widgets = {
            "passport_issued_at": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "registration_address": forms.Textarea(attrs={"rows": 2}),
        }
