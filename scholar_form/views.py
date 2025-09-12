import os

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

import config
from Putevka import settings
from scholar_form.forms import UserProfileForm
from scholar_form.models import UserInfo


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

    return render(request, "personal_info.html", {"form": form, "active": "personal_info"})


@login_required
def video_task(request):
    last = request.user.video_submissions.order_by("-created_at").first()
    return render(request, "video_task.html", {
        "last_submission": last,
        "bot_link": f"https://t.me/{config.TG_BOT_USERS_USERNAME}",
        "media_url": settings.MEDIA_URL,
        "active": "video_task",
    })