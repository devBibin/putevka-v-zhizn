from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path
from .forms import ApplicationWizard, FORMS

urlpatterns = [
    path('apply/', login_required(ApplicationWizard.as_view(FORMS)), name='apply'),
    path('thank-you/', lambda request: render(request, 'thank_you.html'), name='thank_you'),
]
