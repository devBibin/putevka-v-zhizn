from django.urls import path
from . import views
from .views_helper import redirect_to_current_step

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_initial, name='register_initial'),
    path('register/verify-email/', views.verify_email, name='verify_email'),
    path('register/verify-email/confirm/<str:token>/', views.verify_email_confirm, name='verify_email_confirm'),
    path('register/resend-email-code/', views.resend_email_code, name='resend_email_code'),
    path('register/connect-telegram/', views.connect_telegram, name='connect_telegram'),
    path('register/skip-telegram/', views.skip_telegram, name='skip_telegram'),
    path('register/verify-phone/', views.verify_phone_if_needed, name='verify_phone_if_needed'),
    path('register/complete/', views.finish_registration, name='finish_registration'),
    path('bot/<str:bot_token>/', views.webhook, name='bot'),

    path('register/wait-for-call/', views.wait_for_phone_call, name='wait_for_phone_call'),
    path('check-call-status/', views.check_phone_call_status, name='check_phone_call_status'),
    path('redirect-registration/', redirect_to_current_step, name='redirect_to_current_step'),
    path('change_phone_number/', views.change_phone_number, name='change_phone_number'),
    path('return_telegram_connection/', views.return_to_telegram_connection, name='return_telegram_connection'),
]
