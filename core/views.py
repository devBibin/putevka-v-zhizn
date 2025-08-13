import logging
from datetime import timezone, datetime
from .forms import MotivationLetterForm
from .models import MotivationLetter
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction

from .forms import SendNotificationForm
from .models import UserNotification, Notification

from .bot import webhook

logger = logging.getLogger(__name__)

def index(request):
    return render(request, 'core/index.html')


def register(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('index')

        User.objects.create_user(username=username, password=password)
        messages.success(request, "Registration successful. You can now log in.")
        return redirect('index')

    return redirect('index')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome, {user.username}!")
            return redirect('index')
        else:
            messages.error(request, "Invalid credentials")
            return redirect('index')

    return redirect('index')


@login_required
def motivation_letter(request):
    user = request.user
    letter = None
    is_new_letter = True

    try:
        letter = MotivationLetter.objects.get(user=user)
        is_new_letter = False
    except MotivationLetter.DoesNotExist:
        pass

    if request.method == 'POST':
        if letter and letter.status == MotivationLetter.Status.SUBMITTED:
            messages.warning(request, 'Письмо уже отправлено и не может быть отредактировано.')
            return redirect('motivation_letter')

        form = MotivationLetterForm(request.POST, instance=letter)

        if form.is_valid():
            saved_letter = form.save(commit=False)

            if is_new_letter:
                saved_letter.user = user
            else:
                original_letter_instance = MotivationLetter.objects.get(pk=letter.pk)
                if not original_letter_instance.admin_rating:
                    saved_letter.gpt_review = None

            if 'submit' in request.POST:
                saved_letter.status = MotivationLetter.Status.SUBMITTED
                saved_letter.submitted_at = datetime.now()

                try:
                    saved_letter.full_clean()
                    saved_letter.save()
                    messages.success(request, 'Письмо отправлено. Дальнейшее редактирование невозможно.')
                    logger.info('Мотивационное письмо отправлено пользователем %s', user.pk)
                    return redirect('motivation_letter')
                except Exception as e:
                    form.add_error(None, e)
                    messages.error(request, 'Не удалось отправить письмо. Проверьте ошибки.')
            else:
                saved_letter.status = MotivationLetter.Status.DRAFT
                saved_letter.save()
                messages.success(request, 'Черновик успешно сохранён!')
                logger.info('Черновик мотивационного письма сохранён пользователем %s', user.pk)
                return redirect('motivation_letter')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = MotivationLetterForm(instance=letter)

    return render(request, 'MotivationLetter/motivation_letter.html', {
        'form': form,
        'is_new_letter': is_new_letter,
        'user': user,
        'letter': letter,
    })


def notification_list(request):
    user_notifications = UserNotification.objects.filter(recipient=request.user).order_by('is_seen',
                                                                                          '-notification__created_at')

    return render(request, 'notifications/notifications_list.html', {'notifications': user_notifications})


@login_required
@require_POST
def mark_notification_as_seen(request, user_notification_id):
    notification = get_object_or_404(UserNotification, pk=user_notification_id, recipient=request.user)

    if not notification.is_seen:
        notification.is_seen = True
        notification.seen_at = timezone.now()
        notification.save()
        logger.info(f'Оповещение {notification.pk} прочитано')

    return redirect('notifications')


@staff_member_required
def send_notification_to_users(request):
    selected_user_ids = request.session.get('selected_users_for_notification', [])

    if not selected_user_ids:
        messages.error(request, "Не выбраны пользователи для отправки оповещения.")
        return redirect('admin:auth_user_changelist')

    selected_users = User.objects.filter(id__in=selected_user_ids)

    if request.method == 'POST':
        form = SendNotificationForm(request.POST)
        if form.is_valid():
            message_text = form.cleaned_data['message']

            with transaction.atomic():
                new_notification = Notification.objects.create(message=message_text)

                user_notification_objects = [
                    UserNotification(notification=new_notification, recipient=user)
                    for user in selected_users
                ]
                UserNotification.objects.bulk_create(user_notification_objects)

            logger.info(f'Массовое оповещение {new_notification.pk} зарегистрировано')
            messages.success(request, f"Оповещение '{message_text[:30]}...' успешно отправлено {len(selected_user_ids)} пользователям.")
            del request.session['selected_users_for_notification']
            return redirect('admin:auth_user_changelist')
    else:
        form = SendNotificationForm()

    context = {
        'form': form,
        'title': f"Отправить оповещение {len(selected_user_ids)} выбранным пользователям",
        'users': selected_users,
        'opts': User._meta,
        'app_label': 'auth',
    }
    return render(request, 'admin/toManyNotifications.html', context)
