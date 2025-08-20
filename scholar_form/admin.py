from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from scholar_form.forms import UserInfoForm
from scholar_form.models import UserInfo

from django.db import models


class UserAdmin(BaseUserAdmin):
    inlines = []

    def has_userinfo(self, obj):
        return hasattr(obj, 'userinfo')
    has_userinfo.short_description = 'Анкета'
    has_userinfo.boolean = True

    list_display = BaseUserAdmin.list_display + ('has_userinfo',)
