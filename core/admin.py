from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import TelegramAccount

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
        'is_active_web',
        'activation_token',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'activation_token',
    )

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (TelegramAccountInline,)

    list_display = BaseUserAdmin.list_display + ('get_is_active_web',)

    def get_is_active_web(self, obj):
        if hasattr(obj, 'telegram_account'):
            return obj.telegram_account.is_active_web
        return False

    get_is_active_web.short_description = "Активен в вебе"
    get_is_active_web.boolean = True