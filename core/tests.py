import json
import os
import shutil
import tempfile
import threading
import time
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.llm_safe import compute_score, parse_llm_json
from core.models import (
    AiTask,
    MotivationLetter,
    MotivationLetterRubricReview,
    Notification,
    RegistrationPersonalData,
    UserNotification,
)
from documents.ctx_builders import base_user_context, merge_context
from documents.jinja_env import build_jinja_env, date_ru, money_text_ru
from documents.models import DocTemplate, Document
from my_study.models import (
    AssessmentResult,
    Course,
    CourseSelection,
    ProgressTrackerFile,
    School,
    Subject,
    UniversityPriority,
)
from review_by_tutor.models import Interview, TestAssignment
from review_by_tutor.services.staff_users import build_staff_users_queryset, get_staff_users_filters
from scholar_form.models import ScholarVideo, UserInfo, VideoInstruction
from scholar_form.views import (
    _clear_pending_upload,
    _form_error_payload,
    _get_pending_upload,
    _get_upload_status_payload,
    _resolve_file_url,
    _rollback_uploaded_assets,
    _set_upload_status,
    _store_pending_upload,
    _upload_suffix,
    _validate_direct_upload_meta,
    build_video_asset_context,
)
from subscriber.models import EmailSubscriber
from scholar_form.services import yandex_disk


settings.MIGRATION_MODULES = {
    "core": None,
    "documents": None,
    "my_study": None,
    "review_by_tutor": None,
    "scholar_form": None,
    "subscriber": None,
}


class IntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(
            MEDIA_ROOT=cls._media_root,
            DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
        )
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self._external_patches = [
            patch("Putevka.utils.telegram_logging_handler.TelegramHandler.emit", return_value=None),
            patch("documents.signals.bot_admin", None),
            patch("documents.signals.send_tg_notification_to_user"),
            patch("documents.signals.send_email_to_user"),
        ]
        for external_patch in self._external_patches:
            external_patch.start()

    def tearDown(self):
        for external_patch in reversed(self._external_patches):
            external_patch.stop()
        super().tearDown()

    def create_finished_candidate(self, username="candidate@example.com", password="StrongPass123!"):
        user = User.objects.create_user(
            username=username,
            email=username,
            password=password,
            first_name="Ivan",
            last_name="Petrov",
        )
        UserInfo.objects.create(
            user=user,
            email=username,
            first_name="Ivan",
            last_name="Petrov",
            selection_step=UserInfo.SelectionStep.ML,
        )
        RegistrationPersonalData.objects.create(
            user=user,
            email=username,
            password=user.password,
            email_verified=True,
            phone_verified=True,
            current_step="finish",
        )
        return user


class RegistrationFlowTests(IntegrationTestCase):
    @patch("core.views.send_email_verification_code")
    def test_candidate_can_complete_registration_without_external_services(self, send_email):
        email = "new-candidate@example.com"
        password = "StrongPass123!"

        response = self.client.post(
            reverse("register_initial"),
            {
                "email": email,
                "password": password,
                "password_confirm": password,
            },
        )

        self.assertRedirects(response, reverse("verify_email"))
        send_email.assert_called_once()

        user = User.objects.get(email=email)
        attempt = user.registrationpersonaldata
        self.assertEqual(attempt.current_step, "email_verification")
        self.assertTrue(UserInfo.objects.filter(user=user).exists())

        response = self.client.get(reverse("verify_email_confirm", args=[attempt.email_verification_code]))
        self.assertRedirects(response, reverse("connect_telegram"))

        attempt.refresh_from_db()
        self.assertTrue(attempt.email_verified)
        self.assertEqual(attempt.current_step, "telegram_connection")

        response = self.client.get(reverse("skip_telegram"))
        self.assertRedirects(response, reverse("verify_phone_if_needed"))

        with patch("core.views.initiate_zvonok_verification", return_value={"ok": True}):
            response = self.client.post(reverse("verify_phone_if_needed"), {"phone": "+7 900 000-00-01"})
        self.assertRedirects(response, reverse("wait_for_phone_call"))

        success_status = "\u0410\u0431\u043e\u043d\u0435\u043d\u0442 \u043e\u0442\u0432\u0435\u0442\u0438\u043b"
        with patch("core.views.poll_zvonok_status", return_value={"dial_status_display": success_status}):
            response = self.client.post(reverse("check_phone_call_status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        attempt.refresh_from_db()
        self.assertTrue(attempt.phone_verified)
        self.assertEqual(attempt.current_step, "finish")

        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)


class CandidateApplicationFlowTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_finished_candidate()
        self.client.force_login(self.user)

    def test_candidate_submits_letter_documents_study_choices_and_reads_notification(self):
        response = self.client.post(
            reverse("motivation_letter"),
            {"letter_text": "I want to study engineering and grow with the program.", "submit": "1"},
        )
        self.assertRedirects(response, reverse("motivation_letter"))

        letter = MotivationLetter.objects.get(user=self.user)
        self.assertEqual(letter.status, MotivationLetter.Status.SUBMITTED)
        self.assertIsNotNone(letter.submitted_at)

        uploaded = SimpleUploadedFile("statement.txt", b"candidate document", content_type="text/plain")
        with patch("documents.forms.magic.from_buffer", return_value="text/plain", create=True):
            response = self.client.post(
                reverse("documents_dashboard"),
                {
                    "form_type": "general_document_form",
                    "caption": "Statement",
                    "file": uploaded,
                },
            )
        self.assertRedirects(response, reverse("documents_dashboard"))

        document = Document.objects.get(user=self.user, uploaded_by_staff=False)
        self.assertEqual(document.caption, "Statement")
        self.assertFalse(document.is_deleted)

        math = Subject.objects.create(name="Mathematics", slug="math")
        school = School.objects.create(name="Online School")
        course = Course.objects.create(school=school, subject=math, title="Exam prep")

        response = self.client.post(
            reverse("study:select_course", args=[course.id]),
            {"motivation": "Need structured prep", "need_tutor": "on"},
        )
        self.assertRedirects(response, reverse("study:schools"))
        self.assertTrue(CourseSelection.objects.filter(user=self.user, course=course, need_tutor=True).exists())

        response = self.client.post(
            reverse("study:universities"),
            {
                "university": "State University",
                "city": "Tomsk",
                "specialty": "Software Engineering",
                "subjects": [math.id],
                "priority": "1",
                "notes": "Primary goal",
            },
        )
        self.assertRedirects(response, reverse("study:universities"))
        priority = UniversityPriority.objects.get(user=self.user)
        self.assertEqual(priority.priority, 1)
        self.assertEqual(list(priority.subjects.all()), [math])

        response = self.client.post(
            reverse("study:assessments"),
            {
                "kind": AssessmentResult.Kind.PROBNIK,
                "subject": math.id,
                "title": "Mock exam",
                "date": "2026-05-01",
                "score": "82",
                "max_score": "100",
                "place": "School",
                "notes": "Good progress",
            },
        )
        self.assertRedirects(response, reverse("study:assessments"))
        self.assertEqual(AssessmentResult.objects.get(user=self.user).percent, 82.0)

        staff = User.objects.create_user(username="staff", password="StrongPass123!", is_staff=True)
        notification = staff.sent_notifications.create(message="Check your plan")
        user_notification = UserNotification.objects.create(notification=notification, recipient=self.user)

        response = self.client.post(reverse("mark_as_seen", args=[user_notification.id]))
        self.assertRedirects(response, reverse("notifications"))
        user_notification.refresh_from_db()
        self.assertTrue(user_notification.is_seen)
        self.assertIsNotNone(user_notification.seen_at)


class StaffFlowTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.candidate = self.create_finished_candidate("staff-target@example.com")
        ScholarVideo.objects.create(user=self.candidate, deadline_at=timezone.now())
        self.client.force_login(self.staff)

    def test_staff_can_review_candidate_and_candidate_can_attach_requested_document(self):
        response = self.client.get(reverse("staff_scholar_dossier", args=[self.candidate.id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("staff_scholar_action", args=[self.candidate.id]),
            {"action": "set_video_score", "score": "87", "review": "Ready for next stage"},
        )
        self.assertRedirects(response, reverse("staff_scholar_dossier", args=[self.candidate.id]))

        video = self.candidate.scholar_video
        video.refresh_from_db()
        self.assertEqual(video.score, 87)
        self.assertEqual(video.review, "Ready for next stage")

        response = self.client.post(
            reverse("staff_scholar_action", args=[self.candidate.id]),
            {"action": "send_notification", "message": "Please attach signed document"},
        )
        self.assertRedirects(response, reverse("staff_scholar_dossier", args=[self.candidate.id]))
        self.assertTrue(UserNotification.objects.filter(recipient=self.candidate).exists())

        staff_file = SimpleUploadedFile("contract.txt", b"staff contract", content_type="text/plain")
        response = self.client.post(
            reverse("staff_scholar_action", args=[self.candidate.id]),
            {
                "action": "upload_staff_doc",
                "caption": "Contract",
                "status": "PENDING_SIGNATURE",
                "file": staff_file,
            },
        )
        self.assertRedirects(response, reverse("staff_scholar_dossier", args=[self.candidate.id]))

        requested_document = Document.objects.get(user=self.candidate, uploaded_by_staff=True)
        self.assertEqual(requested_document.status, "PENDING_SIGNATURE")

        candidate_file = SimpleUploadedFile("signed.txt", b"signed contract", content_type="text/plain")
        self.client.force_login(self.candidate)
        with patch("documents.forms.magic.from_buffer", return_value="text/plain", create=True):
            response = self.client.post(
                reverse("documents_dashboard"),
                {
                    "form_type": "general_document_form",
                    "caption": "Signed Contract",
                    "file": candidate_file,
                },
            )
        self.assertRedirects(response, reverse("documents_dashboard"))
        candidate_document = Document.objects.get(user=self.candidate, uploaded_by_staff=False)

        response = self.client.post(
            reverse("documents_dashboard"),
            {
                "form_type": "attach_documents_form",
                "target_document_id": str(requested_document.id),
                "documents_to_attach": [str(candidate_document.id)],
            },
        )
        self.assertRedirects(response, reverse("documents_dashboard"))

        requested_document.refresh_from_db()
        self.assertEqual(requested_document.status, "PENDING_SIGNATURE")
        self.assertEqual(list(requested_document.related_documents.all()), [])


class RubricPayloadTests(TestCase):
    def payload(self, **overrides):
        data = {
            "char_count": 1600,
            "word_count": 220,
            "content": {
                "specialty_choice_score": "10",
                "university_choice_score": "10",
                "current_preparation_score": "10",
                "admission_trajectory_score": "10",
                "next_year_preparation_score": "10",
                "higher_education_value_score": "10",
                "support_criticality_score": "10",
            },
            "rhetoric": {"composition_penalty": "0", "style_penalty": "0"},
            "literacy": {"orthography_penalty": "0", "syntax_penalty": "0"},
            "flags": {"suspected_ai_generated": False, "returned_for_revision": False},
            "extractions": {
                "family": "<b>family</b>",
                "hobbies": "hobbies",
                "achievements": "achievements",
                "traits": "traits",
                "school_teachers": "teachers",
                "prep_subjects": "math",
                "specialty": "engineering",
                "preferred_universities": "university",
                "relocation": "yes",
                "olympiads": "none",
                "motivation": "strong",
                "help_criticality": "high",
                "extra": "extra",
            },
            "reviewer_comment": "<script>alert(1)</script>ok",
            "justification": "clear",
        }
        data.update(overrides)
        return data

    def test_parse_valid_payload_sanitizes_and_computes_score(self):
        import json

        payload, flags = parse_llm_json(json.dumps(self.payload()))

        self.assertTrue(flags["ok"])
        self.assertEqual(payload.extractions.family, "family")
        self.assertIn("ok", payload.reviewer_comment)
        self.assertEqual(compute_score(payload), (70, ""))

    def test_compute_score_caps_short_text_and_rejects_ai(self):
        import json

        payload, _ = parse_llm_json(json.dumps(self.payload(char_count=1200)))
        self.assertEqual(compute_score(payload), (69, ""))

        ai_payload, _ = parse_llm_json(
            json.dumps(self.payload(flags={"suspected_ai_generated": True, "returned_for_revision": False}))
        )
        score, reason = compute_score(ai_payload)
        self.assertEqual(score, 0)
        self.assertTrue(reason)

        tiny_payload, _ = parse_llm_json(json.dumps(self.payload(char_count=999)))
        score, reason = compute_score(tiny_payload)
        self.assertEqual(score, 0)
        self.assertTrue(reason)

    def test_parse_invalid_json_and_invalid_schema_returns_flags(self):
        payload, flags = parse_llm_json("{")
        self.assertIsNone(payload)
        self.assertFalse(flags["ok"])
        self.assertIn("JSON decode error", flags["error"])

        payload, flags = parse_llm_json("{}")
        self.assertIsNone(payload)
        self.assertEqual(flags["error"], "Schema validation failed")
        self.assertTrue(flags["details"])

    def test_large_counts_add_warnings(self):
        import json

        payload, flags = parse_llm_json(json.dumps(self.payload(char_count=50001, word_count=10001)))

        self.assertIsNotNone(payload)
        self.assertEqual(len(flags["warnings"]), 2)


class YandexDiskServiceTests(IntegrationTestCase):
    def test_path_helpers_clean_candidate_names_and_extensions(self):
        user = self.create_finished_candidate("ivan@example.com")
        user.user_info.last_name = 'Petrov/Bad:*Name'
        user.user_info.first_name = 'Ivan'
        user.user_info.middle_name = 'I.'
        user.user_info.save()

        with override_settings(YANDEX_DISK_VIDEO_FOLDER="Root Folder"):
            video_path = yandex_disk.build_video_disk_path(user, "intro.mov", unique_suffix="v1")
            schedule_path = yandex_disk.build_schedule_disk_path(user, "schedule", unique_suffix="v2")

        self.assertTrue(video_path.startswith("disk:/Root Folder/"))
        self.assertIn(f"Petrov Bad Name Ivan ({user.id})", video_path)
        self.assertTrue(video_path.endswith(".mov"))
        self.assertTrue(schedule_path.endswith(".pdf"))
        self.assertNotIn(":", video_path.replace("disk:", "", 1))

    def test_progress_reader_reports_initial_and_incremental_progress(self):
        progress = []
        reader = yandex_disk._ProgressReader(BytesIO(b"abcdef"), 6, lambda sent, total: progress.append((sent, total)), chunk_size=2)

        self.assertEqual(len(reader), 6)
        self.assertEqual(reader.read(), b"ab")
        self.assertEqual(reader.read(), b"cd")
        self.assertEqual(reader.read(), b"ef")
        self.assertEqual(reader.read(), b"")
        self.assertEqual(progress, [(0, 6), (2, 6), (4, 6), (6, 6)])

    @override_settings(YANDEX_DISK_OAUTH_TOKEN="")
    def test_auth_headers_requires_token(self):
        with self.assertRaises(yandex_disk.YandexDiskError):
            yandex_disk._auth_headers()

    @override_settings(YANDEX_DISK_OAUTH_TOKEN="token", YANDEX_DISK_API_RETRIES=2, YANDEX_DISK_RETRY_BACKOFF_SECONDS=0)
    def test_request_retries_transient_status_and_returns_success(self):
        responses = [
            SimpleNamespace(status_code=503, text="temporary", json=lambda: {}),
            SimpleNamespace(status_code=200, text='{"ok": true}', json=lambda: {"ok": True}),
        ]
        retry_events = []

        with patch("scholar_form.services.yandex_disk.requests.request", side_effect=responses) as request:
            response = yandex_disk._request(
                "GET",
                "/resources",
                operation="test",
                retry_callback=lambda *args: retry_events.append(args),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(retry_events[0][0], 2)

    @override_settings(YANDEX_DISK_OAUTH_TOKEN="token")
    def test_resource_helpers_handle_api_statuses(self):
        ok_response = SimpleNamespace(status_code=200, text="", json=lambda: {"href": "https://upload.example"})
        missing_response = SimpleNamespace(status_code=404, text="", json=lambda: {})
        error_response = SimpleNamespace(status_code=400, text="bad", json=lambda: {"message": "bad request"})

        with patch("scholar_form.services.yandex_disk._request", return_value=ok_response):
            self.assertTrue(yandex_disk.resource_exists("folder/file.txt"))
            self.assertEqual(yandex_disk.get_download_url("folder/file.txt"), "https://upload.example")

        with patch("scholar_form.services.yandex_disk._request", return_value=missing_response):
            self.assertFalse(yandex_disk.resource_exists("missing.txt"))

        with patch("scholar_form.services.yandex_disk._request", return_value=error_response):
            with self.assertRaises(yandex_disk.YandexDiskError):
                yandex_disk.delete_resource("folder/file.txt")

    @override_settings(YANDEX_DISK_UPLOAD_RETRIES=1, YANDEX_DISK_VERIFY_RETRIES=1)
    def test_upload_file_to_yandex_disk_uploads_and_verifies(self):
        uploaded_file = SimpleUploadedFile("video.mp4", b"video-bytes", content_type="video/mp4")

        with (
            patch("scholar_form.services.yandex_disk.ensure_folder") as ensure_folder,
            patch("scholar_form.services.yandex_disk._get_upload_link", return_value="https://upload.example") as get_link,
            patch("scholar_form.services.yandex_disk.requests.put", return_value=SimpleNamespace(status_code=201, text="", json=lambda: {})) as put,
            patch("scholar_form.services.yandex_disk._verify_uploaded_resource") as verify,
        ):
            yandex_disk.upload_file_to_yandex_disk(uploaded_file=uploaded_file, disk_path="folder/video.mp4")

        ensure_folder.assert_called_once()
        get_link.assert_called_once()
        put.assert_called_once()
        verify.assert_called_once()


class DocumentHelperTests(IntegrationTestCase):
    def test_base_user_context_prefers_personal_data_and_formats_nested_fields(self):
        from scholar_form.models import UserPersonalData

        user = self.create_finished_candidate("doc@example.com")
        user.user_info.city = "Tomsk"
        user.user_info.save()
        personal_data = user.personal_data
        personal_data.last_name = "PersonalLast"
        personal_data.first_name = "PersonalFirst"
        personal_data.middle_name = "M"
        personal_data.email = "personal@example.com"
        personal_data.phone = "+79000000000"
        personal_data.passport_series = "1234"
        personal_data.passport_number = "567890"
        personal_data.passport_issued_at = date(2026, 5, 1)
        personal_data.passport_issued_by = "Office"
        personal_data.passport_department_code = "001-002"
        personal_data.registration_address = "Address"
        personal_data.bank_name = "Bank"
        personal_data.bank_account = "40817"
        personal_data.bank_bik = "044525225"
        personal_data.bank_correspondent_account = "30101"
        personal_data.inn = "1234567890"
        personal_data.save()

        context = base_user_context(user)

        self.assertEqual(context["user"]["fio"], "PersonalLast PersonalFirst M")
        self.assertEqual(context["user"]["email"], "personal@example.com")
        self.assertEqual(context["passport"]["issued_at"], "01.05.2026")
        self.assertEqual(context["address"]["city"], "Tomsk")
        self.assertEqual(merge_context(context, {"extra": "value"})["extra"], "value")

    def test_jinja_filters_format_dates_and_money(self):
        env = build_jinja_env()

        self.assertEqual(date_ru("2026-05-01"), "01.05.2026")
        self.assertEqual(date_ru("not-a-date"), "not-a-date")
        self.assertEqual(env.filters["date_ru"]("2026-05-01"), "01.05.2026")
        self.assertTrue(money_text_ru(125))
        self.assertEqual(money_text_ru(""), "")


class StaffUsersServiceTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.math = Subject.objects.create(name="Mathematics", slug="math-staff")
        self.school = School.objects.create(name="Staff School")
        self.course = Course.objects.create(school=self.school, subject=self.math, title="Staff Course")
        self.candidate = self.create_finished_candidate("filter@example.com")
        self.candidate.user_info.internal_study_profile = UserInfo.InternalStudyProfile.IT
        self.candidate.user_info.next_year_class_digit = 10
        self.candidate.user_info.form_status = UserInfo.FormStatus.SUBMITTED
        self.candidate.user_info.region = "Tomsk"
        self.candidate.user_info.save()
        CourseSelection.objects.create(
            user=self.candidate,
            course=self.course,
            motivation="Need course",
            need_tutor=True,
        )
        MotivationLetter.objects.create(
            user=self.candidate,
            letter_text="letter",
            status=MotivationLetter.Status.SUBMITTED,
            is_favorite=True,
        )
        ScholarVideo.objects.create(user=self.candidate, deadline_at=timezone.now())
        TestAssignment.objects.create(
            user=self.candidate,
            title="Exam",
            external_url="https://example.com",
            due_at=timezone.now() - timezone.timedelta(days=1),
        )
        User.objects.create_user("staff-visible", password="StrongPass123!", is_staff=True)

    def request(self, query):
        return self.factory.get("/staff/users/", data=query)

    def test_build_staff_users_queryset_applies_filters_and_annotations(self):
        request = self.request(
            {
                "q": "Tomsk",
                "profile": [UserInfo.InternalStudyProfile.IT],
                "grade_group": ["10"],
                "curator_need": "1",
                "step": UserInfo.SelectionStep.ML,
                "letter_status": MotivationLetter.Status.SUBMITTED,
                "favorite_letter": "1",
                "test_deadline": "overdue",
                "sort": "tests,user",
            }
        )

        users = list(build_staff_users_queryset(request))

        self.assertEqual(users, [self.candidate])
        self.assertEqual(users[0].docs_total, 0)
        self.assertEqual(users[0].letter_status, MotivationLetter.Status.SUBMITTED)
        self.assertTrue(users[0].has_overdue_test)
        self.assertEqual(users[0].test_status, "overdue")

    def test_staff_users_filters_returns_normalized_query_state(self):
        request = self.request(
            {
                "q": " filter ",
                "show_staff": "1",
                "profile": ["it", ""],
                "grade_group": ["other"],
                "sort": "user",
            }
        )

        filters = get_staff_users_filters(request)

        self.assertEqual(filters["q"], "filter")
        self.assertEqual(filters["profiles_selected"], ["it"])
        self.assertEqual(filters["grades_selected"], ["other"])
        self.assertEqual(filters["show_staff"], "1")

    def test_build_staff_users_queryset_can_include_staff_when_requested(self):
        request = self.request({"show_staff": "1", "sort": "user"})

        usernames = {user.username for user in build_staff_users_queryset(request)}

        self.assertIn("staff-visible", usernames)
        self.assertIn(self.candidate.username, usernames)


class ScholarVideoViewHelperTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_finished_candidate("video-helper@example.com")
        self.client.force_login(self.user)

    def test_upload_status_and_pending_upload_cache_helpers(self):
        _set_upload_status(self.user.id, "upload-1", state="pending", message="Started", percent=10, asset="video")
        status = _get_upload_status_payload(self.user.id, "upload-1")

        self.assertEqual(status["state"], "pending")
        self.assertEqual(status["percent"], 10)
        self.assertEqual(status["asset"], "video")

        payload = {"video": {"name": "intro.mp4"}}
        _store_pending_upload(self.user.id, "upload-1", payload)
        self.assertEqual(_get_pending_upload(self.user.id, "upload-1"), payload)
        _clear_pending_upload(self.user.id, "upload-1")
        self.assertIsNone(_get_pending_upload(self.user.id, "upload-1"))

    def test_validate_direct_upload_meta_accepts_valid_and_rejects_invalid(self):
        meta = _validate_direct_upload_meta(
            file_name="intro.mp4",
            content_type="video/mp4; charset=binary",
            size=1024,
            allowed_types={"video/mp4"},
            allowed_ext={".mp4"},
            max_size=2048,
            type_message="bad type",
            size_message="too large",
        )

        self.assertEqual(meta["content_type"], "video/mp4")
        self.assertEqual(meta["size"], 1024)

        with self.assertRaisesMessage(ValueError, "bad type"):
            _validate_direct_upload_meta(
                file_name="intro.exe",
                content_type="application/octet-stream",
                size=1024,
                allowed_types={"video/mp4"},
                allowed_ext={".mp4"},
                max_size=2048,
                type_message="bad type",
                size_message="too large",
            )

        with self.assertRaisesMessage(ValueError, "too large"):
            _validate_direct_upload_meta(
                file_name="intro.mp4",
                content_type="video/mp4",
                size=4096,
                allowed_types={"video/mp4"},
                allowed_ext={".mp4"},
                max_size=2048,
                type_message="bad type",
                size_message="too large",
            )

    def test_video_asset_context_handles_absent_local_and_remote_files(self):
        self.assertEqual(
            build_video_asset_context(None),
            {
                "video_download_url": None,
                "schedule_download_url": None,
                "video_name": "",
                "schedule_name": "",
                "video_mime": None,
            },
        )

        video = ScholarVideo.objects.create(
            user=self.user,
            yandex_disk_path="disk:/video.mp4",
            schedule_yandex_disk_path="disk:/schedule.pdf",
        )
        with patch("scholar_form.views.get_download_url", side_effect=["https://video", "https://schedule"]):
            context = build_video_asset_context(video)

        self.assertEqual(context["video_download_url"], "https://video")
        self.assertEqual(context["schedule_download_url"], "https://schedule")
        self.assertEqual(context["video_mime"], "video/mp4")

        with patch("scholar_form.views.get_download_url", side_effect=yandex_disk.YandexDiskError("failed")):
            self.assertIsNone(_resolve_file_url("disk:/bad.mp4", video.file))

    def test_rollback_uploaded_assets_deletes_new_paths_and_updates_status(self):
        deleted = []
        with patch("scholar_form.views.delete_resource", side_effect=lambda path, **kwargs: deleted.append(path)):
            _rollback_uploaded_assets(
                [{"new_path": "disk:/new-video.mp4", "asset": "video"}, {"new_path": "", "asset": "schedule"}],
                user_id=self.user.id,
                upload_id="rollback-1",
            )

        self.assertEqual(deleted, ["disk:/new-video.mp4"])
        self.assertEqual(_get_upload_status_payload(self.user.id, "rollback-1")["state"], "rollback")

    def test_form_error_payload_and_upload_suffix(self):
        from core.forms import FeedbackForm

        form = FeedbackForm(data={"message": "", "website": "spam"})
        self.assertFalse(form.is_valid())
        payload = _form_error_payload(form)

        self.assertIn("message", payload)
        self.assertIn("non_field_errors", payload)
        self.assertEqual(_upload_suffix("abc-123-!"), "abc123")

    def test_candidate_video_pages_and_upload_endpoints_smoke(self):
        self.user.user_info.selection_step = UserInfo.SelectionStep.VIDEO
        self.user.user_info.save()
        VideoInstruction.objects.create(title="Video", text="Record", url="https://example.com")

        response = self.client.get(reverse("my_video_page"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("my_video_upload_init"),
            data={
                "upload_id": "upload-video",
                "video_name": "intro.mp4",
                "video_type": "video/mp4",
                "video_size": "1024",
                "schedule_name": "schedule.pdf",
                "schedule_type": "application/pdf",
                "schedule_size": "512",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        response = self.client.get(reverse("my_video_upload_status"), {"upload_id": "upload-video"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "ready")

    def test_video_upload_finalize_success_and_missing_session(self):
        self.user.user_info.selection_step = UserInfo.SelectionStep.VIDEO
        self.user.user_info.save()

        response = self.client.post(reverse("my_video_upload_finalize"), {"upload_id": "missing"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

        _store_pending_upload(
            self.user.id,
            "finalize-1",
            {
                "video_path": "disk:/video.mp4",
                "schedule_path": "disk:/schedule.pdf",
                "previous_video_path": "",
                "previous_schedule_path": "",
            },
        )
        with patch("scholar_form.views.resource_exists", return_value=True), patch("scholar_form.views.delete_resource"):
            response = self.client.post(
                reverse("my_video_upload_finalize"),
                {
                    "upload_id": "finalize-1",
                    "online_school_course": "Course",
                    "schedule_school_day": "School day",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        video = self.user.scholar_video
        video.refresh_from_db()
        self.assertEqual(video.yandex_disk_path, "disk:/video.mp4")
        self.assertEqual(_get_upload_status_payload(self.user.id, "finalize-1")["state"], "done")

    def test_video_upload_finalize_rolls_back_when_remote_file_missing(self):
        self.user.user_info.selection_step = UserInfo.SelectionStep.VIDEO
        self.user.user_info.save()
        _store_pending_upload(
            self.user.id,
            "finalize-2",
            {
                "video_path": "disk:/missing.mp4",
                "schedule_path": "",
                "previous_video_path": "",
                "previous_schedule_path": "",
            },
        )

        with patch("scholar_form.views.resource_exists", return_value=False):
            response = self.client.post(reverse("my_video_upload_finalize"), {"upload_id": "finalize-2"})

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(_get_upload_status_payload(self.user.id, "finalize-2")["state"], "error")


class StaffPageSmokeTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username="staff-pages@example.com",
            email="staff-pages@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.candidate = self.create_finished_candidate("pages-target@example.com")
        self.candidate.user_info.selection_step = UserInfo.SelectionStep.VIDEO
        self.candidate.user_info.form_status = UserInfo.FormStatus.SUBMITTED
        self.candidate.user_info.save()
        MotivationLetter.objects.create(
            user=self.candidate,
            letter_text="Motivation letter text",
            status=MotivationLetter.Status.SUBMITTED,
        )
        ScholarVideo.objects.create(user=self.candidate, deadline_at=timezone.now())
        self.subject = Subject.objects.create(name="Physics", slug="physics")
        self.school = School.objects.create(name="Physics School")
        self.course = Course.objects.create(school=self.school, subject=self.subject, title="Physics Prep")
        CourseSelection.objects.create(
            user=self.candidate,
            course=self.course,
            motivation="Need physics",
            need_tutor=False,
        )
        UniversityPriority.objects.create(
            user=self.candidate,
            university="Tomsk University",
            city="Tomsk",
            specialty="Physics",
            priority=1,
        )
        AssessmentResult.objects.create(
            user=self.candidate,
            kind=AssessmentResult.Kind.TEST,
            subject=self.subject,
            title="Physics test",
            date=date(2026, 5, 1),
            score=75,
            max_score=100,
        )
        Document.objects.create(
            user=self.candidate,
            file=SimpleUploadedFile("passport.txt", b"passport"),
            caption="Passport",
        )
        TestAssignment.objects.create(
            user=self.candidate,
            title="Logic test",
            external_url="https://example.com",
            due_at=timezone.now() + timezone.timedelta(days=2),
        )
        self.client.force_login(self.staff)

    def test_staff_detail_pages_render(self):
        url_names = [
            "staff_letter_detail",
            "staff_profile_detail",
            "staff_video_detail",
            "staff_documents_detail",
            "staff_study_detail",
            "staff_notes",
            "staff_testing_list_for_user",
            "staff_docs_templates",
            "staff_scholar_dossier",
        ]

        for name in url_names:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=[self.candidate.id]))
                self.assertEqual(response.status_code, 200)

    def test_staff_collection_and_json_pages_render(self):
        response = self.client.get(reverse("staff_users_list"), {"q": "pages-target"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("staff_users_ids"), {"q": "pages-target"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.candidate.id, response.json()["ids"])

        response = self.client.get(reverse("staff_testing_template_payload"), {"template_id": ""})
        self.assertIn(response.status_code, {200, 400})

    def test_staff_letter_download_returns_docx(self):
        response = self.client.get(reverse("staff_letter_download", args=[self.candidate.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            response["Content-Type"],
        )

    def test_staff_letter_post_actions_update_state(self):
        with patch("review_by_tutor.views.notify_participant"):
            response = self.client.post(
                reverse("staff_letter_detail", args=[self.candidate.id]),
                {"action_toggle_favorite": "1"},
            )
        self.assertRedirects(response, reverse("staff_letter_detail", args=[self.candidate.id]))
        self.candidate.motivation_letter.refresh_from_db()
        self.assertTrue(self.candidate.motivation_letter.is_favorite)

        deadline = (timezone.now() + timezone.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        with patch("review_by_tutor.views.notify_participant"):
            response = self.client.post(
                reverse("staff_letter_detail", args=[self.candidate.id]),
                {"action_deadline_save": "1", "deadline_at": deadline},
            )
        self.assertEqual(response.status_code, 302)
        self.candidate.motivation_letter.refresh_from_db()
        self.assertIsNotNone(self.candidate.motivation_letter.deadline_at)

    def test_staff_video_and_documents_post_actions(self):
        deadline = (timezone.now() + timezone.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("staff_video_detail", args=[self.candidate.id]),
            {"action_deadline_save": "1", "deadline_at": deadline},
        )
        self.assertRedirects(response, reverse("staff_video_detail", args=[self.candidate.id]))

        response = self.client.post(
            reverse("staff_video_detail", args=[self.candidate.id]),
            {"action_deadline_clear": "1"},
        )
        self.assertRedirects(response, reverse("staff_video_detail", args=[self.candidate.id]))

        doc = self.candidate.documents.first()
        response = self.client.post(
            reverse("staff_documents_detail", args=[self.candidate.id]),
            {
                "form_type": "update_status",
                "document_id": str(doc.id),
                f"st-{doc.id}-status": "APPROVED",
            },
        )
        self.assertRedirects(response, reverse("staff_documents_detail", args=[self.candidate.id]))
        doc.refresh_from_db()
        self.assertEqual(doc.status, "APPROVED")


class SubscriberFlowTests(TestCase):
    def test_announce_subscribes_and_thanks_consumes_session_email(self):
        response = self.client.get(reverse("announce"))
        self.assertIn(response.status_code, {200, 302})

        response = self.client.post(reverse("announce"), {"email": "USER@EXAMPLE.COM"})
        self.assertRedirects(response, reverse("thanks_subscribe"), fetch_redirect_response=False)
        self.assertTrue(EmailSubscriber.objects.filter(email="user@example.com").exists())

        response = self.client.get(reverse("thanks_subscribe"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("thanks_subscribe"))
        self.assertRedirects(response, reverse("announce"))


class AiServiceUnitTests(TestCase):
    def test_worker_executes_supported_task_types_without_external_calls(self):
        from ai_service.worker import execute_task

        client = Mock()

        with patch("ai_service.worker.review_letter", return_value={"review": {"total_score": 75}}) as review:
            result = execute_task(client, {"id": "task-1", "type": "motivation_letter_review", "payload": {"letter_text": "text"}})
        self.assertEqual(result["review"]["total_score"], 75)
        review.assert_called_once_with("text")

        with patch("ai_service.worker._with_downloaded_file", return_value="media.mp4"), \
             patch("ai_service.worker.transcribe_media_file", return_value="transcript") as transcribe, \
             patch("ai_service.worker.os.remove") as remove:
            result = execute_task(
                client,
                {
                    "id": "task-2",
                    "type": "interview_transcription",
                    "payload": {"file_url": "http://files/video.mp4", "language": "ru"},
                },
            )
        self.assertEqual(result, {"transcript": "transcript"})
        transcribe.assert_called_once_with("media.mp4", language="ru")
        remove.assert_called_once_with("media.mp4")

        with patch("ai_service.worker.ask_openai_fill", return_value={"field": "value"}) as fill:
            result = execute_task(
                client,
                {"id": "task-3", "type": "interview_result_fill", "payload": {"fields_schema": {"field": "Text"}, "transcript": "hello"}},
            )
        self.assertEqual(result, {"answers": {"field": "value"}})
        fill.assert_called_once_with({"field": "Text"}, "hello")

        with self.assertRaisesMessage(ValueError, "Unknown AI task type"):
            execute_task(client, {"id": "task-4", "type": "unknown", "payload": {}})

    def test_worker_retries_when_django_api_is_unavailable(self):
        import httpx
        from ai_service.worker import run_once

        client = Mock()
        client.claim.side_effect = httpx.ConnectError("refused")

        with patch("ai_service.worker.time.sleep") as sleep:
            self.assertFalse(run_once(client))

        sleep.assert_called_once()

    def test_worker_run_once_completes_and_fails_tasks(self):
        from ai_service.worker import run_once

        client = Mock()
        client.claim.return_value = {"id": "task-ok", "type": "interview_result_fill", "payload": {}}

        with patch("ai_service.worker.execute_task", return_value={"answers": {"field": "value"}}):
            self.assertTrue(run_once(client))

        client.complete.assert_called_once_with("task-ok", {"answers": {"field": "value"}})

        client = Mock()
        client.claim.return_value = {"id": "task-fail", "type": "interview_result_fill", "payload": {}}
        with patch("ai_service.worker.execute_task", side_effect=RuntimeError("bad result")):
            self.assertTrue(run_once(client))

        client.fail.assert_called_once_with("task-fail", "bad result", retryable=True)

    def test_django_ai_client_posts_expected_payloads_and_downloads_content(self):
        from ai_service.client import DjangoAiClient

        responses = [
            Mock(status_code=200, is_error=False, history=[], json=Mock(return_value={"task": {"id": "1"}}), raise_for_status=Mock()),
            Mock(status_code=200, is_error=False, history=[], raise_for_status=Mock()),
            Mock(status_code=200, is_error=False, history=[], raise_for_status=Mock()),
            Mock(status_code=200, is_error=False, history=[], raise_for_status=Mock()),
            Mock(status_code=200, is_error=False, history=[], content=b"file-bytes", raise_for_status=Mock()),
        ]
        http_client = Mock()
        http_client.post.side_effect = responses[:4]
        http_client.get.return_value = responses[4]

        with patch("ai_service.client.httpx.Client", return_value=http_client) as httpx_client_cls, \
             patch.dict("os.environ", {"AI_DJANGO_BASE_URL": "http://django.local", "AI_WORKER_ID": "worker-1", "AI_SERVICE_TOKEN": "token"}):
            client = DjangoAiClient()
            self.assertEqual(client.claim(600), {"id": "1"})
            client.heartbeat("task-id", 700)
            client.complete("task-id", {"ok": True})
            client.fail("task-id", "bad", retryable=False)
            target = tempfile.NamedTemporaryFile(delete=False)
            target.close()
            try:
                client.download("http://django.local/file", target.name)
                with open(target.name, "rb") as fh:
                    self.assertEqual(fh.read(), b"file-bytes")
            finally:
                os.remove(target.name)

        self.assertEqual(http_client.post.call_args_list[0].args[0], "http://django.local/internal/ai/tasks/claim/")
        self.assertEqual(http_client.post.call_args_list[0].kwargs["json"], {"worker_id": "worker-1", "lease_seconds": 600})
        self.assertFalse(http_client.post.call_args_list[3].kwargs["json"]["retryable"])
        self.assertTrue(httpx_client_cls.call_args.kwargs["follow_redirects"])

    def test_openai_runtime_normalizes_proxy_and_builds_client(self):
        from ai_service.openai_runtime import make_openai_client, normalize_proxy_url

        self.assertIsNone(normalize_proxy_url(""))
        self.assertEqual(normalize_proxy_url(" socks5h://proxy:1080 "), "socks5://proxy:1080")
        self.assertEqual(normalize_proxy_url("http://proxy:8080"), "http://proxy:8080")

        with patch("ai_service.openai_runtime.httpx.Client") as http_client, \
             patch("ai_service.openai_runtime.OpenAI") as openai_cls, \
             patch.dict("os.environ", {"OPENAI_API_KEY": "key", "TELEGRAM_SOCKS5_PROXY": "socks5h://proxy:1080", "OPENAI_MAX_RETRIES": "2"}):
            make_openai_client()

        self.assertEqual(http_client.call_args.kwargs["proxy"], "socks5://proxy:1080")
        self.assertEqual(openai_cls.call_args.kwargs["api_key"], "key")
        self.assertEqual(openai_cls.call_args.kwargs["max_retries"], 2)

    def test_ai_logging_config_uses_rotating_files(self):
        from ai_service.logging_config import configure_logging

        with tempfile.TemporaryDirectory() as log_dir, \
             patch.dict("os.environ", {"AI_LOG_DIR": log_dir, "LOG_LEVEL": "DEBUG", "AI_LOG_LEVEL": "INFO"}), \
             patch("ai_service.logging_config.logging.config.dictConfig") as dict_config:
            configure_logging()

        config_payload = dict_config.call_args.args[0]
        self.assertIn("ai_service", config_payload["loggers"])
        self.assertTrue(config_payload["handlers"]["file_info"]["filename"].endswith("ai_service.log"))
        self.assertTrue(config_payload["handlers"]["file_error"]["filename"].endswith("ai_service_errors.log"))

    def test_fill_form_ask_openai_fill_parses_json_response(self):
        from ai_service.tasks.fill_form import ask_openai_fill

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"answers": {"field": "value"}}'))]
        )
        client = Mock()
        client.chat.completions.create.return_value = response

        with patch("ai_service.tasks.fill_form.make_openai_client", return_value=client), \
             patch.dict("os.environ", {"OPENAI_MODEL": "gpt-test"}):
            result = ask_openai_fill({"field": "Verbose name"}, "transcript")

        self.assertEqual(result, {"field": "value"})
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "gpt-test")
        self.assertEqual(client.chat.completions.create.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_reviewer_parses_valid_openai_payload_and_computes_score(self):
        from ai_service.tasks.reviewer import RUBRIC_VERSION, review_letter

        payload = {
            "char_count": 1600,
            "word_count": 250,
            "content": {
                "specialty_choice_score": "10",
                "university_choice_score": "10",
                "current_preparation_score": "10",
                "admission_trajectory_score": "10",
                "next_year_preparation_score": "10",
                "higher_education_value_score": "10",
                "support_criticality_score": "10",
            },
            "rhetoric": {"composition_penalty": "0", "style_penalty": "0"},
            "literacy": {"orthography_penalty": "0", "syntax_penalty": "0"},
            "flags": {"suspected_ai_generated": False, "returned_for_revision": False},
            "extractions": {
                "family": "",
                "hobbies": "",
                "achievements": "",
                "traits": "",
                "school_teachers": "",
                "prep_subjects": "",
                "specialty": "",
                "preferred_universities": "",
                "relocation": "",
                "olympiads": "",
                "motivation": "",
                "help_criticality": "",
                "extra": "",
            },
            "reviewer_comment": "ok",
            "justification": "clear",
        }
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )
        client = Mock()
        client.chat.completions.create.return_value = response

        with patch("ai_service.tasks.reviewer.make_openai_client", return_value=client), \
             patch("ai_service.tasks.reviewer.OPENAI_MODEL", "gpt-review"):
            result = review_letter("letter text")

        self.assertEqual(result["review"]["total_score"], 70)
        self.assertEqual(result["review"]["schema_version"], RUBRIC_VERSION)
        self.assertEqual(result["review"]["model_name"], "gpt-review")

    def test_transcribe_media_file_handles_short_and_chunked_media(self):
        from ai_service.tasks import transcribe

        extracted = []

        def fake_extract(source, target, start_sec=None, duration_sec=None):
            extracted.append((source, start_sec, duration_sec))

        with patch.object(transcribe, "MAX_MODEL_AUDIO_SECONDS", 10), \
             patch("ai_service.tasks.transcribe._probe_duration_seconds", return_value=9.0), \
             patch("ai_service.tasks.transcribe._extract_audio", side_effect=fake_extract), \
             patch("ai_service.tasks.transcribe._transcribe_audio_file", return_value="one"):
            self.assertEqual(transcribe.transcribe_media_file("short.mp4"), "one")

        extracted.clear()
        with patch.object(transcribe, "MAX_MODEL_AUDIO_SECONDS", 5), \
             patch.object(transcribe, "CHUNK_SECONDS", 4), \
             patch.object(transcribe, "CHUNK_OVERLAP_SECONDS", 1), \
             patch("ai_service.tasks.transcribe._probe_duration_seconds", return_value=8.0), \
             patch("ai_service.tasks.transcribe._extract_audio", side_effect=fake_extract), \
             patch("ai_service.tasks.transcribe._transcribe_audio_file", side_effect=["alpha", "beta", "gamma"]):
            result = transcribe.transcribe_media_file("long.mp4", language="ru")

        self.assertIn("[00:00:00]\nalpha", result)
        self.assertIn("[00:00:03]\nbeta", result)
        self.assertIn("[00:00:06]\ngamma", result)
        self.assertEqual(extracted, [("long.mp4", 0, 4), ("long.mp4", 3, 4), ("long.mp4", 6, 3)])

    def test_transcribe_media_file_handles_diarized_response(self):
        from ai_service.tasks import transcribe

        with patch.object(transcribe, "OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize"), \
             patch.object(transcribe, "MAX_MODEL_AUDIO_SECONDS", 10), \
             patch("ai_service.tasks.transcribe._probe_duration_seconds", return_value=9.0), \
             patch("ai_service.tasks.transcribe._extract_audio"), \
             patch(
                 "ai_service.tasks.transcribe._transcribe_audio_file_diarized",
                 return_value="[00:00:01] A: hello\n[00:00:04] B: hi",
             ) as diarize:
            result = transcribe.transcribe_media_file("short.mp4", language="ru")

        self.assertEqual(result, "[00:00:01] A: hello\n[00:00:04] B: hi")
        diarize.assert_called_once()

        formatted = transcribe._format_diarized_result(
            {
                "segments": [
                    {"speaker": "A", "start": 1.2, "text": "question"},
                    {"speaker": "B", "start": 5.8, "text": "answer"},
                ]
            },
            offset_seconds=10,
        )
        self.assertIn("[00:00:11] A: question", formatted)
        self.assertIn("[00:00:15] B: answer", formatted)

    def test_diarized_transcription_uses_smaller_chunks(self):
        from ai_service.tasks import transcribe

        extracted = []

        def fake_extract(source, target, start_sec=None, duration_sec=None):
            extracted.append((start_sec, duration_sec))

        with patch.object(transcribe, "OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize"), \
             patch.object(transcribe, "DIARIZE_MAX_MODEL_AUDIO_SECONDS", 5), \
             patch.object(transcribe, "DIARIZE_CHUNK_SECONDS", 4), \
             patch.object(transcribe, "DIARIZE_CHUNK_OVERLAP_SECONDS", 1), \
             patch("ai_service.tasks.transcribe._probe_duration_seconds", return_value=8.0), \
             patch("ai_service.tasks.transcribe._extract_audio", side_effect=fake_extract), \
             patch(
                 "ai_service.tasks.transcribe._transcribe_audio_file_diarized",
                 side_effect=["[00:00:00] A: one", "[00:00:03] B: two", "[00:00:06] A: three"],
             ):
            result = transcribe.transcribe_media_file("long.mp4", language="ru")

        self.assertIn("[00:00:00] A: one", result)
        self.assertIn("[00:00:03] B: two", result)
        self.assertIn("[00:00:06] A: three", result)
        self.assertEqual(extracted, [(0, 4), (3, 4), (6, 3)])

    def test_chunked_transcription_runs_chunks_concurrently_and_preserves_order(self):
        from ai_service.tasks import transcribe

        active = 0
        max_active = 0
        lock = threading.Lock()
        two_active = threading.Event()

        def fake_extract(source, target, start_sec=None, duration_sec=None):
            open(target, "wb").close()

        def fake_transcribe(chunk_path, language):
            nonlocal active, max_active
            name = os.path.basename(chunk_path)
            with lock:
                active += 1
                max_active = max(max_active, active)
                if active >= 2:
                    two_active.set()
            two_active.wait(timeout=1)
            if name == "chunk_000.wav":
                time.sleep(0.05)
            with lock:
                active -= 1
            return name

        with patch.object(transcribe, "MAX_MODEL_AUDIO_SECONDS", 5), \
             patch.object(transcribe, "CHUNK_SECONDS", 4), \
             patch.object(transcribe, "CHUNK_OVERLAP_SECONDS", 1), \
             patch.object(transcribe, "CHUNK_TRANSCRIBE_CONCURRENCY", 2), \
             patch("ai_service.tasks.transcribe._probe_duration_seconds", return_value=8.0), \
             patch("ai_service.tasks.transcribe._extract_audio", side_effect=fake_extract), \
             patch("ai_service.tasks.transcribe._transcribe_audio_file", side_effect=fake_transcribe):
            result = transcribe.transcribe_media_file("long.mp4", language="ru")

        self.assertGreaterEqual(max_active, 2)
        self.assertLess(result.index("chunk_000.wav"), result.index("chunk_001.wav"))
        self.assertLess(result.index("chunk_001.wav"), result.index("chunk_002.wav"))

    def test_diarized_transcription_passes_required_openai_options(self):
        from ai_service.tasks import transcribe

        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(b"audio")
        tmp.close()

        create = Mock(
            return_value={
                "segments": [
                    {"speaker": "A", "start": 0, "text": "question"},
                    {"speaker": "B", "start": 2, "text": "answer"},
                ]
            }
        )
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))

        try:
            with patch.object(transcribe, "OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize"), \
                 patch("ai_service.tasks.transcribe.make_openai_client", return_value=client):
                result = transcribe._transcribe_audio_file_diarized(tmp.name, "ru")
        finally:
            os.remove(tmp.name)

        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o-transcribe-diarize")
        self.assertEqual(kwargs["response_format"], "diarized_json")
        self.assertEqual(kwargs["chunking_strategy"], "auto")
        self.assertEqual(kwargs["language"], "ru")
        self.assertIn("[00:00:00] A: question", result)
        self.assertIn("[00:00:02] B: answer", result)

    def test_fill_form_normalizes_values_and_preserves_existing_text(self):
        from ai_service.tasks.fill_form import apply_answers_to_result
        from review_by_tutor.models import Interview, InterviewResult

        user = User.objects.create_user(username="ai-fill@example.com")
        TestAssignment.objects.create(user=user, title="Interview")
        interview = Interview.objects.create(user=user)
        result = InterviewResult.objects.create(interview=interview, other_notes="curator note")

        fields = [
            InterviewResult._meta.get_field("other_notes"),
            InterviewResult._meta.get_field("interviewer_score"),
            InterviewResult._meta.get_field("school_distance_km"),
        ]
        updated = apply_answers_to_result(
            result,
            fields,
            {"other_notes": "ai note", "interviewer_score": "87 баллов", "school_distance_km": "4,75"},
        )

        self.assertEqual(set(updated), {"other_notes", "interviewer_score", "school_distance_km"})
        self.assertIn("curator note", result.other_notes)
        self.assertIn("ai note", result.other_notes)
        self.assertEqual(result.interviewer_score, 87)
        self.assertEqual(result.school_distance_km, Decimal("4.75"))

    def test_apply_interview_result_accepts_verbose_and_schema_answer_keys(self):
        from core.ai_tasks import apply_interview_result
        from review_by_tutor.models import Interview, InterviewResult

        user = User.objects.create_user(username="ai-fill-keys@example.com")
        TestAssignment.objects.create(user=user, title="Interview")
        interview = Interview.objects.create(user=user)

        apply_interview_result(
            interview,
            {
                "Прочие замечания": "кандидат мотивирован",
                "Итоговая оценка интервьюера (field: interviewer_score, type: IntegerField)": "88 баллов",
                "Удалённость от дома (км)": "3,5",
            },
        )

        result = InterviewResult.objects.get(interview=interview)
        self.assertEqual(result.other_notes, "кандидат мотивирован")
        self.assertEqual(result.interviewer_score, 88)
        self.assertEqual(result.school_distance_km, Decimal("3.5"))


class AiTaskApiTests(IntegrationTestCase):
    def test_motivation_letter_review_enqueue_skips_reviewed_letters(self):
        from core.ai_tasks import enqueue_motivation_letter_review

        with_rubric_user = self.create_finished_candidate("ai-rubric-exists@example.com")
        with_rubric = MotivationLetter.objects.create(
            user=with_rubric_user,
            letter_text="submitted letter",
            status=MotivationLetter.Status.SUBMITTED,
        )
        AiTask.objects.filter(source_object_id=with_rubric.pk).delete()
        MotivationLetterRubricReview.objects.create(letter=with_rubric, total_score=55)

        with_score_user = self.create_finished_candidate("ai-admin-score@example.com")
        with_score = MotivationLetter.objects.create(
            user=with_score_user,
            letter_text="submitted letter",
            status=MotivationLetter.Status.SUBMITTED,
            admin_score=60,
        )
        AiTask.objects.filter(source_object_id=with_score.pk).delete()

        with_rating_user = self.create_finished_candidate("ai-admin-rating@example.com")
        with_rating = MotivationLetter.objects.create(
            user=with_rating_user,
            letter_text="submitted letter",
            status=MotivationLetter.Status.SUBMITTED,
            admin_rating="Checked by admin",
        )
        AiTask.objects.filter(source_object_id=with_rating.pk).delete()

        for letter in (with_rubric, with_score, with_rating):
            self.assertIsNone(enqueue_motivation_letter_review(letter))

        self.assertFalse(
            AiTask.objects.filter(
                task_type=AiTask.Type.MOTIVATION_LETTER_REVIEW,
                source_model="motivationletter",
                source_object_id__in=[with_rubric.pk, with_score.pk, with_rating.pk],
            ).exists()
        )

    def test_motivation_letter_review_enqueue_creates_task_for_unreviewed_letter(self):
        from core.ai_tasks import enqueue_motivation_letter_review

        user = self.create_finished_candidate("ai-unreviewed@example.com")
        letter = MotivationLetter.objects.create(
            user=user,
            letter_text="submitted letter",
            status=MotivationLetter.Status.SUBMITTED,
        )
        AiTask.objects.filter(source_object_id=letter.pk).delete()

        task = enqueue_motivation_letter_review(letter)

        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, AiTask.Type.MOTIVATION_LETTER_REVIEW)
        self.assertEqual(task.source_object_id, letter.pk)

    def test_interview_transcription_enqueue_accepts_yandex_disk_video(self):
        from core.ai_tasks import enqueue_interview_transcription

        user = self.create_finished_candidate("ai-interview-yandex@example.com")
        interview = Interview.objects.create(
            user=user,
            video_source_type="yandex_disk_path",
            video_yandex_disk_path="disk:/interviews/candidate.mp4",
            video_name="candidate.mp4",
            transcript_status="PENDING",
        )
        AiTask.objects.filter(source_model="interview", source_object_id=interview.pk).delete()

        task = enqueue_interview_transcription(interview)

        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, AiTask.Type.INTERVIEW_TRANSCRIPTION)
        self.assertEqual(task.source_app, "review_by_tutor")
        self.assertEqual(task.source_model, "interview")
        self.assertEqual(task.source_object_id, interview.pk)
        self.assertEqual(task.source_version, "disk:/interviews/candidate.mp4")
        self.assertIn("/internal/ai/files/", task.payload["file_url"])

    def test_ai_task_api_claim_complete_fail_and_forbidden(self):
        from core.ai_tasks import create_ai_task

        user = self.create_finished_candidate("ai-api@example.com")
        letter = MotivationLetter.objects.create(user=user, letter_text="letter", status=MotivationLetter.Status.SUBMITTED)
        task = AiTask.objects.filter(source_app="core", source_model="motivationletter", source_object_id=letter.pk).earliest("created_at")

        with override_settings(AI_SERVICE_TOKEN="secret"):
            forbidden = self.client.post(reverse("ai_task_claim"), {}, content_type="application/json")
            self.assertEqual(forbidden.status_code, 403)

            response = self.client.post(
                reverse("ai_task_claim"),
                {"worker_id": "worker-1", "lease_seconds": 60},
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer secret",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["task"]["id"], str(task.pk))

            heartbeat = self.client.post(
                reverse("ai_task_heartbeat", args=[task.pk]),
                {"worker_id": "worker-1", "lease_seconds": 60},
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer secret",
            )
            self.assertEqual(heartbeat.status_code, 200)

            with patch("core.ai_tasks.apply_task_result"):
                complete = self.client.post(
                    reverse("ai_task_complete", args=[task.pk]),
                    {"worker_id": "worker-1", "result": {"ok": True}},
                    content_type="application/json",
                    HTTP_AUTHORIZATION="Bearer secret",
                )
            self.assertEqual(complete.status_code, 200)
            task.refresh_from_db()
            self.assertEqual(task.status, AiTask.Status.DONE)

            failed_task = create_ai_task(AiTask.Type.MOTIVATION_LETTER_REVIEW, letter, {"letter_text": "other"}, source_version="v2")
            failed_task.status = AiTask.Status.PROCESSING
            failed_task.locked_by = "worker-1"
            failed_task.attempts = failed_task.max_attempts
            failed_task.save(update_fields=["status", "locked_by", "attempts"])

            with patch("core.ai_tasks.mark_source_failed"):
                failed = self.client.post(
                    reverse("ai_task_fail", args=[failed_task.pk]),
                    {"worker_id": "worker-1", "error": "boom", "retryable": True},
                    content_type="application/json",
                    HTTP_AUTHORIZATION="Bearer secret",
                )
            self.assertEqual(failed.status_code, 200)
            failed_task.refresh_from_db()
            self.assertEqual(failed_task.status, AiTask.Status.FAILED)

    def test_ai_task_complete_marks_unapplicable_fill_result_failed(self):
        from core.ai_tasks import create_ai_task

        user = self.create_finished_candidate("ai-fill-empty@example.com")
        interview = Interview.objects.create(user=user)
        task = create_ai_task(
            AiTask.Type.INTERVIEW_RESULT_FILL,
            interview,
            {"fields_schema": {"other_notes": "Other notes"}, "transcript": "hello"},
            source_version="fill-v1",
        )
        task.status = AiTask.Status.PROCESSING
        task.locked_by = "worker-1"
        task.save(update_fields=["status", "locked_by"])

        with override_settings(AI_SERVICE_TOKEN="secret"):
            response = self.client.post(
                reverse("ai_task_complete", args=[task.pk]),
                {"worker_id": "worker-1", "result": {"answers": {"unknown_field": "value"}}},
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer secret",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], AiTask.Status.FAILED)
        task.refresh_from_db()
        interview.refresh_from_db()
        self.assertEqual(task.status, AiTask.Status.FAILED)
        self.assertIn("no applicable", task.error)
        self.assertEqual(interview.ai_fill_status, interview.AiFillStatus.FAILED)

    def test_ai_file_proxy_downloads_yandex_disk_file_and_deletes_temp_file(self):
        from core.ai_tasks import file_response_from_token, make_file_token

        user = self.create_finished_candidate("ai-file@example.com")
        video = ScholarVideo.objects.create(
            user=user,
            yandex_disk_path="disk:/candidate/video.mp4",
            schedule_yandex_disk_path="disk:/candidate/schedule.pdf",
        )

        created_files = []

        def fake_download(disk_path, local_path, *, log_context=None):
            created_files.append(local_path)
            with open(local_path, "wb") as fh:
                fh.write(f"downloaded:{disk_path}".encode("utf-8"))

        token = make_file_token("scholar_form", "scholarvideo", video.pk, "schedule_file")

        with patch("scholar_form.services.yandex_disk.download_file_from_yandex_disk", side_effect=fake_download):
            response = file_response_from_token(token)
            body = b"".join(response.streaming_content)
            temp_path = created_files[0]
            self.assertTrue(os.path.exists(temp_path))
            response.close()

        self.assertEqual(body, b"downloaded:disk:/candidate/schedule.pdf")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="schedule.pdf"')
        self.assertFalse(os.path.exists(temp_path))

    def test_ai_file_proxy_downloads_interview_yandex_disk_video(self):
        from core.ai_tasks import file_response_from_token, make_file_token

        user = self.create_finished_candidate("ai-interview-file@example.com")
        interview = Interview.objects.create(
            user=user,
            video_source_type="yandex_disk_path",
            video_yandex_disk_path="disk:/interviews/interview.mp4",
            video_name="interview.mp4",
        )
        created_files = []

        def fake_download(disk_path, local_path, *, log_context=None):
            created_files.append(local_path)
            with open(local_path, "wb") as fh:
                fh.write(f"interview:{disk_path}".encode("utf-8"))

        token = make_file_token("review_by_tutor", "interview", interview.pk, "video")

        with patch("scholar_form.services.yandex_disk.download_file_from_yandex_disk", side_effect=fake_download):
            response = file_response_from_token(token)
            body = b"".join(response.streaming_content)
            temp_path = created_files[0]
            self.assertTrue(os.path.exists(temp_path))
            response.close()

        self.assertEqual(body, b"interview:disk:/interviews/interview.mp4")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="interview.mp4"')
        self.assertFalse(os.path.exists(temp_path))

    def test_enqueue_ai_tasks_command_counts_created_tasks(self):
        from django.core.management import call_command

        user = self.create_finished_candidate("ai-command@example.com")
        MotivationLetter.objects.create(
            user=user,
            letter_text="submitted letter",
            status=MotivationLetter.Status.SUBMITTED,
        )
        Interview.objects.create(
            user=user,
            video_source_type="yandex_disk_path",
            video_yandex_disk_path="disk:/interviews/command.mp4",
            video_name="command.mp4",
            transcript_status="PENDING",
        )
        ScholarVideo.objects.create(user=user, yandex_disk_path="disk:/video-command.mp4")
        AiTask.objects.all().delete()

        out = StringIO()
        call_command("enqueue_ai_tasks", stdout=out)

        output = out.getvalue()
        self.assertIn("motivation_letter_review=1", output)
        self.assertIn("interview_transcription=1", output)
        self.assertIn("scholar_video_transcription=1", output)
        self.assertEqual(AiTask.objects.filter(task_type=AiTask.Type.MOTIVATION_LETTER_REVIEW).count(), 1)
        self.assertEqual(AiTask.objects.filter(task_type=AiTask.Type.INTERVIEW_TRANSCRIPTION).count(), 1)
        self.assertEqual(AiTask.objects.filter(task_type=AiTask.Type.SCHOLAR_VIDEO_TRANSCRIPTION).count(), 1)

    def test_interview_yandex_link_helpers_support_file_folder_and_public_url(self):
        from review_by_tutor import views

        self.assertEqual(
            views._normalize_interview_video_source("disk:/folder/video.mp4"),
            ("yandex_disk_path", "disk:/folder/video.mp4"),
        )
        self.assertEqual(
            views._normalize_interview_video_source("folder/video.mp4"),
            ("yandex_disk_path", "disk:/folder/video.mp4"),
        )
        self.assertEqual(
            views._normalize_interview_video_source("https://disk.yandex.ru/i/abc"),
            ("yandex_public_url", "https://disk.yandex.ru/i/abc"),
        )

        folder = {
            "type": "dir",
            "_embedded": {
                "items": [
                    {"type": "file", "name": "notes.txt", "mime_type": "text/plain"},
                    {"type": "file", "name": "interview.mp4", "mime_type": "video/mp4", "size": 100},
                ]
            },
        }
        self.assertEqual(views._single_video_from_folder(folder)["name"], "interview.mp4")

        user = self.create_finished_candidate("ai-link-helper@example.com")
        interview = Interview.objects.create(user=user)
        with patch(
            "review_by_tutor.views.get_resource_metadata",
            return_value={"type": "file", "name": "private.mp4", "mime_type": "video/mp4", "size": 123},
        ):
            views._apply_interview_video_link(interview, "disk:/interviews/private.mp4", user)

        self.assertEqual(interview.video_source_type, "yandex_disk_path")
        self.assertEqual(interview.video_yandex_disk_path, "disk:/interviews/private.mp4")
        self.assertEqual(interview.video_name, "private.mp4")
        self.assertEqual(interview.transcript_status, "PENDING")

    def test_interview_public_folder_link_selects_single_video(self):
        from review_by_tutor import views

        user = self.create_finished_candidate("ai-public-folder@example.com")
        interview = Interview.objects.create(user=user)
        metadata = {
            "type": "dir",
            "_embedded": {
                "items": [
                    {
                        "type": "file",
                        "name": "public-video.webm",
                        "path": "/public-video.webm",
                        "mime_type": "video/webm",
                        "size": 321,
                    }
                ]
            },
        }
        response = SimpleNamespace(
            status_code=206,
            headers={"Content-Type": "video/webm", "Content-Length": "321"},
            close=lambda: None,
        )

        with patch("review_by_tutor.views.get_public_resource_metadata", return_value=metadata), \
             patch("review_by_tutor.views.get_public_download_url", return_value="https://download.example/video"), \
             patch("review_by_tutor.views.requests.head", return_value=SimpleNamespace(status_code=405, headers={}, url="")), \
             patch("review_by_tutor.views.requests.get", return_value=response):
            views._apply_interview_video_link(interview, "https://disk.yandex.ru/d/public", user)

        self.assertEqual(interview.video_source_type, "yandex_public_url")
        self.assertEqual(interview.video_yandex_disk_path, "/public-video.webm")
        self.assertEqual(interview.video_name, "public-video.webm")
        self.assertEqual(interview.video_mime, "video/webm")


class CorePageFlowTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_finished_candidate("feedback@example.com")
        self.client.force_login(self.user)

    @patch("core.views.send_email_message")
    def test_feedback_page_sends_message_and_renders_failure(self, send_email):
        response = self.client.get(reverse("feedback"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("feedback"), {"message": "Need help with documents"})
        self.assertRedirects(response, reverse("feedback"))
        send_email.assert_called_once()

        send_email.side_effect = RuntimeError("smtp is down")
        response = self.client.post(reverse("feedback"), {"message": "Need help again"})
        self.assertEqual(response.status_code, 200)

    def test_notifications_dropdown_returns_unseen_notifications(self):
        first = Notification.objects.create(message="First")
        seen = Notification.objects.create(message="Seen")
        UserNotification.objects.create(recipient=self.user, notification=first, is_seen=False)
        UserNotification.objects.create(recipient=self.user, notification=seen, is_seen=True)

        response = self.client.get(reverse("notifications_dropdown"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First")
        self.assertNotContains(response, "Seen")

    def test_motivation_autosave_creates_and_keeps_submitted_letter(self):
        response = self.client.post(
            reverse("motivation_letter_autosave"),
            {"letter_text": "Draft text"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        letter = MotivationLetter.objects.get(user=self.user)
        self.assertEqual(letter.letter_text, "Draft text")
        self.assertEqual(letter.status, MotivationLetter.Status.DRAFT)

        letter.status = MotivationLetter.Status.SUBMITTED
        letter.save(update_fields=["status"])
        response = self.client.post(
            reverse("motivation_letter_autosave"),
            {"letter_text": "Ignored after submit"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        letter.refresh_from_db()
        self.assertEqual(letter.letter_text, "Draft text")

    def test_motivation_letter_form_allows_twenty_thousand_chars(self):
        from core.forms import MotivationLetterForm

        form = MotivationLetterForm(data={"letter_text": "x" * 20000})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fields["letter_text"].max_length, 20000)
        self.assertEqual(form.fields["letter_text"].widget.attrs["maxlength"], "20000")

        too_long = MotivationLetterForm(data={"letter_text": "x" * 20001})
        self.assertFalse(too_long.is_valid())

    def test_motivation_letter_form_exposes_limit_and_autosave_attrs(self):
        from core.forms import MOTIVATION_LETTER_MAX_LENGTH, MotivationLetterForm

        form = MotivationLetterForm()
        field = form.fields["letter_text"]
        attrs = field.widget.attrs

        self.assertEqual(MOTIVATION_LETTER_MAX_LENGTH, 20000)
        self.assertEqual(field.max_length, 20000)
        self.assertEqual(attrs["maxlength"], "20000")
        self.assertEqual(attrs["data-maxlen"], "20000")
        self.assertEqual(attrs["rows"], 15)
        self.assertEqual(attrs["hx-post"], reverse("motivation_letter_autosave"))
        self.assertEqual(attrs["hx-trigger"], "input changed delay:800ms")

        submitted = MotivationLetter.objects.create(
            user=self.user,
            letter_text="Already submitted",
            status=MotivationLetter.Status.SUBMITTED,
        )
        submitted_form = MotivationLetterForm(instance=submitted)
        self.assertTrue(submitted_form.fields["letter_text"].disabled)

    def test_motivation_letter_model_validates_length_and_submission_rules(self):
        exact_limit = MotivationLetter(
            user=self.user,
            letter_text="x" * 20000,
            status=MotivationLetter.Status.DRAFT,
        )
        exact_limit.full_clean()
        self.assertEqual(exact_limit.word_count(), 1)

        too_long = MotivationLetter(
            user=self.user,
            letter_text="x" * 20001,
            status=MotivationLetter.Status.DRAFT,
        )
        with self.assertRaises(ValidationError):
            too_long.full_clean()

        blank_submitted = MotivationLetter(
            user=self.user,
            letter_text="   ",
            status=MotivationLetter.Status.SUBMITTED,
        )
        with self.assertRaises(ValidationError):
            blank_submitted.full_clean()

        submitted = MotivationLetter.objects.create(
            user=self.user,
            letter_text="First second third",
            status=MotivationLetter.Status.SUBMITTED,
        )
        self.assertTrue(submitted.is_done)
        self.assertIsNotNone(submitted.submitted_at)
        self.assertEqual(submitted.word_count(), 3)

    def test_motivation_autosave_rejects_over_limit_and_keeps_previous_text(self):
        response = self.client.post(
            reverse("motivation_letter_autosave"),
            {"letter_text": "Saved draft"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("motivation_letter_autosave"),
            {"letter_text": "x" * 20001},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)

        letter = MotivationLetter.objects.get(user=self.user)
        self.assertEqual(letter.letter_text, "Saved draft")
        self.assertEqual(letter.status, MotivationLetter.Status.DRAFT)


class DocumentAndStudyPageFlowTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_finished_candidate("study-docs@example.com")
        self.client.force_login(self.user)
        self.subject = Subject.objects.create(name="Math", slug="math")
        self.school = School.objects.create(name="School A", description="STEM")
        self.course = Course.objects.create(
            school=self.school,
            subject=self.subject,
            title="Algebra",
            description="Equations",
        )

    def test_document_dashboard_upload_serve_delete_and_forbid_other_user(self):
        upload = SimpleUploadedFile("statement.txt", b"plain text body", content_type="text/plain")
        with patch("documents.forms.DocumentUploadForm.clean_file", return_value=upload):
            response = self.client.post(
                reverse("documents_dashboard"),
                {"form_type": "general_document_form", "caption": "Statement", "file": upload},
            )
        self.assertRedirects(response, reverse("documents_dashboard"))
        document = Document.objects.get(user=self.user)

        response = self.client.get(reverse("serve_document", args=[document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")

        stranger = self.create_finished_candidate("stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.get(reverse("serve_document", args=[document.id]))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_document", args=[document.id]))
        self.assertRedirects(response, reverse("documents_dashboard"))
        document.refresh_from_db()
        self.assertTrue(document.is_deleted)

    @patch("documents.views.render_docx_bytes", return_value=b"docx bytes")
    def test_staff_template_list_and_params_render_docx(self, render_docx):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        target = self.create_finished_candidate("template-target@example.com")
        tpl = DocTemplate.objects.create(
            name="Agreement",
            file=SimpleUploadedFile("template.docx", b"template"),
            required_params={"signed_at": {"type": "date"}, "amount": {"type": "text"}},
        )

        response = self.client.get(reverse("staff_docs_templates", args=[target.id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("staff_docs_generate", args=[tpl.id, target.id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("staff_docs_generate", args=[tpl.id, target.id]),
            {"signed_at": "2026-05-11", "amount": "1000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"docx bytes")
        render_docx.assert_called_once()

    def test_study_pages_filter_select_unselect_university_and_assessment(self):
        response = self.client.get(reverse("study:schools"), {"q": "Algebra", "subject": self.subject.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Algebra")

        response = self.client.get(reverse("study:select_course", args=[self.course.id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("study:select_course", args=[self.course.id]),
            {"motivation": "I need this", "need_tutor": "on"},
        )
        self.assertRedirects(response, reverse("study:schools"))
        self.assertTrue(CourseSelection.objects.filter(user=self.user, course=self.course).exists())

        response = self.client.post(reverse("study:unselect_course", args=[self.course.id]))
        self.assertRedirects(response, reverse("study:schools"))
        self.assertFalse(CourseSelection.objects.filter(user=self.user, course=self.course).exists())

        response = self.client.post(
            reverse("study:universities"),
            {
                "university": "Tomsk State",
                "city": "Tomsk",
                "specialty": "CS",
                "priority": 1,
                "subjects": [self.subject.id],
                "notes": "target",
            },
        )
        self.assertRedirects(response, reverse("study:universities"))
        priority = UniversityPriority.objects.get(user=self.user)
        self.assertEqual(priority.subjects.get(), self.subject)

        response = self.client.get(reverse("study:delete_university_priority", args=[priority.id]))
        self.assertRedirects(response, reverse("study:universities"))
        self.assertFalse(UniversityPriority.objects.filter(user=self.user).exists())

        ProgressTrackerFile.objects.create(
            title="Tracker",
            file=SimpleUploadedFile("tracker.xlsx", b"xlsx"),
        )
        response = self.client.post(
            reverse("study:assessments"),
            {
                "kind": AssessmentResult.Kind.TEST,
                "subject": self.subject.id,
                "title": "May test",
                "date": "2026-05-11",
                "score": "80",
                "max_score": "100",
            },
        )
        self.assertRedirects(response, reverse("study:assessments"))
        self.assertEqual(AssessmentResult.objects.get(user=self.user).percent, 80)
