from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('bot/<str:code>/', views.webhook, name='bot'),
    path('notifications/', views.notification_list, name='notifications'),
    path('mark-as-seen/<int:notification_id>', views.mark_notification_as_seen, name='mark_as_seen'),
]
