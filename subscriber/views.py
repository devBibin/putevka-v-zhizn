from django.shortcuts import render, redirect
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

from .forms import EmailSubscriberForm
from .models import EmailSubscriber

def _abs_url(request, path: str) -> str:
    return request.build_absolute_uri(path)

def announce(request):
    if request.method == "POST":
        form = EmailSubscriberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            subscriber, _ = EmailSubscriber.objects.get_or_create(email=email)
            request.session["thanks_email"] = email
            return redirect("thanks_subscribe")
    else:
        form = EmailSubscriberForm()

    return render(request, "announce.html", {"form": form})

def thanks(request):
    email = request.session.pop("thanks_email", None)
    if email is None:
        return redirect("announce")
    return render(request, "thanks.html", {"username": email})