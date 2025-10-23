import os

from django.contrib.auth.decorators import login_required
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import render, redirect
from django.utils.encoding import smart_str
from django.contrib import messages

import config
from Putevka import settings
from core.decorators import ensure_registration_gate
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