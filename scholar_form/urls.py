from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path

import review_by_tutor
from core.decorators import ensure_registration_gate
from review_by_tutor.views import testing_list_for_candidate
from scholar_form import views
from .forms import ApplicationWizard, FORMS

urlpatterns = [
    path('apply/', ensure_registration_gate('protected')(login_required(ApplicationWizard.as_view(FORMS))),
         name='apply'),
    path('thank-you/', lambda request: render(request, 'thank_you.html'), name='thank_you'),
    path('personal-info/', views.personal_info, name='personal_info'),
    path("video/", views.my_video_page, name="my_video_page"),
    path("video/upload-status/", views.my_video_upload_status, name="my_video_upload_status"),
    path("testing/", testing_list_for_candidate, name="candidate_testing_list"),
    path("preparation/", review_by_tutor.views.interview_preparation_view, name="preparation"),

    path("tests/complete/<int:pk>/", views.test_assignment_complete, name="test_assignment_complete"),

    path('waiting_stage/', views.form_step_entry, name='form_step_entry'),

]
