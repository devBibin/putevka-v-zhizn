import logging

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse

from core.models import Notification, UserNotification

User = get_user_model()

logger = logging.getLogger(__name__)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('message', 'display_recipients', 'created_at', 'sender__username')
    list_filter = ('created_at',)
    search_fields = ('recipients__username', 'message', 'sender__username')
    exclude = ('sender',)

    raw_id_fields = ('recipients',)

    class UserNotificationInline(admin.TabularInline):
        model = UserNotification
        extra = 1
        raw_id_fields = ('recipient',)
        list_display = ('recipient', 'is_seen')
        readonly_fields = ('seen_at',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.sender = request.user
        super().save_model(request, obj, form, change)

    inlines = [UserNotificationInline]

    def display_recipients(self, obj):
        return ", ".join([user.username for user in obj.recipients.all()[:5]]) + (
            "..." if obj.recipients.count() > 10 else "")

    display_recipients.short_description = "Получатели"


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('notification', 'recipient', 'is_seen', 'seen_at')
    list_filter = ('is_seen', 'seen_at')
    search_fields = ('notification__message', 'recipient__username')
    raw_id_fields = ('notification', 'recipient')


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class MyUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    list_filter = ('is_staff', 'is_active', 'groups')
    actions = ['send_notification_to_selected_users']

    def send_notification_to_selected_users(self, request, queryset):
        selected_ids = queryset.values_list('id', flat=True)
        request.session['selected_users_for_notification'] = list(selected_ids)

        url = reverse('send_notification_to_users')
        return HttpResponseRedirect(url)

    send_notification_to_selected_users.short_description = "Отправить оповещение выбранным пользователям"
