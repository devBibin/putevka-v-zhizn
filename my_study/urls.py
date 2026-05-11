from django.urls import path
from . import views

app_name = "study"

urlpatterns = [
    path("schools/", views.schools_and_courses, name="schools"),
    path("courses/<int:course_id>/select/", views.select_course, name="select_course"),
    path("courses/<int:course_id>/unselect/", views.unselect_course, name="unselect_course"),
    path("universities/", views.universities, name="universities"),
    path("universities/<int:pk>/delete/", views.delete_university_priority, name="delete_university_priority"),
    path("assessments/", views.assessments, name="assessments"),
]
