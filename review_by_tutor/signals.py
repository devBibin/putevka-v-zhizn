import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.ai_tasks import enqueue_interview_result_fill, enqueue_interview_transcription
from review_by_tutor.models import Interview

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Interview)
def enqueue_interview_ai_tasks(sender, instance: Interview, **kwargs):
    try:
        enqueue_interview_transcription(instance)
        enqueue_interview_result_fill(instance)
    except Exception as e:
        logger.warning("Failed to enqueue interview AI task for %s: %s", instance.pk, e)
