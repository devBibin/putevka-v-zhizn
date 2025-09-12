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


class AssessmentResultForm(forms.ModelForm):
    class Meta:
        model = AssessmentResult
        fields = ["kind", "subject", "title", "date", "score", "max_score", "place", "notes", "attachment"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"})
        }
