import logging

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

from core.decorators import ensure_registration_gate
from .models import School, Course, CourseSelection, UniversityPriority, AssessmentResult, Subject
from .forms import CourseFilterForm, CourseSelectionForm, UniversityPriorityForm, AssessmentResultForm

logger = logging.getLogger(__name__)

@login_required
def schools_and_courses(request):
    subjects = Subject.objects.all()
    schools = School.objects.all()

    form = CourseFilterForm(request.GET or None)
    qs = Course.objects.select_related("school", "subject")

    if form.is_valid():
        subject = form.cleaned_data.get("subject")
        q = form.cleaned_data.get("q")
        school_id = request.GET.get("school")
        if subject:
            qs = qs.filter(subject=subject)
        if school_id:
            qs = qs.filter(school_id=school_id)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    paginator = Paginator(qs, 12)
    page = request.GET.get("page")
    courses = paginator.get_page(page)

    selections = (
        CourseSelection.objects
        .filter(user=request.user)
        .select_related("course__school", "course__subject")
        .order_by("-created_at")
    )

    return render(request, "study/schools.html", {
        "subjects": subjects,
        "schools": schools,
        "courses": courses,
        "filter_form": form,
        "selected_school": request.GET.get("school"),
        "selections": selections,
        "active": "study"
    })


@ensure_registration_gate('protected')
@login_required
def select_course(request, course_id):
    course = get_object_or_404(Course.objects.select_related("school", "subject"), id=course_id)
    if request.method == "POST":
        form = CourseSelectionForm(request.POST)
        if form.is_valid():
            selection, created = CourseSelection.objects.get_or_create(
                user=request.user, course=course,
                defaults={"motivation": form.cleaned_data["motivation"],
                          "need_tutor": form.cleaned_data["need_tutor"],}
            )
            if not created:
                selection.motivation = form.cleaned_data["motivation"]
                selection.need_tutor = form.cleaned_data["need_tutor"]
                selection.save()
            messages.success(request, "Ваш выбор сохранён.")
            return redirect("study:schools")
    else:
        initial = {}
        existing = CourseSelection.objects.filter(user=request.user, course=course).first()
        if existing:
            initial["motivation"] = existing.motivation
            initial["need_tutor"] = existing.need_tutor
        form = CourseSelectionForm(initial=initial)

    return render(request, "study/select_course.html", {"course": course, "form": form})


@ensure_registration_gate('protected')
@login_required
def unselect_course(request, course_id: int):
    if request.method != "POST":
        return redirect("study:schools")
    course = get_object_or_404(Course, id=course_id)
    sel = CourseSelection.objects.filter(user=request.user, course=course).first()
    if not sel:
        messages.info(request, "Этот курс не был выбран.")
        return redirect("study:schools")
    sel.delete()
    messages.success(request, "Курс удалён из выбранных.")
    return redirect("study:schools")


@ensure_registration_gate('protected')
@login_required
def universities(request):
    priorities = (UniversityPriority.objects
                  .filter(user=request.user)
                  .prefetch_related("subjects")
                  .order_by("priority"))

    if request.method == "POST":
        form = UniversityPriorityForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    spec = form.cleaned_data.get("specialty", "")

                    obj, created = UniversityPriority.objects.update_or_create(
                        user=request.user,
                        university=form.cleaned_data["university"],
                        specialty=spec,                     # 🔽 добавили в ключ
                        defaults={
                            "priority": form.cleaned_data["priority"],
                            "notes": form.cleaned_data.get("notes", ""),
                            "city": form.cleaned_data.get("city", ""),
                            "is_targeted": form.cleaned_data.get("is_targeted", False),
                        },
                    )
                    obj.subjects.set(form.cleaned_data.get("subjects") or [])
                messages.success(request, "Запись сохранена.")
                return redirect("study:universities")
            except IntegrityError:
                messages.warning(
                    request,
                    "Такой приоритет или направление уже заняты. Выберите другие значения."
                )
        else:
            messages.warning(request, "Исправьте ошибки в форме.")
    else:
        form = UniversityPriorityForm(user=request.user)

    return render(
        request,
        "study/universities.html",
        {"form": form, "priorities": priorities, "active": "study"}
    )


@login_required
def delete_university_priority(request, pk):
    obj = get_object_or_404(UniversityPriority, pk=pk, user=request.user)
    obj.delete()
    messages.info(request, "Запись удалена.")
    return redirect("study:universities")


@ensure_registration_gate('protected')
@login_required
def assessments(request):
    results = AssessmentResult.objects.filter(user=request.user).select_related("subject").order_by("-date", "-id")

    if request.method == "POST":
        form = AssessmentResultForm(request.POST, request.FILES)
        if form.is_valid():
            inst = form.save(commit=False)
            inst.user = request.user
            inst.save()
            messages.success(request, "Результат добавлен.")
            return redirect("study:assessments")
    else:
        form = AssessmentResultForm()

    return render(request, "study/assessments.html", {"form": form, "results": results, "active": "study"
})
