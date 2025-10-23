from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path

from review_by_tutor.views import testing_list_for_candidate
from scholar_form import views
from core.decorators import ensure_registration_gate
from .forms import ApplicationWizard, FORMS

urlpatterns = [
    path('apply/', ensure_registration_gate('protected')(login_required(ApplicationWizard.as_view(FORMS))), name='apply'),
    path('thank-you/', lambda request: render(request, 'thank_you.html'), name='thank_you'),
    path('personal-info/', views.personal_info, name='personal_info'),
    path("video/", views.my_video_page, name="my_video_page"),
    path("testing/", testing_list_for_candidate, name="candidate_testing_list"),

]
