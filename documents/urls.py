from django.urls import path
from . import views

urlpatterns = [
    path('', views.documents_dashboard, name='documents_dashboard'),
    path('delete/<int:document_id>/', views.delete_document, name='delete_document'),
    path('view/<int:document_id>/', views.serve_document, name='serve_document'),
]