from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from core.decorators import ensure_registration_gate
from django.utils import timezone
from review_by_tutor.models import TestAssignment
from review_by_tutor.utils.selection_stages import require_selection_step
from scholar_form.forms import UserProfileForm, ScholarVideoForm, UserPersonalDataForm
from scholar_form.models import UserInfo, UserPersonalData, ScholarVideo, VideoInstruction


@ensure_registration_gate('protected')
@login_required
def personal_info(request):
    profile, _ = UserInfo.objects.get_or_create(user=request.user)
    personal_data, _ = UserPersonalData.objects.get_or_create(user=request.user)

    planned_exams_qs = profile.planned_exams.all()
    planned_exams_labels = [str(x) for x in planned_exams_qs]

    if request.method == "POST":
        print("FILES:", request.FILES)
        print("avatar:", request.FILES.get("avatar"))

        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        personal_form = UserPersonalDataForm(request.POST, request.FILES, instance=personal_data)

        if profile_form.is_valid() and personal_form.is_valid():
            profile_form.save()
            personal_form.save()
            return redirect("personal_info")
    else:
        profile_form = UserProfileForm(instance=profile)
        personal_form = UserPersonalDataForm(instance=personal_data)

    return render(
        request,
        "personal_info.html",
        {
            "form": profile_form,
            "personal_form": personal_form,
            "active": "personal_info",
            "profile": profile,
            "planned_exams_labels": planned_exams_labels,
        },
    )

@ensure_registration_gate('protected')
@require_selection_step(UserInfo.SelectionStep.VIDEO)
@login_required
def my_video_page(request):
    instance, _ = ScholarVideo.objects.get_or_create(user=request.user)
    video_instruction = VideoInstruction.get_current()

    if request.method == "POST":
        form = ScholarVideoForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "Данные по видеовизитке сохранены.")
            return redirect("my_video_page")
        else:
            messages.error(request, "Проверь форму. Видео должно быть MP4/WebM, а график — PDF/DOC/DOCX.")
    else:
        form = ScholarVideoForm(instance=instance)

    return render(
        request,
        "video_task.html",
        {
            "form": form,
            "video": instance,
            "video_instruction": video_instruction,
            "active": "my_video_page",
            "now": timezone.now(),
        },
    )


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


@login_required
def form_step_entry(request):
    user_obj = request.user
    uinfo, _ = UserInfo.objects.get_or_create(user=user_obj)

    return render(
        request,
        "stage_locked.html",
        {
            "user_obj": user_obj,
            "uinfo": uinfo,
        },
    )