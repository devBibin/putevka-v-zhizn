from django import forms

from core.models import MotivationLetter
from documents.models import Document
from review_by_tutor.models import Interview, TestAssignment
from scholar_form.models import UserInfo, ScholarVideo


class StatusChangeForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = ["status", "profile"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "profile": forms.Select(attrs={"class": "form-select"}),
        }


class ProfileChangeForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = ["profile"]
        widgets = {
            "profile": forms.Select(attrs={"class": "form-select"}),
        }


class MotivationLetterStaffForm(forms.ModelForm):
    class Meta:
        model = MotivationLetter
        fields = ["admin_score", "admin_rating",]
        widgets = {
            "admin_rating": forms.Textarea(attrs={
                "rows": 6,
                "class": "form-control",
                "placeholder": "Ваши комментарии/оценка для соискателя"
            }),
        }
        labels = {
            "admin_score": "Оценка администратора",
            "admin_rating": "Фидбэк администратора",
        }


class UserInfoStaffForm(forms.ModelForm):
    class Meta:
        model = UserInfo
        fields = ["tutor_summary", "is_done"]
        widgets = {
            "tutor_summary": forms.Textarea(attrs={
                "rows": 8,
                "class": "form-control",
                "placeholder": "Заметки/фидбэк куратора для участника."
            }),
        }
        labels = {
            "tutor_summary": "Заметки куратора (фидбэк)",
            "is_done": "Анкета принята (галочка)",
        }


class ScholarVideoStaffForm(forms.ModelForm):
    class Meta:
        model = ScholarVideo
        fields = ["review", "score"]
        widgets = {
            "review": forms.Textarea(attrs={
                "rows": 8,
                "class": "form-control",
                "placeholder": "Фидбэк/отзыв куратора по видеовизитке"
            }),
            "score": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "step": 1,
                "placeholder": "Баллы (целое число)"
            }),
        }
        labels = {
            "review": "Отзыв",
            "score": "Оценка в баллах",
        }


class DocumentModerationForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["status", "only_staff_comment"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "only_staff_comment": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }
        labels = {
            "status": "Статус",
            "only_staff_comment": "Комментарий только для сотрудников"
        }


class DocumentAttachForm(forms.Form):
    MODE_CHOICES = (("set", "Заменить список"), ("add", "Добавить к списку"))
    documents_to_attach = forms.ModelMultipleChoiceField(
        queryset=Document.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Прикрепить к этому документу",
    )
    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="set", widget=forms.RadioSelect, label="Режим")
    mirror = forms.BooleanField(required=False, initial=True, label="Синхронизировать в обе стороны")

    def __init__(self, *args, user=None, exclude_document=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Document.objects.filter(user=user, is_deleted=False)
        if exclude_document:
            qs = qs.exclude(pk=exclude_document.pk)
        self.fields["documents_to_attach"].queryset = qs.order_by("-uploaded_at")


class DocumentStaffUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "caption", "status", "only_staff_comment"]
        widgets = {
            "caption": forms.TextInput(attrs={"class": "form-control", "placeholder": "Название/подпись документа"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "only_staff_comment": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
        labels = {
            "file": "Файл",
            "caption": "Подпись",
            "status": "Статус",
            "only_staff_comment": "Комментарий только для сотрудников",
        }

    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control"}))


class DocumentStatusForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["status"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select form-select-sm auto-submit"}),
        }
        labels = {"status": "Статус"}


class DocumentCommentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["only_staff_comment"]
        widgets = {
            "only_staff_comment": forms.Textarea(attrs={
                "rows": 2,
                "class": "form-control form-control-sm",
                "placeholder": "Внутренний комментарий",
            }),
        }
        labels = {"only_staff_comment": "Комментарий (только для сотрудников)"}


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["notes", "filled_form", "video"]
        widgets = {
            "filled_form": forms.FileInput(),
        }


class TestAssignmentCreateForm(forms.ModelForm):
    class Meta:
        model = TestAssignment
        fields = ("user", "title", "external_url", "instructions", "due_at", "status")
        widgets = {
            "due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }


class TestAssignmentEditForm(forms.ModelForm):
    class Meta:
        model = TestAssignment
        fields = ("title", "external_url", "instructions", "due_at", "status")


class TestResultForm(forms.ModelForm):
    class Meta:
        model = TestAssignment
        fields = ("result_score", "result_text", "passed", "percentile")
        widgets = {
            "result_text": forms.Textarea(attrs={"rows": 4}),
            "percentile": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
        }

class LetterRevisionForm(forms.Form):
    revision_comment = forms.CharField(
        label="Комментарий для соискателя",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=True
    )


from django import forms
from core.models import MotivationLetterRubricReview

class DeadlineForm(forms.ModelForm):
    class Meta:
        model = MotivationLetter
        fields = ("deadline_at",)


class MotivationLetterRubricReviewStaffForm(forms.ModelForm):
    class Meta:
        model = MotivationLetterRubricReview
        fields = [
            # computed/meta
            "total_score",
            "word_count",

            # content
            "specialty_choice",
            "university_choice",
            "current_preparation",
            "next_year_plan",
            "higher_ed_value",
            "support_criticality",

            # rhetoric
            "composition",
            "style_precision",

            # literacy
            "orthography",
            "syntax",

            # extractions
            "family",
            "hobbies",
            "achievements",
            "traits",
            "school_teachers",
            "prep_subjects",
            "specialty",
            "preferred_universities",
            "relocation",
            "olympiads",
            "motivation",
            "help_criticality",
            "extra",

            # justification
            "justification",
        ]
        widgets = {
            "justification": forms.Textarea(attrs={"rows": 6}),
            "family": forms.Textarea(attrs={"rows": 2}),
            "hobbies": forms.Textarea(attrs={"rows": 2}),
            "achievements": forms.Textarea(attrs={"rows": 2}),
            "traits": forms.Textarea(attrs={"rows": 2}),
            "school_teachers": forms.Textarea(attrs={"rows": 2}),
            "prep_subjects": forms.Textarea(attrs={"rows": 2}),
            "specialty": forms.Textarea(attrs={"rows": 2}),
            "preferred_universities": forms.Textarea(attrs={"rows": 2}),
            "relocation": forms.Textarea(attrs={"rows": 2}),
            "olympiads": forms.Textarea(attrs={"rows": 2}),
            "motivation": forms.Textarea(attrs={"rows": 2}),
            "help_criticality": forms.Textarea(attrs={"rows": 2}),
            "extra": forms.Textarea(attrs={"rows": 2}),
        }
