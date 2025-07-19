import logging

from django.contrib import admin

from core.models import Notification

logger = logging.getLogger(__name__)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'created_at', 'is_seen')
    list_filter = ('is_seen', 'created_at')
    search_fields = ('recipient__username', 'message', 'sender__username')

    raw_id_fields = ('recipient', 'sender')

    actions = ['mark_seen', 'mark_unseen']

    def mark_seen(self, request, queryset):
        notification_ids = list(queryset.values_list('id', flat=True))

        queryset.update(is_seen=True)
        self.message_user(request, 'Оповещения помечены как просмотренные.')
        logger.info(f'Оповещения {notification_ids} помечены как прочитанные пользователем {request.user.username}')
    mark_seen.short_description = 'Пометить как просмотренные'

    def mark_unseen(self, request, queryset):
        notification_ids = list(queryset.values_list('id', flat=True))

        queryset.update(is_seen=False)
        self.message_user(request, 'Оповещения помечены как непросмотренные.')
        logger.info(f'Оповещения {notification_ids} помечены как непрочитанные пользователем {request.user.username}')
    mark_unseen.short_description = 'Пометить как непросмотренные'