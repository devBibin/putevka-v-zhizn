from django.urls import path

from core import telegram_views


urlpatterns = [
    path("updates/", telegram_views.update, name="telegram_update"),
    path("messages/claim/", telegram_views.claim_message, name="telegram_message_claim"),
    path("messages/<uuid:task_id>/complete/", telegram_views.complete_message, name="telegram_message_complete"),
    path("messages/<uuid:task_id>/fail/", telegram_views.fail_message, name="telegram_message_fail"),
]
