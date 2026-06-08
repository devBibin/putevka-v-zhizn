from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from scholar_form.forms import UserInfoForm
from scholar_form.models import UserInfo, ScholarVideo, UserPersonalData, VideoInstruction, InterviewInstruction

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


class UserPersonalDataInline(admin.StackedInline):
    model = UserPersonalData


@admin.register(VideoInstruction)
class VideoInstructionAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("title", "text", "url")
    ordering = ("-updated_at",)

    def has_add_permission(self, request):
        if VideoInstruction.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(InterviewInstruction)
class InterviewInstructionAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("title", "text", "url")
    ordering = ("-updated_at",)

    def has_add_permission(self, request):
        if InterviewInstruction.objects.exists():
            return False
        return super().has_add_permission(request)
