from core.forms import SendNotificationForm
from core.models import Notification, UserNotification
from django.contrib import messages


def handle_send_notification(request, recipient_user):
    form = SendNotificationForm()

    if request.method == "POST" and request.POST.get("action") == "send_notification":
        form = SendNotificationForm(request.POST)
        if form.is_valid():
            msg = form.cleaned_data["message"]
            notif = Notification.objects.create(message=msg, sender=request.user)
            UserNotification.objects.create(notification=notif, recipient=recipient_user)

            messages.success(request, "Оповещение создано и назначено пользователю.")
            form = SendNotificationForm()
        else:
            messages.error(request, "Проверьте текст сообщения.")

    return form