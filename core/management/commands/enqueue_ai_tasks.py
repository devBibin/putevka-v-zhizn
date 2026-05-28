from django.core.management.base import BaseCommand

from core.ai_tasks import (
    enqueue_interview_result_fill,
    enqueue_interview_transcription,
    enqueue_motivation_letter_review,
    enqueue_scholar_video_transcription,
)
from core.models import AiTask, MotivationLetter
from review_by_tutor.models import Interview
from scholar_form.models import ScholarVideo


class Command(BaseCommand):
    help = "Enqueue pending AI work for existing application data."

    @staticmethod
    def _count_created(callback, obj) -> int:
        before = AiTask.objects.count()
        callback(obj)
        after = AiTask.objects.count()
        return max(after - before, 0)

    def handle(self, *args, **options):
        created = {
            "motivation_letter_review": 0,
            "interview_transcription": 0,
            "scholar_video_transcription": 0,
            "interview_result_fill": 0,
        }

        for letter in MotivationLetter.objects.select_related("user").iterator():
            created["motivation_letter_review"] += self._count_created(enqueue_motivation_letter_review, letter)

        for interview in Interview.objects.select_related("user").iterator():
            created["interview_transcription"] += self._count_created(enqueue_interview_transcription, interview)
            created["interview_result_fill"] += self._count_created(enqueue_interview_result_fill, interview)

        for video in ScholarVideo.objects.select_related("user").iterator():
            created["scholar_video_transcription"] += self._count_created(enqueue_scholar_video_transcription, video)

        self.stdout.write(
            self.style.SUCCESS(
                "AI tasks enqueued: "
                + ", ".join(f"{name}={count}" for name, count in created.items())
            )
        )
