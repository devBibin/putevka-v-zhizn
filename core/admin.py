from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import TelegramAccount, RegistrationPersonalData, UserInfo


class UserInfoInline(admin.StackedInline):
    model = UserInfo
    can_delete = False
    verbose_name_plural = 'Доп. информация о пользователе'


class TelegramAccountInline(admin.StackedInline):
    model = TelegramAccount
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
    search_fields = ('email', 'telegram_username', 'phone_number')
    readonly_fields = ('token', 'created_at', 'updated_at', 'telegram_account')
    fieldsets = (
        (None, {
            'fields': ('user', 'email', 'password', 'current_step', 'token')
        }),
        ('Подтверждение Email', {
            'fields': ('email_verification_code', 'email_code_expires_at', 'email_verified')
        }),
        ('Подтверждение Telegram', {
            'fields': ('telegram_account',)
        }),
        ('Подтверждение Телефона', {
            'fields': ('phone_number', 'phone_verification_code', 'phone_code_expires_at', 'phone_verified')
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


class UserAdmin(BaseUserAdmin):
    inlines = (UserInfoInline, TelegramAccountInline)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)