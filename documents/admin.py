from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('caption', 'user', 'uploaded_at', 'status', 'is_deleted', 'only_staff_comment')
    list_filter = ('uploaded_at', 'user', 'status', 'is_deleted')
    search_fields = ('caption', 'user__username', 'status', 'only_staff_comment')
    date_hierarchy = 'uploaded_at'


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    fields = ('caption', 'file', 'uploaded_at', 'status', 'only_staff_comment', 'is_deleted')
    readonly_fields = ('uploaded_at', 'caption', 'file', 'is_deleted')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.can_delete = False
        return formset

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True


class CustomUserAdmin(UserAdmin):
    inlines = [DocumentInline, ]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
