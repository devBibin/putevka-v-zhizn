from django.urls import path

from . import views

urlpatterns = [
    path("letters/<int:user_id>/", views.staff_letter_detail, name="staff_letter_detail"),
    path("profiles/<int:user_id>/", views.staff_profile_detail, name="staff_profile_detail"),
    path("staff/video/<int:user_id>/", views.staff_video_detail, name="staff_video_detail"),
    path("staff/documents/<int:user_id>/", views.staff_documents_detail, name="staff_documents_detail"),
]
