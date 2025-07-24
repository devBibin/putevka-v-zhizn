from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('caption', 'user', 'uploaded_at', 'status', 'is_deleted', 'only_staff_comment', 'uploaded_by_staff', 'display_related_documents', 'is_locked')
    list_filter = ('uploaded_at', 'user', 'status', 'is_deleted', 'uploaded_by_staff')
    search_fields = ('caption', 'user__username', 'status', 'only_staff_comment')
    date_hierarchy = 'uploaded_at'
    raw_id_fields = ('user',)

    readonly_fields = ('display_related_documents',)

    exclude = ('user_file_name', 'uploaded_by_staff')

    def display_related_documents(self, obj):
        if obj.related_documents.exists():
            links = []
            for doc in obj.related_documents.all():
                admin_url = reverse('serve_document', args=[doc.pk])
                link_text = doc.caption or doc.user_file_name or doc.file.name
                links.append(f'<a href="{admin_url}" target="_blank">{link_text}</a>')
            return format_html("<br>".join(links))
        return "Нет прикрепленных документов"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by_staff = request.user.is_staff
        super().save_model(request, obj, form, change)


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    fields = ('caption', 'file', 'uploaded_at', 'status', 'only_staff_comment', 'is_deleted', 'display_related_documents')
    readonly_fields = ('uploaded_at', 'caption', 'file', 'is_deleted', 'display_related_documents')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.can_delete = False
        return formset

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def display_related_documents(self, obj):
        if obj.related_documents.exists():
            links = []
            for doc in obj.related_documents.all():
                admin_url = reverse('serve_document', args=[doc.pk])
                link_text = doc.caption or doc.user_file_name or doc.file.name
                links.append(f'<a href="{admin_url}" target="_blank">{link_text}</a>')
            return format_html("<br>".join(links))
        return "Нет прикрепленных документов"

    display_related_documents.short_description = "Прикрепленные документы"


class CustomUserAdmin(UserAdmin):
    inlines = [DocumentInline, ]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
