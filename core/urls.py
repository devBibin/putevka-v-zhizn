from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('registration-pending/', views.registration_pending_view, name='registration_pending'),
    path('telegram/activate/<uuid:token>/', views.telegram_activate_view, name='telegram_activate'),
    path('bot/<str:bot_token>/', views.webhook, name='bot'),
]
