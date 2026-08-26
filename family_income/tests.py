from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from documents.models import Document
from scholar_form.models import UserInfo

from .forms import IncomeDocumentForm, SocialBenefitDocumentForm
from .models import (
    FamilyIncomeCase, FamilyIncomeDocument, IncomeEvidence, IncomeYear,
    SocialBenefitEvidence, SocialBenefitType,
)


class FamilyIncomeUserFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="finalist", password="password")
        self.info = UserInfo.objects.create(user=self.user, status="FINAL STAGE")
        self.client.force_login(self.user)
        self.year = IncomeYear.objects.get(year=2025)
        self.other_benefit = SocialBenefitType.objects.get(name="Другое")

    def _case(self):
        return FamilyIncomeCase.objects.get(user_info=self.info)

    def _other_document(self, *, review_status=FamilyIncomeDocument.ReviewStatus.PENDING):
        case = self._case()
        document = Document.objects.create(
            user=self.user,
            caption="Справка",
            user_file_name="old.pdf",
            yandex_disk_path="disk:/documents/old.pdf",
        )
        return FamilyIncomeDocument.objects.create(
            case=case,
            document=document,
            category=FamilyIncomeDocument.Category.OTHER,
            candidate_comment="Справка",
            review_status=review_status,
        )

    def _document_for_category(self, category):
        case = self._case()
        document = Document.objects.create(user=self.user, caption=category, yandex_disk_path=f"disk:/{category}.pdf")
        return FamilyIncomeDocument.objects.create(
            case=case,
            document=document,
            category=category,
            candidate_comment=category,
        )

    def test_finalist_can_open_page_and_non_finalist_cannot(self):
        response = self.client.get(reverse("family_income:page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Состав семьи")

        other = User.objects.create_user(username="candidate", password="password")
        UserInfo.objects.create(user=other, status="CANDIDATE")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("family_income:page")).status_code, 404)

    def test_income_allows_empty_amounts(self):
        form = IncomeDocumentForm(
            data={"income-year": self.year.pk, "income-owner_name": "Мама"},
            files={"income-file": SimpleUploadedFile("income.pdf", b"%PDF-1.4")},
            prefix="income",
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_social_benefit_requires_name(self):
        form = SocialBenefitDocumentForm(
            data={
                "social_benefit-recipient_name": "Мама",
                "social_benefit-benefit_type": self.other_benefit.pk,
            },
            files={"social_benefit-file": SimpleUploadedFile("benefit.pdf", b"%PDF-1.4")},
            prefix="social_benefit",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("other_benefit_name", form.errors)

    @patch("family_income.views.upload_file_to_yandex_disk")
    @patch("documents.forms.magic.from_buffer", return_value="application/pdf", create=True)
    def test_income_document_creates_metadata(self, _mime, _upload):
        response = self.client.post(
            reverse("family_income:add_document", args=[FamilyIncomeDocument.Category.INCOME]),
            {
                "income-file": SimpleUploadedFile("income.pdf", b"%PDF-1.4"),
                "income-year": self.year.pk,
                "income-owner_name": "Мама",
            },
        )
        self.assertRedirects(response, reverse("family_income:page"))
        evidence = IncomeEvidence.objects.get()
        self.assertEqual(evidence.year, self.year)
        self.assertEqual(evidence.owner_name, "Мама")
        self.assertIsNone(evidence.gross_amount)

    @patch("family_income.views.upload_file_to_yandex_disk")
    @patch("documents.forms.magic.from_buffer", return_value="application/pdf", create=True)
    def test_social_benefit_document_creates_metadata(self, _mime, _upload):
        response = self.client.post(
            reverse("family_income:add_document", args=[FamilyIncomeDocument.Category.SOCIAL_BENEFIT]),
            {
                "social_benefit-file": SimpleUploadedFile("benefit.pdf", b"%PDF-1.4"),
                "social_benefit-recipient_name": "Мама",
                "social_benefit-benefit_type": self.other_benefit.pk,
                "social_benefit-other_benefit_name": "Ежемесячное пособие",
            },
        )
        self.assertRedirects(response, reverse("family_income:page"))
        evidence = SocialBenefitEvidence.objects.get()
        self.assertEqual(evidence.recipient_name, "Мама")
        self.assertEqual(evidence.other_benefit_name, "Ежемесячное пособие")

    def test_user_cannot_access_another_family_document(self):
        self.client.get(reverse("family_income:page"))
        other = User.objects.create_user(username="other-finalist", password="password")
        other_info = UserInfo.objects.create(user=other, status="FINAL STAGE")
        other_case = FamilyIncomeCase.objects.create(
            user_info=other_info,
            family_members_count=2,
            family_members_description="Семья",
            status=FamilyIncomeCase.Status.REVISION,
        )
        document = Document.objects.create(user=other, caption="Чужой", yandex_disk_path="disk:/other.pdf")
        item = FamilyIncomeDocument.objects.create(
            case=other_case,
            document=document,
            category=FamilyIncomeDocument.Category.OTHER,
            candidate_comment="Чужой",
        )
        self.assertEqual(self.client.get(reverse("family_income:edit_document", args=[item.pk])).status_code, 404)

    def test_confirmed_document_is_not_deleted(self):
        self.client.get(reverse("family_income:page"))
        item = self._other_document(review_status=FamilyIncomeDocument.ReviewStatus.APPROVED)
        response = self.client.post(reverse("family_income:delete_document", args=[item.pk]))
        self.assertRedirects(response, reverse("family_income:page"))
        self.assertTrue(FamilyIncomeDocument.objects.filter(pk=item.pk).exists())

    def test_confirmed_document_is_not_editable(self):
        self.client.get(reverse("family_income:page"))
        item = self._other_document(review_status=FamilyIncomeDocument.ReviewStatus.APPROVED)
        response = self.client.get(reverse("family_income:edit_document", args=[item.pk]))
        self.assertRedirects(response, reverse("family_income:page"))

    def test_case_is_read_only_outside_revision(self):
        self.client.get(reverse("family_income:page"))
        case = self._case()
        case.status = FamilyIncomeCase.Status.PENDING_REVIEW
        case.save(update_fields=("status",))
        response = self.client.post(
            reverse("family_income:page"),
            {"family_members_count": 5, "family_members_description": "Новый состав", "family_characteristics": ""},
        )
        self.assertRedirects(response, reverse("family_income:page"))
        case.refresh_from_db()
        self.assertEqual(case.family_members_count, 1)

    def test_submit_requires_family_description(self):
        self.client.get(reverse("family_income:page"))
        response = self.client.post(reverse("family_income:submit"))
        self.assertRedirects(response, reverse("family_income:page"))
        self.assertEqual(self._case().status, FamilyIncomeCase.Status.REVISION)

    def test_submit_locks_case_without_documents(self):
        self.client.get(reverse("family_income:page"))
        case = self._case()
        case.family_members_description = "Мама работает, ребёнок учится"
        case.save(update_fields=("family_members_description",))
        response = self.client.post(reverse("family_income:submit"))
        self.assertRedirects(response, reverse("family_income:page"))
        case.refresh_from_db()
        self.assertEqual(case.status, FamilyIncomeCase.Status.PENDING_REVIEW)

    @patch("family_income.views.delete_resource")
    @patch("family_income.views.upload_file_to_yandex_disk")
    @patch("documents.forms.magic.from_buffer", return_value="application/pdf", create=True)
    def test_edit_replaces_file(self, _mime, _upload, _delete):
        self.client.get(reverse("family_income:page"))
        item = self._other_document()
        response = self.client.post(
            reverse("family_income:edit_document", args=[item.pk]),
            {
                "other-file": SimpleUploadedFile("new.pdf", b"%PDF-1.4"),
                "other-candidate_comment": "Новая справка",
            },
        )
        self.assertRedirects(response, reverse("family_income:page"))
        item.document.refresh_from_db()
        self.assertEqual(item.document.user_file_name, "new.pdf")
        self.assertEqual(item.document.caption, "Новая справка")
