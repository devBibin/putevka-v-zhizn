from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from core.decorators import ensure_registration_gate
from review_by_tutor.models import TestAssignment
from scholar_form.forms import UserProfileForm, ScholarVideoForm
from scholar_form.models import UserInfo


@ensure_registration_gate('protected')
@login_required
def personal_info(request):
    profile, _ = UserInfo.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("personal_info")
    else:
        form = UserProfileForm(instance=profile)

    return render(request, "personal_info.html", {"form": form, "active": "personal_info", 'profile': profile})


@ensure_registration_gate('protected')
@login_required
def my_video_page(request):
    instance = getattr(request.user, "scholar_video", None)
    if request.method == "POST":
        form = ScholarVideoForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "Видеовизитка сохранена.")
            return redirect("my_video_page")
        else:
            messages.error(request, "Проверь форму. Видео должно быть MP4/WebM и не слишком большим.")
    else:
        form = ScholarVideoForm(instance=instance)
    return render(request, "video_task.html", {"form": form, "video": instance, 'active': 'my_video_page'})


@login_required
def test_assignment_complete(request, pk):
    assignment = get_object_or_404(TestAssignment, pk=pk, user=request.user)

    if request.method == "POST":
        assignment.mark_completed()
        assignment.result_filled_by = None
        assignment.result_filled_at = None
        assignment.save()
        return redirect(reverse("candidate_testing_list"))

    return redirect(reverse("candidate_testing_list"))
