import logging

from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import TelegramAccount, RegistrationPersonalData
from scholar_form.forms import UserInfoForm
from scholar_form.models import UserInfo
from django.db import models
from django import forms

from core.models import Notification, UserNotification
from core.models import MotivationLetter
from documents.admin import DocumentInline


class UserInfoInline(admin.StackedInline):
    model = UserInfo
    form = UserInfoForm
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'Доп. информация о пользователе'


class TelegramAccountInline(admin.StackedInline):
    model = TelegramAccount
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'Аккаунт Telegram'
    fields = (
        'telegram_id',
        'username',
        'first_name',
        'last_name',
        'language_code',
        'telegram_verified',
        'activation_token',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'activation_token',
        'telegram_verified',
    )

@admin.register(RegistrationPersonalData)
class RegistrationAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'email',
        'current_step',
        'email_verified',
        'get_telegram_verified_display',
        'phone_verified',
        'user',
        'created_at',
    )
    list_filter = (
        'email_verified',
        'telegram_account__telegram_verified',
        'phone_verified',
        'current_step',
        'created_at',
    )
    search_fields = ('email', 'telegram_username', 'phone')
    readonly_fields = ('created_at', 'updated_at', 'telegram_account')
    fieldsets = (
        (None, {
            'fields': ('user', 'email', 'password', 'current_step')
        }),
        ('Подтверждение Email', {
            'fields': ('email_verification_code', 'email_code_expires_at', 'email_verified')
        }),
        ('Подтверждение Telegram', {
            'fields': ('telegram_account',)
        }),
        ('Подтверждение Телефона', {
            'fields': ('phone', 'phone_verified')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_telegram_verified_display(self, obj):
        if obj.telegram_account:
            return obj.telegram_account.telegram_verified
        return False

    get_telegram_verified_display.short_description = "Telegram Verified"  # Заголовок столбца
    get_telegram_verified_display.boolean = True

logger = logging.getLogger(__name__)


@admin.register(MotivationLetter)
class MotivationLetterAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'admin_rating', 'gpt_review')
    list_filter = ('created_at',)
    search_fields = ('letter_text', 'user__username')

    fields = ('user', 'letter_text', 'admin_rating', 'gpt_review', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


    formfield_overrides = {
        models.CharField: {'widget': forms.Textarea(attrs={'rows': 10, 'cols': 80})},
    }

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


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserInfoInline, TelegramAccountInline, DocumentInline)

    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    list_filter = ('is_staff', 'is_active', 'groups')
    actions = ['send_notification_to_selected_users']

    def has_userinfo(self, obj):
        return hasattr(obj, 'userinfo')
    has_userinfo.short_description = 'Анкета'
    has_userinfo.boolean = True

    def send_notification_to_selected_users(self, request, queryset):
        selected_ids = queryset.values_list('id', flat=True)
        request.session['selected_users_for_notification'] = list(selected_ids)
        url = reverse('send_notification_to_users')
        return HttpResponseRedirect(url)

    send_notification_to_selected_users.short_description = "Отправить оповещение выбранным пользователям"

User = get_user_model()

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
