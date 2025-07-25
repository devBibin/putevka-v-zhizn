from django.urls import path
from . import views
from core.bot import webhook as telegram_webhook

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('bot/<str:code>/', views.webhook, name='bot'),
    path('telegram/webhook/', telegram_webhook),
]
