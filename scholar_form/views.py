from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

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