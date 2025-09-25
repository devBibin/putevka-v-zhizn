from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from scholar_form.forms import UserInfoForm
from scholar_form.models import UserInfo, ScholarVideo

from django.db import models


class UserAdmin(BaseUserAdmin):
    inlines = []

    def has_userinfo(self, obj):
        return hasattr(obj, 'userinfo')
    has_userinfo.short_description = 'Анкета'
    has_userinfo.boolean = True

    list_display = BaseUserAdmin.list_display + ('has_userinfo',)

@admin.register(ScholarVideo)
class ScholarVideoAdmin(admin.ModelAdmin):
    list_display = ('user',)
    list_filter = ('updated_at',)
    raw_id_fields = ('user',)
