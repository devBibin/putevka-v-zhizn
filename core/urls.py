from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_initial, name='register_initial'),
    path('register/verify-email/', views.verify_email, name='verify_email'),
    path('register/resend-email-code/', views.resend_email_code, name='resend_email_code'),
    path('register/connect-telegram/', views.connect_telegram, name='connect_telegram'),
    path('register/skip-telegram/', views.skip_telegram, name='skip_telegram'),
    path('register/verify-phone/', views.verify_phone_if_needed, name='verify_phone_if_needed'),
    path('register/verify-phone-code/', views.verify_phone_code, name='verify_phone_code'),
    path('register/resend-phone-code/', views.resend_phone_code, name='resend_phone_code'),
    path('register/complete/', views.finish_registration, name='finish_registration'),
    path('bot/<str:bot_token>/', views.webhook, name='bot'),
]
