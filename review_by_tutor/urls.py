from django.urls import path

from . import views

urlpatterns = [
    path("letters/<int:user_id>/", views.staff_letter_detail, name="staff_letter_detail"),
    path("profiles/<int:user_id>/", views.staff_profile_detail, name="staff_profile_detail"),
    path("video/<int:user_id>/", views.staff_video_detail, name="staff_video_detail"),
    path("documents/<int:user_id>/", views.staff_documents_detail, name="staff_documents_detail"),
    path("study/<int:user_id>/", views.staff_study_detail, name="staff_study_detail"),
    path("notes/<int:user_id>/", views.staff_notes_by_user, name="staff_notes"),
    path("users/", views.staff_users_list, name="staff_users_list"),
]
