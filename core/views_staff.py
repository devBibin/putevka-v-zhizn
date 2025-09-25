from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from core.models import UserNotification, Notification
from documents.models import Document

User = get_user_model()

from core.forms_staff import SetVideoScoreForm, SendNotificationForm, UploadStaffDocForm


@method_decorator(staff_member_required, name="dispatch")
class StaffScholarDossierView(TemplateView):
    template_name = "staff/scholar_dossier.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user_id = kwargs["user_id"]
        user = get_object_or_404(
            User.objects
            .select_related("user_info", "scholar_video", "telegram_account", "motivation_letter"),
            pk=user_id
        )

        documents = (Document.objects
                     .filter(user=user, is_deleted=False)
                     .order_by("-uploaded_at"))

        user_notifs = (UserNotification.objects
                       .select_related("notification")
                       .filter(recipient=user)
                       .order_by("-notification__created_at")[:50])

        ctx.update({
            "scholar": user,
            "uinfo": getattr(user, "user_info", None),
            "video": getattr(user, "scholar_video", None),
            "tg": getattr(user, "telegram_account", None),
            "ml": getattr(user, "motivation_letter", None),
            "documents": documents,
            "user_notifs": user_notifs,

            "video_form": SetVideoScoreForm(initial={
                "score": getattr(getattr(user, "scholar_video", None), "score", None),
                "review": getattr(getattr(user, "scholar_video", None), "review", ""),
            }),
            "notif_form": SendNotificationForm(),
            "upload_form": UploadStaffDocForm(),
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

    else:
        messages.error(request, "Неизвестное действие.")

    return redirect(reverse("staff_scholar_dossier", args=[user_id]))
