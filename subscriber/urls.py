from django.urls import path
from . import views

urlpatterns = [
    path("announce/", views.announce, name="announce"),
    path("thanks/", views.thanks, name="thanks_subscribe"),
]
