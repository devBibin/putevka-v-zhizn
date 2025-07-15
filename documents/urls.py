from django.urls import path
from . import views

urlpatterns = [
    path('', views.documents_dashboard, name='documents_dashboard'),
]