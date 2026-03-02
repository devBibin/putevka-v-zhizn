from django.apps import apps
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from config import BASE_URL
from core.models import UserNotification, Notification
from documents.models import Document
from review_by_tutor.forms import StatusChangeForm, ProfileChangeForm, SelectionStepUpdateForm
from scholar_form.models import UserInfo, StaffNote

User = get_user_model()

from core.forms_staff import SetVideoScoreForm, SendNotificationForm, UploadStaffDocForm


@method_decorator(staff_member_required, name="dispatch")
class StaffScholarDossierView(TemplateView):
    template_name = "staff/scholar_dossier.html"

    def _get_model_safe(self, app_label, model_name):
        try:
            return apps.get_model(app_label, model_name)
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        global notifs_page
        ctx = super().get_context_data(**kwargs)
        user_id = kwargs["user_id"]

        User = apps.get_model("auth", "User")
        user = get_object_or_404(
            User.objects.select_related("user_info", "scholar_video", "telegram_account", "motivation_letter"),
            pk=user_id
        )

        Document = self._get_model_safe("documents", "Document")
        UserNotification = self._get_model_safe("core", "UserNotification") or self._get_model_safe("notifications",
                                                                                                    "UserNotification")

        uinfo = UserInfo.objects.get_or_create(user=user)[0]
        video = getattr(user, "scholar_video", None)
        ml = getattr(user, "motivation_letter", None)

        favorite_notes = (StaffNote.objects
                          .select_related("author")
                          .filter(target_user=user, is_favorite=True)
                          .order_by("-created_at")[:5])

        video_score = getattr(video, "score", None) if video else None
        ml_score = getattr(ml, "admin_score", None) if ml else None

        status_form = StatusChangeForm(instance=uinfo)
        profile_form = ProfileChangeForm(instance=uinfo)

        questionnaire_done = bool(getattr(uinfo, "is_done", False))

        video_exists = video is not None
        video_needs_review = bool(
            video_exists and not getattr(video, "score", None) and not getattr(video, "review", ""))

        ml_exists = ml is not None
        ml_needs_review = bool(
            ml_exists
            and ml.status == ml.Status.SUBMITTED
            and ml.admin_score is None
            and not (ml.admin_rating or "").strip()
        )

        documents_qs = Document.objects.filter(user=user, is_deleted=False).order_by("-uploaded_at") if Document else []

        unseen_notifs_count = 0
        recent_notifs = []
        if UserNotification:
            try:
                notifs_qs = (UserNotification.objects
                             .select_related("notification")
                             .filter(recipient=user)
                             .order_by("-notification__created_at"))

                unseen_notifs_count = notifs_qs.filter(is_seen=False).count()

                paginator = Paginator(notifs_qs, 5)
                page_number = self.request.GET.get("page") or 1
                notifs_page = paginator.get_page(page_number)
            except Exception:
                notifs_page = None
                unseen_notifs_count = 0

        candidates = [
            getattr(user, "last_login", None),
            getattr(uinfo, "updated_at", None) if uinfo else None,
            getattr(video, "updated_at", None) if video else None,
            getattr(ml, "updated_at", None) if ml else None,
            getattr(ml, "submitted_at", None) if ml else None,
        ]
        if Document and hasattr(Document, "uploaded_at"):
            latest_doc = documents_qs[:1].first() if hasattr(documents_qs, "first") else None
            candidates.append(getattr(latest_doc, "uploaded_at", None))
        if notifs_page and notifs_page.object_list:
            first_un = notifs_page.object_list[0]
            candidates.append(getattr(first_un.notification, "created_at", None))

        last_action = max([d for d in candidates if d], default=None)

        from .forms import SendNotificationForm
        notif_form = SendNotificationForm()

        ctx.update({
            'user_obj': user,
            "summary": {
                "questionnaire_done": questionnaire_done,
                "video_exists": video_exists,
                "video_needs_review": video_needs_review,
                "ml_exists": ml_exists,
                "ml_needs_review": ml_needs_review,
                "unseen_notifs_count": unseen_notifs_count,
                "last_action": last_action,
                "video_score": video_score,
                "ml_score": ml_score,
            },
            "documents": documents_qs[:5],
            "notif_form": notif_form,
            "notifs_page": notifs_page,
            'active': 'dossier',
            "status_form": status_form,
            "profile_form": profile_form,
            "selection_step_form": SelectionStepUpdateForm(
                instance=user.user_info
            ),
            "favorite_notes": favorite_notes,
        })
        return ctx


@staff_member_required
def staff_scholar_action(request, user_id: int):
    user = get_object_or_404(User.objects.select_related("scholar_video"), pk=user_id)

    if request.method != "POST":
        return HttpResponseForbidden("POST only")

    action = request.POST.get("action")

    if action == "set_video_score":
        form = SetVideoScoreForm(request.POST)
        if form.is_valid():
            video = getattr(user, "scholar_video", None)
            if not video:
                messages.error(request, "У пользователя нет видеовизитки.")
            else:
                score = form.cleaned_data.get("score")
                review = form.cleaned_data.get("review", "")
                video.score = score if score is not None else None
                video.review = review
                video.save(update_fields=["score", "review", "updated_at"])
                messages.success(request, "Оценка/отзыв по видео сохранены.")
        else:
            messages.error(request, "Исправьте ошибки в форме оценки видео.")

    elif action == "send_notification":
        form = SendNotificationForm(request.POST)
        if form.is_valid():
            msg = form.cleaned_data["message"]
            notif = Notification.objects.create(
                message=msg,
                sender=request.user
            )
            UserNotification.objects.create(notification=notif, recipient=user)
            messages.success(request, "Оповещение создано и назначено пользователю.")
        else:
            messages.error(request, "Проверьте текст сообщения.")

    elif action == "upload_staff_doc":
        form = UploadStaffDocForm(request.POST, request.FILES)
        if form.is_valid():
            doc = Document(
                user=user,
                file=form.cleaned_data["file"],
                caption=form.cleaned_data["caption"],
                status=form.cleaned_data["status"],
                uploaded_by_staff=True,
            )
            doc.save()
            messages.success(request, "Документ загружен.")
        else:
            messages.error(request, "Не удалось загрузить документ. Проверьте поля.")

    elif action == "change_status":
        uinfo, _ = UserInfo.objects.get_or_create(user=user)
        form = StatusChangeForm(request.POST, instance=uinfo)
        if form.is_valid():
            u = form.save()
            new = u.get_status_display()
            messages.success(request, f"Статус обновлён: «{new}».")
        else:
            messages.error(request, "Не удалось обновить статус. Проверьте данные.")

    elif action == "change_profile":
        uinfo, _ = UserInfo.objects.get_or_create(user=user)
        form = ProfileChangeForm(request.POST, instance=uinfo)
        if form.is_valid():
            u = form.save()
            new = u.get_internal_study_profile_display()
            messages.success(request, f"Статус обновлён: «{new}».")
        else:
            messages.error(request, "Не удалось обновить профиль. Проверьте данные.")


    elif action == "change_selection_step":
        uinfo = user.user_info
        old_step = uinfo.selection_step
        form = SelectionStepUpdateForm(request.POST, instance=uinfo)
        if form.is_valid():
            updated_obj = form.save(commit=False)
            new_step = updated_obj.selection_step
            updated_obj.save()
            if old_step != new_step:
                notif = Notification.objects.create(
                    message=f"Теперь ты на этапе отбора: {uinfo.get_selection_step_display()}, проверь свой кабинет {BASE_URL}",
                    sender=request.user
                )
                UserNotification.objects.create(
                    notification=notif,
                    recipient=user
                )
            messages.success(request, "Этап отбора обновлён.")
        else:
            messages.error(request, "Ошибка обновления этапа.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    else:
        messages.error(request, "Неизвестное действие.")

    return redirect(reverse("staff_scholar_dossier", args=[user_id]))
