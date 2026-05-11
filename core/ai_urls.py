from django.urls import path

from core import ai_views

urlpatterns = [
    path("tasks/claim/", ai_views.claim_task, name="ai_task_claim"),
    path("tasks/<uuid:task_id>/heartbeat/", ai_views.heartbeat, name="ai_task_heartbeat"),
    path("tasks/<uuid:task_id>/complete/", ai_views.complete, name="ai_task_complete"),
    path("tasks/<uuid:task_id>/fail/", ai_views.fail, name="ai_task_fail"),
    path("files/<path:token>/", ai_views.download_file, name="ai_file_download"),
]
