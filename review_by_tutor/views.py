import logging
import mimetypes

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, Count, Exists
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import ensure_registration_gate
from core.models import MotivationLetter, Notification, UserNotification
from documents.models import Document
from my_study.models import CourseSelection, UniversityPriority, AssessmentResult, School, Course
from review_by_tutor.forms import MotivationLetterStaffForm, UserInfoStaffForm, ScholarVideoStaffForm, \
    DocumentStaffUploadForm, DocumentCommentForm, DocumentLockForm, \
    DocumentStatusForm, InterviewForm, TestAssignmentCreateForm, TestAssignmentEditForm, TestResultForm
from review_by_tutor.models import Interview, TestAssignment, InterviewPreparation
from scholar_form.models import UserInfo, ScholarVideo, StaffNote

logger = logging.getLogger(__name__)
User = get_user_model()


def _staff_check(user):
    return user.is_staff


@login_required
@user_passes_test(_staff_check)
@transaction.atomic
def staff_letter_detail(request, user_id: int):
    user = get_object_or_404(User, pk=user_id)

    letter = (
        MotivationLetter.objects.select_related("user")
        .filter(user_id=user_id)
        .first()
    )

    if request.method == "POST":
        if letter is None:
            messages.error(request, "У пользователя ещё нет мотивационного письма — сохранять нечего.")
            return redirect("staff_letter_detail", user_id=user_id)

        form = MotivationLetterStaffForm(request.POST, instance=letter)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            messages.success(request, "Оценка/фидбэк сохранены.")
            return redirect("staff_letter_detail", user_id=user_id)
        else:
            messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = MotivationLetterStaffForm(instance=letter) if letter else None

    readonly_ctx = {
        "status": getattr(letter, "status", None),
        "submitted_at": getattr(letter, "submitted_at", None),
        "gpt_review": getattr(letter, "gpt_review", None),
        "gpt_score": getattr(letter, "gpt_score", None),
        "gpt_word_count": getattr(letter, "gpt_word_count", None) or (letter.word_count() if letter else None),
        'gpt_json': letter.gpt_json if letter and letter.gpt_json else None,
    }

    ctx = {
        "user_obj": user,
        "letter": letter,
        "form": form,
        'active': 'motivation_letter',
        'readonly': readonly_ctx,
    }
    return render(request, "staff_templates/letter_detail.html", ctx)


@login_required
@user_passes_test(_staff_check)
@transaction.atomic
def staff_profile_detail(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)
    profile = get_object_or_404(UserInfo.objects.select_related("user"), user_id=user_id)

    if request.method == "POST":
        form = UserInfoStaffForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Фидбэк/статус анкеты сохранены.")
            logger.info("Staff %s updated user_info for user_id=%s", request.user.pk, user_id)
            return redirect("staff_profile_detail", user_id=user_id)
        messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = UserInfoStaffForm(instance=profile)

    return render(request, "staff_templates/profile_details.html", {
        "profile": profile,
        "user_obj": user_obj,
        "form": form,
        "active": "apply",
    })


@login_required
@user_passes_test(_staff_check)
@transaction.atomic
def staff_video_detail(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)

    video = (ScholarVideo.objects
             .select_related("user")
             .filter(user_id=user_id)
             .first())

    if request.method == "POST":
        if not video:
            messages.error(request, "У пользователя ещё нет загруженного видео — нечего оценивать.")
            return redirect("staff_video_detail", user_id=user_id)

        form = ScholarVideoStaffForm(request.POST, instance=video)
        if form.is_valid():
            form.save()
            messages.success(request, "Отзыв/оценка по видео сохранены.")
            logger.info("Staff %s updated ScholarVideo for user_id=%s", request.user.pk, user_id)
            return redirect("staff_video_detail", user_id=user_id)
        else:
            messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = ScholarVideoStaffForm(instance=video) if video else None

    mime = None
    if video:
        try:
            file_name = getattr(getattr(video, "file", None), "name", "") or ""
            if file_name:
                mime, _ = mimetypes.guess_type(file_name)
        except Exception:
            mime = None

    return render(request, "staff_templates/video_detail.html", {
        "user_obj": user_obj,
        "video": video,
        "video_mime": mime,
        "form": form,
        "active": "my_video_page",
    })


@login_required
@user_passes_test(_staff_check)
@transaction.atomic
def staff_documents_detail(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)
    docs = (Document.objects
            .filter(user_id=user_id)
            .prefetch_related("related_documents")
            .order_by("-uploaded_at", "-id"))

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type in {"update_status", "update_lock", "update_comment"}:
            doc_id = request.POST.get("document_id")
            doc = get_object_or_404(Document, pk=doc_id, user_id=user_id)

            if form_type == "update_status":
                prefix = f"st-{doc.pk}"
                form = DocumentStatusForm(request.POST, instance=doc, prefix=prefix)
            elif form_type == "update_lock":
                prefix = f"lk-{doc.pk}"
                form = DocumentLockForm(request.POST, instance=doc, prefix=prefix)
            else:
                prefix = f"cm-{doc.pk}"
                form = DocumentCommentForm(request.POST, instance=doc, prefix=prefix)

            if form.is_valid():
                obj = form.save(commit=False)
                obj._ignore_lock_validation = True
                obj.save()
                messages.success(request, "Изменения сохранены.")
            else:
                logger.warning("Doc form errors for #%s: %s", doc.pk, form.errors)
                messages.error(request, "Исправьте ошибки в форме.")
            return redirect("staff_documents_detail", user_id=user_id)

        elif form_type == "upload_staff_document":
            upload_form = DocumentStaffUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                new_doc = upload_form.save(commit=False)
                new_doc.user = user_obj
                new_doc.uploaded_by_staff = True
                new_doc._ignore_lock_validation = True
                new_doc.save()
                messages.success(request, "Документ загружен.")
            else:
                messages.error(request, "Не удалось загрузить документ. Проверьте форму.")
        else:
            messages.error(request, "Неизвестный тип формы.")
            return redirect("staff_documents_detail", user_id=user_id)

    rows = []
    for d in docs:
        rows.append((
            d,
            DocumentStatusForm(instance=d, prefix=f"st-{d.pk}"),
            DocumentLockForm(instance=d, prefix=f"lk-{d.pk}"),
            DocumentCommentForm(instance=d, prefix=f"cm-{d.pk}"),
        ))
    upload_form = locals().get("upload_form", DocumentStaffUploadForm())

    return render(request, "staff_templates/documents_detail.html", {
        "user_obj": user_obj,
        "rows": rows,
        "upload_form": upload_form,
        "active": "documents_dashboard",
    })


@login_required
@user_passes_test(_staff_check)
def staff_study_detail(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)

    selections = (
        CourseSelection.objects
        .select_related("course__school", "course__subject")
        .filter(user_id=user_id)
        .order_by("-created_at", "-id")
    )

    priorities = (
        UniversityPriority.objects
        .filter(user_id=user_id)
        .order_by("priority", "id")
    )

    assessments = (
        AssessmentResult.objects
        .select_related("subject")
        .filter(user_id=user_id)
        .order_by("-date", "-id")
    )

    return render(request, "staff_templates/study_detail.html", {
        "user_obj": user_obj,
        "selections": selections,
        "priorities": priorities,
        "assessments": assessments,
        "active": "study",

    })


@login_required
@user_passes_test(_staff_check)
def staff_notes_by_user(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        text = (request.POST.get("text") or "").strip()
        if text:
            StaffNote.objects.create(target_user=user_obj, author=request.user, text=text)
            messages.success(request, "Запись добавлена.")
            return redirect("staff_notes", user_id=user_id)
        messages.error(request, "Текст записи обязателен.")

    notes_qs = (StaffNote.objects
                .select_related("author")
                .filter(target_user=user_obj)
                .order_by("-created_at"))

    page = request.GET.get("page", 1)
    paginator = Paginator(notes_qs, 5)
    try:
        notes = paginator.page(page)
    except PageNotAnInteger:
        notes = paginator.page(1)
    except EmptyPage:
        notes = paginator.page(paginator.num_pages)

    try:
        letter = MotivationLetter.objects.select_related("user").get(user=user_obj)
    except MotivationLetter.DoesNotExist:
        letter = None

    documents = (Document.objects
                 .filter(user=user_obj, is_deleted=False)
                 .order_by("-uploaded_at")[:50])

    try:
        video = ScholarVideo.objects.select_related("user").get(user=user_obj)
    except ScholarVideo.DoesNotExist:
        video = None

    ctx = {
        "user_obj": user_obj,
        "notes": notes,
        "total_count": paginator.count,
        "letter": letter,
        "documents": documents,
        "video": video,
        "active": "notes",
    }
    return render(request, "staff_templates/staff_notes_by_user.html", ctx)


@login_required
@user_passes_test(_staff_check)
def staff_users_list(request):
    q = (request.GET.get("q") or "").strip()
    school = (request.GET.get("school") or "").strip()
    course = (request.GET.get("course") or "").strip()
    curator_paid = (request.GET.get("curator_need") or "").strip()
    grade = (request.GET.get("grade") or "").strip()

    qs = (User.objects
          .all()
          .select_related("user_info")
          )

    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(user_info__phone__icontains=q) |
            Q(user_info__region__icontains=q)
        )

    if school:
        qs = qs.filter(course_selections__course__school_id=school)

    if course:
        qs = qs.filter(course_selections__course_id=course)

    if grade:
        qs = qs.filter(user_info__grade=grade)

    if curator_paid == "1":
        qs = qs.filter(course_selections__need_tutor=True)
    elif curator_paid == "0":
        qs = qs.filter(course_selections__need_tutor=False)

    qs = qs.distinct()

    letter_status_sq = Subquery(
        MotivationLetter.objects.filter(user_id=OuterRef("pk"))
        .values("status")[:1]
    )

    qs = qs.annotate(
        docs_total=Count("documents", filter=Q(documents__is_deleted=False)),
        docs_pending=Count("documents", filter=Q(documents__is_deleted=False, documents__status="PENDING")),
        docs_question=Count("documents", filter=Q(documents__is_deleted=False, documents__status="QUESTION")),
        docs_signed=Count("documents", filter=Q(documents__is_deleted=False, documents__status="SIGNED")),
        has_profile=Exists(UserInfo.objects.filter(user_id=OuterRef("pk"))),
        has_video=Exists(ScholarVideo.objects.filter(user_id=OuterRef("pk"))),
        letter_status=letter_status_sq,
    ).order_by("last_name", "first_name", "username")

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    schools = School.objects.all().order_by("name")
    courses_qs = Course.objects.all()
    if school:
        courses_qs = courses_qs.filter(school_id=school)
    courses = courses_qs.order_by("title")

    # grades = list(range(1, 12))

    return render(request, "staff_templates/users_list.html", {
        "page_obj": page_obj,

        "q": q,
        "school": school,
        "course": course,
        "curator_need": curator_paid,
        "grade": grade,
        # "grades": grades,
        "schools": schools,
        "courses": courses,
    })


@staff_member_required
@require_POST
def staff_send_notification(request):
    raw_ids = request.POST.getlist('ids')
    message_text = (request.POST.get('message') or '').strip()
    include_inactive = request.POST.get('include_inactive') == '1'

    ids = [int(x) for x in raw_ids if str(x).isdigit()]
    if not ids:
        messages.error(request, "Не выбраны пользователи.")
        return redirect('staff_users_list')

    if not message_text:
        messages.error(request, "Введите текст сообщения.")
        return redirect('staff_users_list')

    qs = User.objects.filter(id__in=ids).only('id', 'is_active')
    if not include_inactive:
        qs = qs.filter(is_active=True)
    final_ids = list(qs.values_list('id', flat=True))
    if not final_ids:
        messages.error(request, "Нет подходящих получателей (все неактивны или не найдены).")
        return redirect('staff_users_list')

    with transaction.atomic():
        notif = Notification.objects.create(message=message_text, sender=request.user)
        for uid in final_ids:
            link, created = UserNotification.objects.get_or_create(notification=notif, recipient_id=uid)

    logger.info(f'Оповещение {notif.pk} создано для {len(final_ids)} пользователей')
    messages.success(request, f"Оповещение «{message_text[:50]}…» отправлено {len(final_ids)} пользователям.")
    return redirect('staff_users_list')


@login_required
@user_passes_test(_staff_check)
def interview_detail(request, user_id: int):
    user_obj = get_object_or_404(User, pk=user_id)
    interview, _ = Interview.objects.get_or_create(user=user_obj)

    if request.method == "POST":
        form = InterviewForm(request.POST, instance=interview)
        if form.is_valid():
            form.save()
            messages.success(request, "Изменения сохранены.")
            return redirect("interview_detail", user_id=user_id)
    else:
        form = InterviewForm(instance=interview)

    ctx = {
        "user_obj": user_obj,
        "form": form,
        "interview": interview,
        'active': 'interview'
    }
    return render(request, "staff_templates/interview_detail.html", ctx)


@login_required
def testing_list_for_candidate(request):
    items = (TestAssignment.objects
             .filter(user=request.user)
             .order_by("-assigned_at", "-id"))
    return render(request, "testing.html", {"items": items, "user_obj": request.user, "active": "testing"})


@user_passes_test(_staff_check)
def testing_list_for_user(request, user_id):
    items = (TestAssignment.objects
             .select_related("user", "assigned_by", "result_filled_by")
             .filter(user_id=user_id)
             .order_by("-assigned_at", "-id"))
    return render(request, "staff_templates/testing/list.html",
                  {"items": items, "target_user_id": user_id, "user_obj": get_object_or_404(User, pk=user_id),
                   "active": 'testing'})


@user_passes_test(_staff_check)
def testing_create(request):
    fixed_user_id = request.GET.get("user_id")

    fixed_user = None
    if fixed_user_id:
        fixed_user = User.objects.filter(pk=fixed_user_id).only("id").first()

    if request.method == "POST":
        form = TestAssignmentCreateForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if fixed_user:
                obj.user = fixed_user
            obj.assigned_by = request.user
            obj.save()
            return redirect("staff_testing_list_for_user", user_id=obj.user_id)
    else:
        if fixed_user:
            form = TestAssignmentCreateForm(initial={"user": fixed_user.id})
        else:
            form = TestAssignmentCreateForm()

    return render(request, "staff_templates/testing/form.html", {
        "form": form,
        "title": "Назначить тест",
        "fixed_user": fixed_user,

    })


@user_passes_test(_staff_check)
def testing_edit(request, pk):
    obj = get_object_or_404(TestAssignment, pk=pk)
    if request.method == "POST":
        form = TestAssignmentEditForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect("staff_testing_list_for_user", user_id=obj.user_id)
    else:
        form = TestAssignmentEditForm(instance=obj)
    return render(request, "staff_templates/testing/form.html",
                  {"form": form, "title": "Редактировать тест", "user_obj": get_object_or_404(User, pk=obj.user.id)})


@user_passes_test(_staff_check)
def testing_fill_result(request, pk):
    obj = get_object_or_404(TestAssignment, pk=pk)
    if request.method == "POST":
        form = TestResultForm(request.POST, instance=obj)
        if form.is_valid():
            filled = form.save(commit=False)
            filled.result_filled_by = request.user
            filled.result_filled_at = timezone.now()
            filled.mark_completed()
            filled.save()
            return redirect("staff_testing_list_for_user", user_id=obj.user_id)
    else:
        form = TestResultForm(instance=obj)
    return render(request, "staff_templates/testing/result_form.html",
                  {"form": form, "obj": obj, "user_obj": get_object_or_404(User, pk=obj.user.id), "active": "testing"})


@ensure_registration_gate('protected')
@login_required
def interview_preparation_view(request):
    prep = (
        InterviewPreparation.objects
        .filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )

    return render(request, "interview_preparation.html", {"prep": prep, "active": "interview"})
