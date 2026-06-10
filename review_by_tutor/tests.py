from decimal import Decimal
from io import BytesIO
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase, override_settings
from openpyxl import Workbook

from core.models import MotivationLetter, MotivationLetterRubricReview
from review_by_tutor.models import Interview, InterviewResult
from review_by_tutor.services.interview_xlsx import _build_application_values, import_interview_result_xlsx
from scholar_form.models import ScholarVideo, UserInfo

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class InterviewXlsxImportTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def _xlsx_payload(self):
        workbook = Workbook()
        ws = workbook.active
        ws["B12"] = "Школа кандидата, номер"
        ws["D12"] = "57"
        ws["B14"] = "Как далеко школа"
        ws["D14"] = "3,5 км"
        ws["C255"] = "Комментарий"
        ws["F255"] = "Кандидат мотивирован"
        ws["C258"] = "Итоговая оценка"
        ws["F258"] = "87 баллов"

        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        return payload

    def test_import_interview_result_xlsx_updates_model_fields(self):
        user = get_user_model().objects.create_user(username="xlsx-import")
        interview = Interview.objects.create(user=user)
        result = InterviewResult.objects.create(interview=interview)

        updated_fields = import_interview_result_xlsx(self._xlsx_payload(), result)
        result.refresh_from_db()

        self.assertIn("school_number", updated_fields)
        self.assertIn("school_distance_km", updated_fields)
        self.assertIn("interviewer_summary", updated_fields)
        self.assertIn("interviewer_score", updated_fields)
        self.assertEqual(result.school_number, "57")
        self.assertEqual(result.school_distance_km, Decimal("3.50"))
        self.assertEqual(result.interviewer_summary, "Кандидат мотивирован")
        self.assertEqual(result.interviewer_score, 87)

    def test_upload_interview_template_saves_file_and_updates_result(self):
        staff = get_user_model().objects.create_user(username="staff", is_staff=True)
        user = get_user_model().objects.create_user(username="candidate")
        interview = Interview.objects.create(user=user)
        InterviewResult.objects.create(interview=interview)
        upload = SimpleUploadedFile(
            "filled.xlsx",
            self._xlsx_payload().getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.client.force_login(staff)
        response = self.client.post(
            reverse("interview_detail", args=[user.id]),
            {"op": "upload_interview_template", "filled_template": upload},
        )

        self.assertEqual(response.status_code, 302)
        interview.refresh_from_db()
        result = InterviewResult.objects.get(interview=interview)
        self.assertTrue(interview.filled_template.name.endswith(".xlsx"))
        self.assertIsNotNone(interview.filled_uploaded_at)
        self.assertEqual(result.school_number, "57")
        self.assertEqual(result.interviewer_score, 87)

    def test_interview_detail_can_advance_candidate_after_interview(self):
        staff = get_user_model().objects.create_user(username="advance-staff", is_staff=True)
        user = get_user_model().objects.create_user(username="advance-candidate")
        user_info = UserInfo.objects.create(
            user=user,
            selection_step=UserInfo.SelectionStep.INTERVIEW_PREP,
        )

        self.client.force_login(staff)
        response = self.client.post(
            reverse("interview_detail", args=[user.id]),
            {"op": "advance_selection_step"},
        )

        self.assertEqual(response.status_code, 302)
        user_info.refresh_from_db()
        self.assertEqual(user_info.selection_step, UserInfo.SelectionStep.AFTER_INTERVIEW)

    def test_after_interview_candidate_sees_waiting_message(self):
        user = get_user_model().objects.create_user(username="after-interview-candidate")
        UserInfo.objects.create(
            user=user,
            selection_step=UserInfo.SelectionStep.AFTER_INTERVIEW,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("preparation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Собеседование пройдено.")
        self.assertContains(response, "дождаться результатов отбора")
    def test_after_interview_candidate_can_save_checkboxes(self):
        user = get_user_model().objects.create_user(username="after-interview-checkboxes")
        user_info = UserInfo.objects.create(
            user=user,
            selection_step=UserInfo.SelectionStep.AFTER_INTERVIEW,
        )

        self.client.force_login(user)
        response = self.client.post(
            reverse("preparation"),
            {
                "after_interview_parents_notified": "on",
                "after_interview_documents_ready": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        user_info.refresh_from_db()
        self.assertTrue(user_info.after_interview_parents_notified)
        self.assertTrue(user_info.after_interview_documents_ready)


        response = self.client.post(reverse("preparation"), {})

        self.assertEqual(response.status_code, 302)
        user_info.refresh_from_db()
        self.assertTrue(user_info.after_interview_parents_notified)
        self.assertTrue(user_info.after_interview_documents_ready)

    def test_interview_xlsx_uses_human_letter_comment_for_post_letter_questions(self):
        user = get_user_model().objects.create_user(username="letter-comment-match")
        interview = Interview.objects.create(user=user)
        letter = MotivationLetter.objects.create(
            user=user,
            letter_text="Текст письма",
            admin_rating="Комментарий от человека",
        )
        MotivationLetterRubricReview.objects.create(
            letter=letter,
            reviewer_comment="Комментарий из рубрики",
        )

        values = _build_application_values(user, interview, None)

        self.assertEqual(
            values["Вопросы на собеседование после мотписьма"],
            "Комментарий от человека",
        )
    def test_interview_xlsx_uses_selected_courses_from_scholar_video(self):
        user = get_user_model().objects.create_user(username="video-selected-courses")
        UserInfo.objects.create(
            user=user,
            preparation_plan="Общий план подготовки",
        )
        video = ScholarVideo.objects.create(
            user=user,
            online_school_selected_courses="Курсы из видеовизитки",
        )
        interview = Interview.objects.create(user=user)

        values = _build_application_values(user, interview, None)

        self.assertEqual(
            values["Выбранные курсы и онлайн-школы"],
            video.online_school_selected_courses,
        )

    def test_interview_xlsx_uses_video_review_for_video_internal_note(self):
        user = get_user_model().objects.create_user(username="video-review-note")
        video = ScholarVideo.objects.create(
            user=user,
            review="Отзыв из видеовизитки",
            online_school_interview_questions="Вопросы из видеовизитки",
        )
        interview = Interview.objects.create(user=user)

        values = _build_application_values(user, interview, None)

        self.assertEqual(
            values["Внутренняя заметка по видеовизитке"],
            video.review,
        )

    def test_interview_xlsx_leaves_interviewer_questions_empty(self):
        user = get_user_model().objects.create_user(username="empty-interviewer-questions")
        ScholarVideo.objects.create(
            user=user,
            online_school_interview_questions="Вопрос по курсам",
            schedule_interview_questions="Вопрос по графику",
        )
        interview = Interview.objects.create(
            user=user,
            notes="Заметка интервьюера",
        )

        values = _build_application_values(user, interview, None)

        self.assertEqual(values["Вопросы на собеседование от интервьюера"], "")
