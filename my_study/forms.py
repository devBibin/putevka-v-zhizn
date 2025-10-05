from django import forms
from .models import CourseSelection, UniversityPriority, AssessmentResult, Subject


class CourseFilterForm(forms.Form):
    school = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={"hidden": True}))
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(), required=False, empty_label="Все предметы"
    )
    q = forms.CharField(required=False, label="Поиск", widget=forms.TextInput(attrs={
        "placeholder": "Название курса…"
    }))


class CourseSelectionForm(forms.ModelForm):
    class Meta:
        model = CourseSelection
        fields = ["motivation"]
        widgets = {
            "motivation": forms.Textarea(attrs={"rows": 6, "placeholder": "Почему вы выбрали этот курс?"})
        }


class UniversityPriorityForm(forms.ModelForm):
    class Meta:
        model = UniversityPriority
        fields = ["university", "priority", "notes"]
        widgets = {
            "priority": forms.Select(choices=[(i, str(i)) for i in range(1, 6)]),
            "notes": forms.Textarea(attrs={"rows": 6, "placeholder": "Почему вы выбрали этот вуз?"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        user = self.user
        pr = cleaned.get("priority")
        uni = cleaned.get("university")

        if user is not None and pr is not None:
            qs = UniversityPriority.objects.filter(user=user, priority=pr)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists() and not qs.filter(university=uni).exists():
                self.add_error("priority", "Этот приоритет уже занят другим вузом.")

        return cleaned


class AssessmentResultForm(forms.ModelForm):
    class Meta:
        model = AssessmentResult
        fields = ["kind", "subject", "title", "date", "score", "max_score", "place", "notes", "attachment"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"})
        }
