from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserInfoForm
from .models import UserInfo
from django.db import models

class UserInfoInline(admin.StackedInline):
    model = UserInfo
    form = UserInfoForm
    can_delete = False
    verbose_name_plural = "Анкета"
    fk_name = "user"


class UserAdmin(BaseUserAdmin):
    inlines = [UserInfoInline]

    def has_userinfo(self, obj):
        return hasattr(obj, 'userinfo')
    has_userinfo.short_description = 'Анкета'
    has_userinfo.boolean = True

    list_display = BaseUserAdmin.list_display + ('has_userinfo',)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
