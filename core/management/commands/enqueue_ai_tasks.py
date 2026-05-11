from django.core.management.base import BaseCommand

from core.ai_tasks import (
    enqueue_interview_result_fill,
    enqueue_interview_transcription,
    enqueue_motivation_letter_review,
    enqueue_scholar_video_transcription,
)
from core.models import MotivationLetter
from review_by_tutor.models import Interview
from scholar_form.models import ScholarVideo


class Command(BaseCommand):
    help = "Enqueue pending asynchronous AI tasks for existing domain objects."

    def handle(self, *args, **options):
        created = 0

        for letter in MotivationLetter.objects.filter(status=MotivationLetter.Status.SUBMITTED).exclude(letter_text__exact=""):
            if enqueue_motivation_letter_review(letter):
                created += 1

        for interview in Interview.objects.exclude(video__exact="").filter(transcript_status__in=["PENDING", "FAILED"]):
            if enqueue_interview_transcription(interview):
                created += 1

        for interview in Interview.objects.filter(transcript_status="DONE", ai_fill_status__in=["PENDING", "FAILED"]):
            if enqueue_interview_result_fill(interview):
                created += 1

        for video in ScholarVideo.objects.filter(transcript_status__in=["PENDING", "FAILED"]):
            if enqueue_scholar_video_transcription(video):
                created += 1

        self.stdout.write(self.style.SUCCESS(f"AI task enqueue pass finished, touched={created}"))
